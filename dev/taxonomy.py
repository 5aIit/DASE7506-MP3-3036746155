"""R02: structural failure taxonomy (discovery + validation failures only).

Holdout failures are counted but never inspected, so holdout stays a clean
transfer check for gate A. Compares each failed final SQL with the gold SQL of
the TRAIN/VALIDATION task (train_memory / validation_references) and assigns
multi-label differences. Labels are diagnostics for choosing variant families,
not rules applied at run time.

Usage: python dev/taxonomy.py <run-name>   -> dev/reports/r02_taxonomy.md
"""
import json
import os
import sys
from collections import Counter
from pathlib import Path

import sqlglot
from sqlglot import exp

PKG = Path(os.environ.get("MP3_PKG", Path.home() / "mp3/MP3_SQL_student_package"))
WORK = Path(os.environ.get("MP3_WORK", Path.home() / "mp3/work"))
DATA = PKG / "mp3_sql/data"
HERE = Path(__file__).resolve().parent


def parse(sql):
    try:
        t = sqlglot.parse_one(sql, read="sqlite")
        return t
    except Exception:
        return None


def tables(t):
    return {x.name.lower() for x in t.find_all(exp.Table)}


def literals(t):
    return {x.this for x in t.find_all(exp.Literal) if x.is_string}


def where_conjuncts(t):
    w = t.args.get("where") if isinstance(t, exp.Select) else None
    if w is None:
        return 0
    return len(list(w.this.flatten())) if isinstance(w.this, exp.And) else 1


def has(t, cls):
    return t.find(cls) is not None


def count_distinct(t):
    return any(isinstance(c.this, exp.Distinct) for c in t.find_all(exp.Count))


def group_cols(t):
    g = t.args.get("group") if isinstance(t, exp.Select) else None
    return {c.name.lower() for c in g.find_all(exp.Column)} if g else set()


def labels(final, gold):
    f, g = parse(final), parse(gold)
    if f is None or g is None:
        return ["unparsed"]
    out = []
    tf, tg = tables(f), tables(g)
    if tf - tg:
        out.append("extra_join")
    if tg - tf:
        out.append("missing_table")
    if bool(f.args.get("distinct")) != bool(g.args.get("distinct")):
        out.append("distinct")
    if count_distinct(f) != count_distinct(g):
        out.append("count_distinct")
    if group_cols(f) != group_cols(g) and group_cols(f) and group_cols(g):
        out.append("group_key")
    if bool(group_cols(f)) != bool(group_cols(g)):
        out.append("grouping")
    lf, lg = literals(f), literals(g)
    if lf != lg:
        if {x.lower().replace(" ", "") for x in lf} == {x.lower().replace(" ", "") for x in lg}:
            out.append("literal_case_space")
        else:
            out.append("literal_value")
    if where_conjuncts(f) > where_conjuncts(g):
        out.append("extra_filter")
    elif where_conjuncts(f) < where_conjuncts(g):
        out.append("missing_filter")
    for cls, name in ((exp.Intersect, "set_intersect"), (exp.Except, "set_except"),
                      (exp.Union, "set_union")):
        if has(g, cls) and not has(f, cls):
            out.append(name)
    if has(f, exp.Like) and not has(g, exp.Like):
        out.append("like_vs_eq")
    if bool(f.args.get("limit")) != bool(g.args.get("limit")):
        out.append("limit_vs_max")
    if bool(f.args.get("order")) != bool(g.args.get("order")):
        out.append("order")
    fs = f.selects if isinstance(f, exp.Select) else []
    gs = g.selects if isinstance(g, exp.Select) else []
    if len(fs) != len(gs):
        out.append("projection_arity")
    aggs = lambda t: Counter(type(a).__name__ for a in t.find_all(exp.AggFunc))
    if aggs(f) != aggs(g):
        out.append("aggregate")
    return out or ["other_semantic"]


def main():
    run = sys.argv[1]
    records = json.loads((WORK / "runs" / run / "records.json").read_text())
    gold = {m["id"]: m["gold_sql"] for m in map(json.loads, open(DATA / "train_memory.jsonl"))}
    gold.update(json.loads((DATA / "validation_references.json").read_text())["gold_sql"])
    questions = {}
    for split in ("train", "validation"):
        for line in open(DATA / f"{split}.jsonl"):
            r = json.loads(line)
            questions[r["id"]] = r
    fails = [d for d in records if not d["passed"]]
    hold = [d for d in fails if d["group"] == "holdout"]
    inspect = [d for d in fails if d["group"] in ("discovery", "validation")]
    tally, rows = Counter(), []
    for d in inspect:
        lab = labels(d["final_sql"], gold[d["id"]])
        tally.update(lab)
        rows.append((d, lab))
    lines = [f"# R02 failure taxonomy (run `{run}`)", "",
             f"Inspected: {len(inspect)} failures (discovery + validation). "
             f"Holdout failures not inspected: {len(hold)}.", "",
             "| label | tasks | FP | NM |", "|---|---|---|---|"]
    for lab, n in tally.most_common():
        fp = sum(1 for d, l in rows if lab in l and d["status"] == "FP")
        lines.append(f"| {lab} | {n} | {fp} | {n - fp} |")
    lines += ["", "## Per task", ""]
    for d, lab in sorted(rows, key=lambda x: (x[0]["status"], x[1])):
        q = questions[d["id"]]
        lines += [f"- **{d['status']}** `{d['db']}` [{d['kind']}] {', '.join(lab)}"
                  f"  pool_correct={d.get('checked_correct')} hint_correct={d.get('hint_correct')}",
                  f"  - Q: {q['question']}",
                  f"  - FINAL: `{' '.join(d['final_sql'].split())[:400]}`",
                  f"  - GOLD: `{' '.join(gold[d['id']].split())[:400]}`"]
    out = HERE / "reports" / "r02_taxonomy.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:4 + 4 + len(tally)]))


if __name__ == "__main__":
    main()
