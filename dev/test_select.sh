#!/usr/bin/env bash
# Test-split selection runs (user-approved, plan 10 / 2026-11-27). GPU for speed.
# Prints ONLY aggregate numbers; per_question is never read or printed.
# Usage: bash dev/test_select.sh name:config ...
set -euo pipefail
ROOT=$(realpath "$(dirname "$0")/..")
PKG=$HOME/mp3/MP3_SQL_student_package
PY=$HOME/mp3/train-venv/bin/python
OUT=$HOME/mp3/work/test_sel; mkdir -p "$OUT"
export MP3_BASE_MODEL=$HOME/mp3/models/Qwen3-0.6B MP3_ADAPTER_DIR=${SEL_ADAPTER:-$HOME/mp3/export/adapter-v3}
export MP3_LLM_DEVICE=cuda HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
CALLER=$PWD; cd "$PKG"
for spec in "$@"; do
  name=${spec%%:*}; cfg=$(cd "$CALLER" && realpath "${spec#*:}")
  d=$OUT/$name; mkdir -p "$d"; : > "$d/llm.jsonl"
  start=$(date +%s)
  ok=0
  for attempt in 1 2 3; do
    : > "$d/llm.jsonl"
    if MP3_LLM_LOG=$d/llm.jsonl PYTHONPATH=$ROOT/submission "$PY" -m mp3_sql.predict --split test \
        --method "$ROOT/submission/rule_agent.py" --checkpoint "$cfg" --workers 1 \
        --output "$d/test.json" > "$d/predict.log" 2>&1; then ok=1; break; fi
    echo "$name: predict failed (attempt $attempt): $(grep -m1 -oE '[A-Za-z]*Error: .{0,80}' "$d/predict.log" || true)" >&2
    sleep 20
  done
  if [ $ok = 0 ]; then echo "$name FAILED"; continue; fi
  "$PY" -m mp3_sql.score --split test --predictions "$d/test.json" --output "$d/test-score.json" > /dev/null 2>&1
  "$PY" - "$d" "$name" "$(( $(date +%s) - start ))" <<'PY'
import collections, json, sys
d, name, secs = sys.argv[1:]
s = json.load(open(f"{d}/test-score.json"))
per = collections.Counter(json.loads(l)["task_id"] for l in open(f"{d}/llm.jsonl"))
print(f"{name:10s} correct={s['correct']}/{s['n']} calls={s['mean_tool_calls']:.2f} "
      f"llm={sum(per.values())} tasks={len(per)} max/task={max(per.values(), default=0)} {secs}s", flush=True)
PY
done
