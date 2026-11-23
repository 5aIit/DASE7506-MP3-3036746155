"""Discovery-only statistics: how gold SQL uses DISTINCT / COUNT(DISTINCT) vs question cues."""
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

import sqlglot
from sqlglot import exp

PKG = Path(os.environ.get("MP3_PKG", Path.home() / "mp3/MP3_SQL_student_package"))
DATA = PKG / "mp3_sql/data"
HERE = Path(__file__).resolve().parent
split = json.loads((HERE / "split.json").read_text())
discovery = set(split["discovery"])
rows = [json.loads(l) for l in open(DATA / "train.jsonl")]
gold = {m["id"]: m["gold_sql"] for m in map(json.loads, open(DATA / "train_memory.jsonl"))}
CUE = re.compile(r"\b(distinct|different|unique|kinds?|types?|various|variety)\b", re.I)

top, cnt = Counter(), Counter()
for r in rows:
    if r["db_id"] not in discovery:
        continue
    try:
        t = sqlglot.parse_one(gold[r["id"]], read="sqlite")
    except Exception:
        continue
    cue = bool(CUE.search(r["question"]))
    if isinstance(t, exp.Select):
        top[(cue, bool(t.args.get("distinct")))] += 1
    for c in t.find_all(exp.Count):
        cnt[(cue, isinstance(c.this, exp.Distinct))] += 1
print("top-level SELECT DISTINCT in gold, by question cue (cue, distinct): n")
for k in sorted(top):
    print("  ", k, top[k])
print("COUNT(DISTINCT) in gold, by question cue (cue, count_distinct): n")
for k in sorted(cnt):
    print("  ", k, cnt[k])
