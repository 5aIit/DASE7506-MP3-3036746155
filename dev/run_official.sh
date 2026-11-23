#!/usr/bin/env bash
# Official prediction + scoring for one split with the v2 (live-LLM) route,
# under the reproduction budget: 4 CPU cores, --workers 1, CPU fp32.
# Records commands, environment, timings, peak memory and the completion log.
#
# Usage: bash dev/run_official.sh <split> <out_dir> [config]
#   needs MP3_BASE_MODEL (Qwen/Qwen3-0.6B @ c1899de2...) and MP3_ADAPTER_DIR.
# For the test split this is a milestone run: log it in 进度.md and only read the
# aggregate counts, never per_question.
set -euo pipefail
split=$1; out=$(realpath -m "$2"); config=$(realpath "${3:-$(dirname "$0")/../submission/config.json}")
ROOT=$(realpath "$(dirname "$0")/..")
PKG=${MP3_PKG:-$HOME/mp3/MP3_SQL_student_package}
PY=${MP3_LLM_PYTHON:-$HOME/mp3/llm-venv/bin/python}
: "${MP3_BASE_MODEL:?set MP3_BASE_MODEL}" "${MP3_ADAPTER_DIR:?set MP3_ADAPTER_DIR}"
mkdir -p "$out"; : > "$out/llm_completions.jsonl"
export MP3_LLM_DEVICE=cpu MP3_LLM_THREADS=4 OMP_NUM_THREADS=4 MP3_LLM_LOG=$out/llm_completions.jsonl
cd "$PKG"
predict=("$PY" -m mp3_sql.predict --split "$split" --method "$ROOT/submission/rule_agent.py"
         --checkpoint "$config" --workers 1 --output "$out/$split.json")
score=("$PY" -m mp3_sql.score --split "$split" --predictions "$out/$split.json"
       --output "$out/$split-score.json")
PYTHONPATH=$ROOT/submission taskset -c 0-3 /usr/bin/time -f "%e %M %U %S" -o "$out/predict.time" "${predict[@]}" \
  > "$out/predict.stdout.log" 2> "$out/predict.stderr.log"
taskset -c 0-3 /usr/bin/time -f "%e %M %U %S" -o "$out/score.time" "${score[@]}" \
  > "$out/score.stdout.log" 2> "$out/score.stderr.log"
"$PY" - "$out" "$split" "$ROOT" "$PKG" "$config" <<'EOF'
import hashlib, json, os, platform, sqlite3, subprocess, sys
from pathlib import Path
out, split, root, pkg, config = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4]), Path(sys.argv[5])
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
def t(name):
    wall, rss, user, sys_ = (out / f"{name}.time").read_text().split()[-4:]
    return {"wall_s": float(wall), "peak_rss_kib": int(rss), "user_s": float(user), "sys_s": float(sys_)}
score = json.loads((out / f"{split}-score.json").read_text())
log = [json.loads(l) for l in open(out / "llm_completions.jsonl")]
per_task = {}
for r in log:
    per_task[r["task_id"]] = per_task.get(r["task_id"], 0) + 1
import sqlglot, torch, transformers, peft
summary = {
    "split": split, "n": score["n"], "correct": score["correct"], "accuracy": score["accuracy"],
    "mean_tool_calls": score["mean_tool_calls"],
    "predict": t("predict"), "score": t("score"),
    "llm": {"completions": len(log), "tasks_with_completions": len(per_task),
            "max_completions_per_task": max(per_task.values(), default=0),
            "prompt_tokens": sum(r["prompt_tokens"] for r in log),
            "new_tokens": sum(r["new_tokens"] for r in log),
            "max_new_tokens_one_completion": max((r["new_tokens"] for r in log), default=0),
            "generation_seconds": round(sum(r["seconds"] for r in log), 1),
            "identity": log[0]["identity"] if log else None},
    "environment": {"python": sys.version.split()[0], "platform": platform.platform(),
                    "sqlite": sqlite3.sqlite_version, "sqlglot": sqlglot.__version__,
                    "torch": torch.__version__, "transformers": transformers.__version__,
                    "peft": peft.__version__, "cpu_affinity": "taskset -c 0-3", "workers": 1,
                    "threads": 4, "device": "cpu", "dtype": "float32"},
    "hashes": {"predictions": sha(out / f"{split}.json"), "score": sha(out / f"{split}-score.json"),
               "config": sha(config),
               "submission": {p.name: sha(p) for p in sorted((root / "submission").glob("*.py"))},
               "package_manifest": sha(pkg / "PACKAGE_MANIFEST.json")},
    "git_commit": subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True,
                                 text=True).stdout.strip(),
    "git_dirty": bool(subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                                     capture_output=True, text=True).stdout.strip()),
}
(out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
s = {k: summary[k] for k in ("split", "n", "correct", "accuracy", "mean_tool_calls")}
print(json.dumps(s), "| predict", summary["predict"]["wall_s"], "s,",
      summary["predict"]["peak_rss_kib"] // 1024, "MiB | score", summary["score"]["wall_s"], "s | completions",
      summary["llm"]["completions"], "| dirty", summary["git_dirty"])
EOF
