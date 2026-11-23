"""L01: SFT data for the LoRA repair proposer from the TRAIN split only.

Scope `discovery` (dev adapter) uses train tasks on discovery schemas; scope
`all` (final v2 adapter) uses every train task. Each task yields up to 4
examples: the original draft and distinct other candidates (checked
candidates from the run's traces, cached hints), each with its official-format
feedback on the public database, mapped to the task's training gold SQL
(train_memory.jsonl). Validation (and, for `discovery`, holdout) get
prompt-only files (original draft + its real first-check feedback) for
checkpoint selection; their gold is never put in any training file. Test is
never read. Writes ~/mp3/work/llm/sft/ and dev/llm/data_provenance_<scope>.json.

Usage: python dev/llm/make_sft.py v2-nollm [discovery|all]
"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1] / "submission"))
from eval import PKG, WORK  # noqa: E402
from mp3_sql.common import load_bank, result_fingerprint  # noqa: E402
from mp3_sql.sqlite_tool import execute_sql  # noqa: E402

from llm_prompt import build_messages  # noqa: E402
from submission import _candidate, _key  # noqa: E402

run = sys.argv[1]
scope = sys.argv[2] if len(sys.argv) > 2 else "discovery"
assert scope in ("discovery", "all")
DATA = PKG / "mp3_sql/data"
OUT = WORK / "llm" / "sft"
OUT.mkdir(parents=True, exist_ok=True)
split_doc = json.loads((HERE.parent / "split.json").read_text())
discovery, holdout = set(split_doc["discovery"]), set(split_doc["holdout"])
train_dbs = discovery if scope == "discovery" else discovery | holdout


def tidy(sql):
    """Collapse whitespace outside quotes (Spider gold has '  =  '); literals untouched."""
    out, quote, space = [], None, False
    for ch in sql.strip().rstrip(";").strip():
        if quote:
            out.append(ch)
            quote = None if ch == quote else quote
        elif ch in "'\"`":
            quote, space = ch, False
            out.append(ch)
        elif ch.isspace():
            if not space:
                out.append(" ")
            space = True
        else:
            space = False
            out.append(ch)
    return "".join(out)


gold = {m["id"]: tidy(m["gold_sql"]) for m in map(json.loads, open(DATA / "train_memory.jsonl"))}
hints = json.loads((DATA / "repair_hints.json").read_text())
expected = json.loads((DATA / "public_results.json").read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def public_feedback(manifest, folder, row, sql):
    meta = manifest["databases"][row["db_id"]]
    r = execute_sql(folder / meta["public_path"], sql, [t["name"] for t in meta["schema"]])
    return {"ok": r["ok"], "columns": r["columns"], "rows": r["rows"][:8], "row_count": len(r["rows"]),
            "error": r["error"],
            "matches_example": bool(r["ok"] and result_fingerprint(r, row["ordered"]) == expected[row["id"]])}


def first_feedback(pred, sql):
    return next((e["observation"] for e in pred["trace"]
                 if e["tool"] in ("check", "execute") and e["sql"] == sql), None)


counts = {}
for split in ("train", "validation"):
    rows, manifest, folder = load_bank(split)
    preds = {p["id"]: p for p in json.loads((WORK / "runs" / run / f"{split}.json").read_text())["predictions"]}
    train_rows, prompt_rows = [], {"validation": [], "holdout": []}
    for row in rows:
        schema = manifest["databases"][row["db_id"]]["schema"]
        pred = preds[row["id"]]
        q, ex = row["question"], row["example"]
        if split == "train" and row["db_id"] in train_dbs:
            drafts = [row["issue_sql"]] + [e["sql"] for e in pred["trace"] if e["tool"] == "check"]
            drafts += [h for h in (_candidate(t) for t in hints[row["id"]]["suggestions"]) if h]
            seen, picked = set(), []
            for d in drafts:
                if _key(d) not in seen:
                    seen.add(_key(d))
                    picked.append(d)
            for d in picked[:4]:
                fb = first_feedback(pred, d) or public_feedback(manifest, folder, row, d)
                train_rows.append({"id": row["id"], "messages": build_messages(q, schema, d, fb, ex),
                                   "target": gold[row["id"]]})
        else:
            group = "validation" if split == "validation" else ("holdout" if row["db_id"] in holdout else None)
            if group is None:
                continue
            fb = first_feedback(pred, row["issue_sql"])
            prompt_rows[group].append({"id": row["id"], "messages": build_messages(q, schema, row["issue_sql"], fb, ex)})
    if split == "train":
        name = f"train_{scope}.jsonl"
        (OUT / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in train_rows))
        counts[f"train_{scope}_examples"] = len(train_rows)
        counts[f"train_{scope}_tasks"] = len({r["id"] for r in train_rows})
        if scope == "discovery":
            (OUT / "holdout_prompts.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in prompt_rows["holdout"]))
            counts["holdout_prompts"] = len(prompt_rows["holdout"])
    else:
        (OUT / "validation_prompts.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in prompt_rows["validation"]))
        counts["validation_prompts"] = len(prompt_rows["validation"])

targets = ("gold_sql of TRAIN tasks whose database is in dev/split.json 'discovery' (train_memory.jsonl)"
           if scope == "discovery" else "gold_sql of ALL 480 TRAIN tasks (train_memory.jsonl)")
not_used = ["validation split (prompts only, checkpoint selection)", "test split (never read)"]
if scope == "discovery":
    not_used.insert(1, "train holdout schemas (prompts only, gate estimate)")
provenance = {
    "purpose": "SFT data for the optional Qwen/Qwen3-0.6B LoRA SQL repair proposer (DASE7506 MP3, L line)",
    "scope": scope,
    "training_targets": targets,
    "training_inputs": ("question, official schema, candidate SQL (original draft, candidates checked by run "
                        f"'{run}' on train, cached repair hints) and its public-database feedback, public example"),
    "not_used_for_training": not_used,
    "external_data": "none; no external LLM generated any training data",
    "source_sha256": {name: sha(DATA / name) for name in
                      ("train.jsonl", "train_memory.jsonl", "repair_hints.json", "public_results.json", "manifest.json")},
    "run_predictions_sha256": sha(WORK / "runs" / run / "train.json"),
    "split_sha256": sha(HERE.parent / "split.json"),
    "prompt_code_sha256": sha(HERE.parents[1] / "submission" / "llm_prompt.py"),
    "counts": counts,
    "output_sha256": {f"train_{scope}.jsonl": sha(OUT / f"train_{scope}.jsonl"),
                      "validation_prompts.jsonl": sha(OUT / "validation_prompts.jsonl")},
}
(HERE / f"data_provenance_{scope}.json").write_text(json.dumps(provenance, indent=1) + "\n")
print(json.dumps(counts))
