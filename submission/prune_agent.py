"""Final-stage convention proposals and value grounding on the incumbent (R03).

Wraps the v1 controller. When v1 is about to submit:

1. If v1's answer did not match the public example but another checked query
   did, v1's choice stands untouched.
2. Conventions: build rewrites of the incumbent (convention_rules, join_prune),
   the full composition first and then each rewrite alone, and spend official
   checks on them. A rewrite that matches the public example becomes the new
   incumbent. The schema tool is called first when needed.
3. Value grounding (only when the public example is empty, so it cannot tell
   a wrong string literal from a right one): run v1's read-only value probe
   through the official execute tool for the incumbent's string filters, then
   check v1's observed-value repairs. A matching repair becomes the answer.
Every submitted rewrite was checked and matched; otherwise the incumbent stays.
"""
from convention_rules import count_star, drop_distinct, like_to_equality, semi_join
from join_prune import needs_schema, pruned_query
from submission import _key


class FinalVariants:
    MAX_COMPLETIONS = 4  # course limit is 6 completions per task
    LLM_RESERVE = 2      # calls kept for the LLM while nothing matches the example

    def __init__(self, base, *, prune_joins=False, like_to_equality=False, drop_distinct=False,
                 count_star=False, semi_join=False, ground_values=False, llm_on_nomatch=False,
                 llm_on_weak=False, llm_replace_weak=False):
        self.base = base
        self.flags = {"prune_joins": prune_joins, "like_to_equality": like_to_equality,
                      "drop_distinct": drop_distinct, "count_star": count_star,
                      "semi_join": semi_join, "ground_values": ground_values,
                      "llm_on_nomatch": llm_on_nomatch, "llm_on_weak": llm_on_weak,
                      "llm_replace_weak": llm_replace_weak}
        self._reset()

    def _reset(self):
        self.incumbent, self.phase, self.queue = None, None, []
        self.llm_purpose, self.llm_calls, self.llm_sources = None, 0, set()
        self.pre_used, self.pre_active = False, False

    # ---- proposal construction -------------------------------------------
    def _transforms(self, question, schema):
        f = self.flags
        steps = []
        if f["like_to_equality"]:
            steps.append(lambda s: like_to_equality(s, question))
        if f["drop_distinct"]:
            steps.append(lambda s: drop_distinct(s, question))
        if f["count_star"]:
            steps.append(lambda s: count_star(s, question))
        if f["semi_join"]:
            steps.append(lambda s: semi_join(s, question, schema))
        if f["prune_joins"]:
            steps.append(lambda s: pruned_query(s, question, schema))
        return steps

    def _conventions(self, sql, question, schema):
        steps = self._transforms(question, schema)
        full, applied = sql, 0
        for step in steps:
            out = step(full)
            if out:
                full, applied = out, applied + 1
        proposals = [full] if applied > 1 else []
        proposals += [out for out in (step(sql) for step in steps) if out]
        return self._unique(sql, proposals)

    def _unique(self, sql, proposals):
        seen, out = {_key(sql)}, []
        for s in proposals:
            if s and _key(s) not in seen and len(s.encode()) <= 16000:
                seen.add(_key(s))
                out.append(s)
        return out

    def _value_proposals(self, obs, schema, probe):
        from value_rules import value_repairs
        return self._unique(self.incumbent, list(value_repairs(
            self.incumbent, None, obs["example"], obs["task"]["question"], schema, probe)))

    # ---- control ---------------------------------------------------------
    @staticmethod
    def _schema(history):
        return next((e["observation"] for e in history if e["tool"] == "schema"), None)

    def _next_check(self, obs):
        checked = {_key(e["sql"]): e for e in obs["history"] if e["tool"] == "check"}
        while self.queue:
            sql = self.queue.pop(0)
            event = checked.get(_key(sql))
            if event is not None:
                if event["observation"].get("matches_example"):
                    self.incumbent, self.queue = event["sql"], []
                continue
            if obs["remaining"] > 0:
                return {"tool": "check", "sql": sql}
            self.queue = []
        return None

    def _probe_action(self, obs, schema):
        from value_rules import value_probe
        if (not self.flags["ground_values"] or schema is None
                or obs["example"].get("row_count") != 0 or obs["remaining"] < 2):
            return None
        probe = value_probe([{"sql": self.incumbent}], obs["task"]["question"], schema)
        if probe is None:
            return None
        previous = next((e for e in obs["history"] if e["tool"] == "execute" and e["sql"] == probe), None)
        if previous is not None:
            self.phase = "values"
            self.queue = self._value_proposals(obs, schema, previous["observation"])
            return self._next_check(obs) or {"tool": "submit", "sql": self.incumbent}
        self.phase = "probe"
        return {"tool": "execute", "sql": probe}

    def _advance(self, obs):
        history, question = obs["history"], obs["task"]["question"]
        if self.phase == "start":
            matches = [e for e in history if e["tool"] == "check" and e["observation"].get("matches_example")]
            if matches and not any(e["sql"] == self.incumbent for e in matches):
                return {"tool": "submit", "sql": self.incumbent}
            needs = ((self.flags["prune_joins"] and needs_schema(self.incumbent))
                     or (self.flags["ground_values"] and obs["example"].get("row_count") == 0))
            if needs and self._schema(history) is None and obs["remaining"] >= 2:
                self.phase = "schema"
                return {"tool": "schema"}
            self.phase = "schema"
        if self.phase == "schema":
            self.phase = "conventions"
            self.queue = self._conventions(self.incumbent, question, self._schema(history))
        if self.phase == "conventions":
            action = self._next_check(obs)
            if action is not None:
                return action
            action = self._probe_action(obs, self._schema(history))
            if action is not None:
                return action
            self.phase = "llm"
        if self.phase == "values":
            action = self._next_check(obs)
            if action is not None:
                return action
            self.phase = "llm"
        if self.phase in ("llm", "llm-schema"):
            return self._llm_action(obs) or {"tool": "submit", "sql": self.incumbent}
        return {"tool": "submit", "sql": self.incumbent}

    # ---- optional live LLM proposer (L line) -----------------------------
    def _llm_trigger(self, obs):
        checks = [e for e in obs["history"] if e["tool"] == "check"]
        matched = [e for e in checks if e["observation"].get("matches_example")]
        if not matched:
            return "nomatch" if self.flags["llm_on_nomatch"] else None
        incumbent_matched = any(e["sql"] == self.incumbent for e in matched)
        if (incumbent_matched and self.flags["llm_on_weak"]
                and obs["example"].get("row_count", 2) <= 1):
            return "weak"
        return None

    def _llm_action(self, obs):
        history = obs["history"]
        if self.llm_purpose is None:
            self.llm_purpose = self._llm_trigger(obs)
        if self.llm_purpose is None or self.llm_calls >= self.MAX_COMPLETIONS or obs["remaining"] <= 0:
            return None
        schema = self._schema(history)
        if schema is None:
            if obs["remaining"] < 2 or self.phase == "llm-schema":
                return None
            self.phase = "llm-schema"
            return {"tool": "schema"}
        from llm_generate import generate, schema_consistent
        from llm_prompt import build_messages
        checked = {_key(e["sql"]): e for e in history if e["tool"] == "check"}
        # Repair the original draft first (the offline-evaluated format), then the
        # newest other checked queries. Generation costs no tool call; a check does,
        # so generated SQL that names unknown tables/columns is dropped unchecked.
        sources = [e for e in history if e["tool"] == "check" and e["sql"] == obs["issue_sql"]][:1]
        sources += [e for e in reversed(history) if e["tool"] == "check" and e["sql"] != obs["issue_sql"]]
        sources = [e for e in sources if e["sql"] not in self.llm_sources]
        if self.llm_purpose == "weak":
            sources = [e for e in sources if e["sql"] == self.incumbent]
        while sources and self.llm_calls < self.MAX_COMPLETIONS:
            src = sources.pop(0)
            self.llm_sources.add(src["sql"])
            messages = build_messages(obs["task"]["question"], schema, src["sql"],
                                      src["observation"], obs["example"])
            self.llm_calls += 1
            sql, _ = generate(messages, task_id=obs["task"]["id"], purpose=self.llm_purpose)
            if sql is None or len(sql.encode()) > 16000 or not schema_consistent(sql, schema):
                continue
            event = checked.get(_key(sql))
            if event is None:
                self.phase = "llm-check"
                return {"tool": "check", "sql": sql}
            if self.llm_purpose == "weak":
                return None
        return None

    def _after_llm_check(self, obs):
        last = obs["history"][-1]
        if last["observation"].get("matches_example"):
            if self.llm_purpose == "nomatch" or self.flags["llm_replace_weak"]:
                self.incumbent = last["sql"]
            return {"tool": "submit", "sql": self.incumbent}
        self.phase = "llm"
        if self.llm_purpose == "weak":
            return {"tool": "submit", "sql": self.incumbent}
        return self._llm_action(obs) or {"tool": "submit", "sql": self.incumbent}

    def _should_preempt(self, obs):
        history = obs["history"]
        return (self.flags["llm_on_nomatch"] and not self.pre_used
                and 0 < obs["remaining"] <= self.LLM_RESERVE
                and any(e["tool"] == "check" for e in history)
                and not any(e["tool"] == "check" and e["observation"].get("matches_example")
                            for e in history))

    def act(self, obs):
        history = obs["history"]
        if not history:
            self._reset()
        if self.pre_active:
            # Reserved-budget LLM attempt made before v1 spends its last calls.
            last = history[-1]
            if self.phase == "llm-schema":
                action = self._llm_action(obs)
                if action is not None and action["tool"] == "check":
                    return action
            elif self.phase == "llm-check" and last["observation"].get("matches_example"):
                self.pre_active, self.phase = False, None
                return {"tool": "submit", "sql": last["sql"]}
            self.pre_active, self.phase = False, None
        if self.incumbent is None:
            if self._should_preempt(obs):
                self.pre_used, self.pre_active, self.llm_purpose = True, True, "nomatch"
                action = self._llm_action(obs)
                if action is not None:
                    return action
                self.pre_active, self.phase = False, None
            action = self.base.act(obs)
            if action["tool"] != "submit":
                return action
            self.incumbent, self.phase = action["sql"], "start"
            return self._advance(obs)
        last = history[-1]
        if self.phase == "llm-check":
            return self._after_llm_check(obs)
        if last["tool"] == "check" and last["observation"].get("matches_example"):
            self.incumbent, self.queue = last["sql"], []
        if self.phase == "probe" and last["tool"] == "execute":
            self.phase = "values"
            self.queue = self._value_proposals(obs, self._schema(history), last["observation"])
        return self._advance(obs)
