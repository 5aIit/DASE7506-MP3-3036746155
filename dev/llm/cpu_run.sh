#!/usr/bin/env bash
# L04: reproduction-budget measurement for the live-LLM route on a dev split.
# 4 CPU cores, --workers 1, CPU fp32, model loaded once. Reports wall time,
# peak RSS, completions and the official score. Never used on test here.
# Usage: bash dev/llm/cpu_run.sh <split> <config> <adapter_dir> <name>
set -euo pipefail
split=$1; config=$(realpath "$2"); adapter=$(realpath "$3"); name=$4
ROOT=$(realpath "$(dirname "$0")/../..")
PKG=${MP3_PKG:-$HOME/mp3/MP3_SQL_student_package}
PY=${MP3_LLM_PYTHON:-$HOME/mp3/llm-venv/bin/python}
OUT=$HOME/mp3/work/cpu/$name; mkdir -p "$OUT"; : > "$OUT/llm.log"
cd "$PKG"
export MP3_BASE_MODEL=$HOME/mp3/models/Qwen3-0.6B MP3_ADAPTER_DIR=$adapter MP3_LLM_DEVICE=cpu \
       MP3_LLM_THREADS=4 MP3_LLM_LOG=$OUT/llm.log OMP_NUM_THREADS=4 PYTHONPATH=$ROOT/submission
taskset -c 0-3 /usr/bin/time -f "predict wall=%e s maxrss=%M KiB" "$PY" -m mp3_sql.predict --split "$split" \
  --method "$ROOT/submission/rule_agent.py" --checkpoint "$config" --workers 1 \
  --output "$OUT/$split.json" 2> "$OUT/predict.time" >/dev/null || { cat "$OUT/predict.time"; exit 1; }
grep -E "^predict" "$OUT/predict.time"
taskset -c 0-3 /usr/bin/time -f "score   wall=%e s maxrss=%M KiB" "$PY" -m mp3_sql.score --split "$split" \
  --predictions "$OUT/$split.json" --output "$OUT/$split-score.json" 2> "$OUT/score.time" | grep -E '"(correct|n)"'
grep -E "^score" "$OUT/score.time"
echo "completions=$(wc -l < "$OUT/llm.log")"
