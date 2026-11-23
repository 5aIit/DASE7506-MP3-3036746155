"""Agent-visible cost statistics of an official prediction file (any split).

Uses only the recorded tool traces (tool names, public-example match flags),
never grading references or per-question scores.
Usage: python dev/trace_stats.py <predictions.json>
"""
import json
import sys
from collections import Counter

doc = json.load(open(sys.argv[1]))
preds = doc["predictions"]
actions, dist = Counter(), Counter()
final_match = changed = 0
for p in preds:
    dist[p["tool_calls"]] += 1
    checks = {}
    for e in p["trace"]:
        actions[e["tool"]] += 1
        if e["tool"] == "check":
            checks[e["sql"]] = e["observation"].get("matches_example")
    final_match += bool(checks.get(p["sql"]))
print(json.dumps({"split": doc["split"], "n": len(preds),
                  "mean_tool_calls": sum(p["tool_calls"] for p in preds) / len(preds),
                  "tool_call_distribution": dict(sorted(dist.items())),
                  "tool_action_counts": {k: v for k, v in sorted(actions.items()) if k != "submit"},
                  "final_sql_matches_public_example": final_match,
                  "prediction_seconds": round(doc.get("prediction_seconds", 0), 1)}, indent=1))
