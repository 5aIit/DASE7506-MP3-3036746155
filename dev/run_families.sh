#!/usr/bin/env bash
# Evaluate one config per R03 family on top of the current submission config.
# Usage: bash dev/run_families.sh <base-run> name:switch[,switch] ...
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${MP3_PYTHON:-$HOME/mp3/MP3_SQL_student_package/.venv312/bin/python}
base=$1; shift
for spec in "$@"; do
  name=${spec%%:*}; switches=${spec#*:}
  "$PY" - "$name" "$switches" <<'EOF'
import json, sys
name, switches = sys.argv[1], sys.argv[2]
config = json.load(open("submission/config.json"))
for s in switches.split(","):
    config[s] = True
json.dump(config, open(f"dev/configs/{name}.json", "w"), indent=2)
EOF
  "$PY" dev/eval.py --name "$name" --method submission/rule_agent.py \
    --checkpoint "dev/configs/$name.json" --compare "$base" \
    | grep -E "^(==|discovery|holdout|validation|gate)" | cut -c1-150
done
