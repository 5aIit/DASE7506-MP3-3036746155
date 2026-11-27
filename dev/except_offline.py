"""Offline check of except_rules on discovery no-match tasks of a run (dev only).

For each discovery task whose final answer has no public match, build EXCEPT
proposals from the run's checked candidates, check them offline exactly like the
official check tool (public DB + public fingerprint) and score them on all three
instances. Holdout/validation: counts only.
Usage: python dev/except_offline.py <run>
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "submission"))
from eval import WORK, Oracle  # noqa: E402
from mp3_sql.common import result_fingerprint  # noqa: E402
from mp3_sql.sqlite_tool import execute_sql  # noqa: E402
from except_rules import except_proposals  # noqa: E402

run = sys.argv[1]
rec = {d["id"]: d for d in json.loads((WORK / "runs" / run / "records.json").read_text())}
for split in ("train", "validation"):
    oracle = Oracle(split)
    rows = {r["id"]: r for r in oracle.rows}
    expected = json.loads((oracle.folder / "public_results.json").read_text())
    preds = json.loads((WORK / "runs" / run / f"{split}.json").read_text())["predictions"]
    stats = {}
    for p in preds:
        d = rec[p["id"]]
        row = rows[p["id"]]
        schema = oracle.manifest["databases"][row["db_id"]]["schema"]
        props = except_proposals(p["trace"], row["question"], schema)
        g = stats.setdefault(d["group"], {"tasks_with_props": 0, "nm_with_props": 0, "first_match": 0,
                                          "first_match_correct": 0, "any_match_correct": 0,
                                          "props_on_ok_tasks": 0})
        if not props:
            continue
        g["tasks_with_props"] += 1
        if d["status"] == "ok":
            g["props_on_ok_tasks"] += 1
        if d["status"] != "NM":
            continue
        g["nm_with_props"] += 1
        meta = oracle.manifest["databases"][row["db_id"]]
        outs = []
        for sql in props[:3]:
            r = execute_sql(oracle.folder / meta["public_path"], sql, [t["name"] for t in meta["schema"]])
            m = bool(r["ok"] and result_fingerprint(r, row["ordered"]) == expected[row["id"]])
            outs.append((sql, m, all(oracle.correct(row, sql)) if m else False, r["error"]))
        if outs[0][1]:
            g["first_match"] += 1
            g["first_match_correct"] += outs[0][2]
        g["any_match_correct"] += any(o[2] for o in outs)
        if d["group"] == "discovery":
            print(f"[discovery NM] {row['db_id']} | {row['question']}")
            for sql, m, c, err in outs:
                print(f"   match={m} correct={c} err={(err or {}).get('message', '')[:60]} | {sql[:230]}")
    oracle.save()
    for grp, s in stats.items():
        print(grp, s)
