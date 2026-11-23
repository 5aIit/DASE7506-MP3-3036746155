"""Why did ground_values not change anything? Inspect discovery/val traces of a run."""
import json
import os
import sys
from pathlib import Path

WORK = Path(os.environ.get("MP3_WORK", Path.home() / "mp3/work"))
run = sys.argv[1]
records = {d["id"]: d for d in json.loads((WORK / "runs" / run / "records.json").read_text())}
stats = {"empty": 0, "probe_run": 0, "probe_ok_complete": 0}
for split in ("train", "validation"):
    preds = json.loads((WORK / "runs" / run / f"{split}.json").read_text())["predictions"]
    for p in preds:
        d = records[p["id"]]
        if d["group"] == "holdout" or d["kind"] != "empty":
            continue
        stats["empty"] += 1
        probes = [e for e in p["trace"] if e["tool"] == "execute" and e["sql"].startswith("/* value-grounding */")]
        if probes:
            stats["probe_run"] += 1
            o = probes[-1]["observation"]
            if o.get("ok") and not o.get("truncated") and o.get("row_count", 9) < 8:
                stats["probe_ok_complete"] += 1
        if d["db"] in ("network_2", "music_4") and not d["passed"]:
            print(d["db"], "calls", p["tool_calls"], [e["tool"] for e in p["trace"]])
            for e in probes:
                print("   probe obs:", json.dumps(e["observation"])[:600])
print(stats)
