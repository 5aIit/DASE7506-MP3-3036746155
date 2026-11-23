"""Aggregate LLM generation outcomes by the run's status (ok / FP / NM) and example kind.

Prints counts only (safe for holdout). Usage: python dev/llm/gen_breakdown.py <gen_eval.json> [run]
"""
import json
import os
import sys
from collections import Counter
from pathlib import Path

WORK = Path(os.environ.get("MP3_WORK", Path.home() / "mp3/work"))
gen = json.loads(Path(sys.argv[1]).read_text())["outputs"]
run = sys.argv[2] if len(sys.argv) > 2 else "v2-nollm"
rec = {d["id"]: d for d in json.loads((WORK / "runs" / run / "records.json").read_text())}
c = Counter()
for o in gen:
    d = rec[o["id"]]
    key = (d["status"], d["kind"])
    c[key + ("n",)] += 1
    if o.get("match"):
        c[key + ("llm_match",)] += 1
        c[key + ("llm_match_correct" if o.get("correct") else "llm_match_wrong",)] += 1
for status in ("NM", "FP", "ok"):
    for kind in ("empty", "1row", "multi"):
        n = c[(status, kind, "n")]
        if n:
            print(f"{status:2s} {kind:5s} n={n:3d} llm_match={c[(status, kind, 'llm_match')]:3d} "
                  f"match&correct={c[(status, kind, 'llm_match_correct')]:3d} "
                  f"match&wrong={c[(status, kind, 'llm_match_wrong')]:3d}")
