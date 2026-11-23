"""Show final-SQL changes between two runs for discovery/validation tasks only.

Usage: python dev/diff_runs.py <old-run> <new-run>
Holdout tasks are listed by id only, never with SQL, to keep holdout clean.
"""
import json
import os
import sys
from pathlib import Path

PKG = Path(os.environ.get("MP3_PKG", Path.home() / "mp3/MP3_SQL_student_package"))
WORK = Path(os.environ.get("MP3_WORK", Path.home() / "mp3/work"))
DATA = PKG / "mp3_sql/data"

old = {d["id"]: d for d in json.loads((WORK / "runs" / sys.argv[1] / "records.json").read_text())}
new = {d["id"]: d for d in json.loads((WORK / "runs" / sys.argv[2] / "records.json").read_text())}
gold = {m["id"]: m["gold_sql"] for m in map(json.loads, open(DATA / "train_memory.jsonl"))}
gold.update(json.loads((DATA / "validation_references.json").read_text())["gold_sql"])
question = {}
for split in ("train", "validation"):
    for line in open(DATA / f"{split}.jsonl"):
        r = json.loads(line)
        question[r["id"]] = r["question"]
flat = lambda s: " ".join(s.split())[:300]
for i, d in new.items():
    o = old.get(i)
    if o is None or o["final_sql"] == d["final_sql"]:
        continue
    tag = ("GAIN" if d["passed"] and not o["passed"] else "LOST" if o["passed"] and not d["passed"]
           else "same-" + ("ok" if d["passed"] else "fail"))
    if d["group"] == "holdout":
        print(f"[holdout] {tag} {i}")
        continue
    print(f"[{d['group']}] {tag} {d['db']} [{d['kind']}] {question[i]}")
    print(f"   OLD : {flat(o['final_sql'])}")
    print(f"   NEW : {flat(d['final_sql'])}")
    print(f"   GOLD: {flat(gold[i])}")
