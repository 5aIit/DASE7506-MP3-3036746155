"""Discovery-only look at no-match failures: gold set operations and checked candidates.

Usage: python dev/nm_study.py <run>   (prints discovery tasks only; holdout is counted, never shown)
"""
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

WORK = Path(os.environ.get("MP3_WORK", Path.home() / "mp3/work"))
DATA = Path(os.environ.get("MP3_PKG", Path.home() / "mp3/MP3_SQL_student_package")) / "mp3_sql/data"
run = sys.argv[1]
rec = {d["id"]: d for d in json.loads((WORK / "runs" / run / "records.json").read_text())}
gold = {m["id"]: m["gold_sql"] for m in map(json.loads, open(DATA / "train_memory.jsonl"))}
rows = {json.loads(l)["id"]: json.loads(l) for l in open(DATA / "train.jsonl")}
preds = {p["id"]: p for p in json.loads((WORK / "runs" / run / "train.json").read_text())["predictions"]}
SETOP = re.compile(r"\b(EXCEPT|INTERSECT|UNION)\b", re.I)
flat = lambda s: " ".join(s.split())

stat = Counter()
for i, d in rec.items():
    if d["group"] not in ("discovery", "holdout") or d["status"] != "NM":
        continue
    m = SETOP.search(gold[i])
    stat[(d["group"], m.group(1).upper() if m else "none")] += 1
print("NM tasks by gold set operation:", dict(sorted(stat.items())))
# all discovery tasks (any status) whose gold uses a set operation
allset = Counter((rec[i]["group"], rec[i]["status"]) for i in rec
                 if rec[i]["group"] in ("discovery", "holdout") and SETOP.search(gold[i]))
print("tasks with set-op gold, by group/status:", dict(sorted(allset.items())))

for i, d in rec.items():
    if d["group"] != "discovery" or d["status"] == "ok" or not SETOP.search(gold[i]):
        continue
    print(f"\n[{d['status']}] {d['db']} | {rows[i]['question']}")
    print("   GOLD :", flat(gold[i])[:300])
    for e in preds[i]["trace"]:
        if e["tool"] == "check":
            o = e["observation"]
            print(f"   chk  match={o.get('matches_example')} rows={o.get('row_count')} :", flat(e["sql"])[:220])
