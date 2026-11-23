"""Best self-reported score per student on the MP3 leaderboard (GitHub issues)."""
import json
import re
import sys

data = json.load(open(sys.argv[1]))
best = {}
for item in data.get("items", []):
    body = item.get("body") or ""
    sid = re.search(r'"student_id": "([0-9]+)"', body)
    correct = re.search(r'"correct": ([0-9]+)', body)
    if sid and correct:
        best[sid.group(1)] = max(best.get(sid.group(1), 0), int(correct.group(1)))
scores = sorted(best.values(), reverse=True)
print("issues", data.get("total_count"), "students", len(scores), "best scores", scores)
