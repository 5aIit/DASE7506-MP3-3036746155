#!/usr/bin/env bash
# R01 resource check for the no-live-LLM route: 4 CPU threads, 2 GiB virtual
# address space, prediction + scoring <= 180 s. Uses TRAIN (480 tasks, twice the
# size of test) so that no test run is spent on it.
# Usage: bash dev/resource_check.sh submission/rule_agent.py submission/config.json
set -euo pipefail
METHOD=$(realpath "$1"); CKPT=${2:+$(realpath "$2")}
PKG=${MP3_PKG:-$HOME/mp3/MP3_SQL_student_package}
PY=${MP3_PYTHON:-$PKG/.venv312/bin/python}
OUT=$(mktemp -d)
cd "$PKG"
start=$(date +%s.%N)
(
  ulimit -v 2097152
  PYTHONPATH=$(dirname "$METHOD") taskset -c 0-3 /usr/bin/time -f "predict wall=%e s maxrss=%M KiB" \
    "$PY" -m mp3_sql.predict --split train --method "$METHOD" ${CKPT:+--checkpoint "$CKPT"} \
    --output "$OUT/train.json" >/dev/null
  taskset -c 0-3 /usr/bin/time -f "score   wall=%e s maxrss=%M KiB" \
    "$PY" -m mp3_sql.score --split train --predictions "$OUT/train.json" \
    --output "$OUT/train-score.json" | grep -E '"correct"'
)
total=$(echo "$(date +%s.%N) - $start" | bc)
echo "train total wall=${total}s (limit for 240-task test: 180 s)"
rm -rf "$OUT"
