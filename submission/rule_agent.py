"""Spend otherwise unused calls on additional schema-grounded repairs."""
from rescue import rescue_queries
from submission import build_agent, load_config


class RemainingChecks:
    def __init__(self, base):
        self.base = base
        self.fallback = None
        self.offers = None

    def act(self, obs):
        if not obs["history"]:
            self.fallback = self.offers = None
        if self.offers is None:
            action = self.base.act(obs)
            if action["tool"] != "submit" or obs["remaining"] == 0:
                return action
            self.fallback = action["sql"]
            self.offers = rescue_queries(obs["history"], obs["remaining"], self.fallback,
                                         obs["task"]["question"], obs["example"], obs["ordered"])
        else:
            last = obs["history"][-1]
            if last["observation"].get("matches_example"):
                self.offers = None
                return {"tool":"submit","sql":last["sql"]}
        sql = next(self.offers, None) if obs["remaining"] else None
        if sql is not None:
            return {"tool":"check","sql":sql}
        self.offers = None
        return {"tool":"submit","sql":self.fallback}


# Switches added after v1; all default to off so v1 behaviour is unchanged.
V2_SWITCHES = ("prune_joins", "like_to_equality", "drop_distinct", "count_star", "semi_join",
               "ground_values", "llm_on_nomatch", "llm_on_weak", "llm_replace_weak",
               "llm_beams", "llm_early", "except_nomatch")


# Optional integer settings of the LLM proposer (defaults = the v2 submission).
LLM_LIMITS = {"llm_reserve": ("LLM_RESERVE", 2, 1, 4), "max_completions": ("MAX_COMPLETIONS", 4, 1, 6)}


def create_agent(checkpoint=None):
    config = load_config(checkpoint)
    switches = {key: config.pop(key, False) for key in V2_SWITCHES}
    if any(type(v) is not bool for v in switches.values()):
        raise ValueError("Strategy JSON accepts only boolean feature switches")
    limits = {}
    for key, (attr, default, low, high) in LLM_LIMITS.items():
        value = config.pop(key, default)
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"{key} must be an integer in [{low}, {high}]")
        limits[attr] = value
    agent = RemainingChecks(build_agent(config, checked=checkpoint is not None))
    if any(switches.values()):
        from prune_agent import FinalVariants
        agent = FinalVariants(agent, **switches)
        for attr, value in limits.items():
            setattr(agent, attr, value)
    return agent
