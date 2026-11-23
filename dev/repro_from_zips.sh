#!/usr/bin/env bash
# Clean-room reproduction of the v2 test result from the two submission ZIPs and
# a freshly extracted official package, following REPRODUCE.md. Writes a
# comparison record. This is a reproduction check of the frozen result, not a
# design iteration (logged as such in the test-run register).
# Usage: bash dev/repro_from_zips.sh <release_dir> <record.json>
set -euo pipefail
REL=$(realpath "$1"); RECORD=$(realpath -m "$2")
BASE=$HOME/mp3/repro-$(date +%Y%m%d-%H%M%S); mkdir -p "$BASE"; cd "$BASE"
PKGZIP=$HOME/mp3/downloads/MP3_SQL_student_package.zip
echo "406d69507ccf955a53b35db1c1368bd7452565ebd928b47d0f6161fe35b99a61  $PKGZIP" | sha256sum -c -
python3 -c "import zipfile,sys; [zipfile.ZipFile(a).extractall(b) for a,b in ((sys.argv[1],'.'),(sys.argv[2],'src'),(sys.argv[3],'adapter-v2'))]" \
  "$PKGZIP" "$REL/MP3_source_v2.zip" "$REL/MP3_adapter_v2.zip"
SRC=$BASE/src/MP3_source_v2
cd MP3_SQL_student_package
uv venv --python 3.11 .venv -q
uv pip install --python .venv/bin/python -q -r requirements.txt
uv pip install --python .venv/bin/python -q torch==2.7.1 --index-url https://download.pytorch.org/whl/cpu
uv pip install --python .venv/bin/python -q transformers==4.53.2 peft==0.17.1 accelerate==1.10.1 \
  safetensors==0.8.0 huggingface-hub==0.36.2
. .venv/bin/activate
python -m mp3_sql.check_data | tail -1
export MP3_BASE_MODEL=$HOME/mp3/models/Qwen3-0.6B MP3_ADAPTER_DIR=$BASE/adapter-v2
export MP3_LLM_LOG=$PWD/outputs/llm_completions.jsonl HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=4
mkdir -p outputs
start=$(date +%s)
PYTHONPATH="$SRC/submission" taskset -c 0-3 python -m mp3_sql.predict --split test \
  --method "$SRC/submission/rule_agent.py" --checkpoint "$SRC/submission/config.json" \
  --workers 1 --output outputs/test.json
mid=$(date +%s)
python -m mp3_sql.score --split test --predictions outputs/test.json --output outputs/test-score.json >/dev/null
end=$(date +%s)
python - "$SRC" "$PWD/outputs" "$RECORD" "$((mid-start))" "$((end-mid))" <<'EOF'
import hashlib, json, sqlite3, sys
from pathlib import Path
src, out, record, t_pred, t_score = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
ours = json.loads((src / "outputs" / "test.json").read_text())
new = json.loads((out / "test.json").read_text())
score_old = json.loads((src / "outputs" / "test-score.json").read_text())
score_new = json.loads((out / "test-score.json").read_text())
same_preds = ours["predictions"] == new["predictions"]
same_per_q = score_old["per_question"] == score_new["per_question"]
keys = ("correct", "n", "accuracy", "manifest_sha256", "bank_sha256", "references_sha256", "scorer_sha256", "executor_sha256")
rec = {"what": "clean-room rerun of the test split from MP3_source_v2.zip + MP3_adapter_v2.zip and a freshly extracted, hash-verified official package, following REPRODUCE.md",
       "python": sys.version.split()[0], "sqlite": sqlite3.sqlite_version,
       "result": {k: score_new[k] for k in keys},
       "submitted_result": {k: score_old[k] for k in keys},
       "predictions_identical_except_timing": same_preds,
       "per_question_outcomes_identical": same_per_q,
       "llm_completions": sum(1 for _ in open(out / "llm_completions.jsonl")),
       "prediction_wall_s": t_pred, "scoring_wall_s": t_score}
record.write_text(json.dumps(rec, indent=1) + "\n")
print(json.dumps({k: rec[k] for k in ("result", "predictions_identical_except_timing", "per_question_outcomes_identical", "prediction_wall_s")}, indent=1))
EOF
