#!/usr/bin/env bash
# Dev evaluation of LLM-policy variants on train/val with the GPU (fast).
#   adapter "dev"   = disc-r16/epoch3 (trained on discovery only): holdout is out-of-sample
#   adapter "final" = adapter-v3 (all train): only validation is out-of-sample
# Usage: bash dev/llm/run_variants.sh <dev|final> <base-run-to-compare> name:config ...
set -euo pipefail
cd "$(dirname "$0")/../.."
which=$1; base=$2; shift 2
case $which in
  dev) ADAPTER=$HOME/mp3/work/llm/adapters/disc-r16/epoch3 ;;
  final) ADAPTER=$HOME/mp3/export/adapter-v3-final ;;
  *) echo "unknown adapter $which"; exit 1 ;;
esac
for spec in "$@"; do
  name=${spec%%:*}; cfg=${spec#*:}
  log=$HOME/mp3/work/llm/agent-$name.log; : > "$log"
  MP3_PYTHON=$HOME/mp3/train-venv/bin/python MP3_BASE_MODEL=$HOME/mp3/models/Qwen3-0.6B \
  MP3_ADAPTER_DIR=$ADAPTER MP3_LLM_DEVICE=cuda MP3_LLM_LOG=$log \
    "$HOME/mp3/MP3_SQL_student_package/.venv312/bin/python" dev/eval.py --name "$name" \
    --method submission/rule_agent.py --checkpoint "$cfg" --compare "$base" --no-oracle \
    | grep -E "^(==|discovery|holdout|validation|gate|     LOST)" | cut -c1-140
  echo "completions: $(wc -l < "$log")  tasks: $(python3 -c "import json,sys;print(len({json.loads(l)['task_id'] for l in open(sys.argv[1])}))" "$log")"
done
