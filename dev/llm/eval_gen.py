"""L02: offline generation quality of base / LoRA checkpoints on VALIDATION or HOLDOUT.

Greedy-decodes one SQL per prompt (original draft + its real feedback), then
reports parse rate, public-example match rate, three-instance correctness,
and the overlap with the run's own correctness:
  rescue      = LLM correct where the run is wrong
  safe_rescue = rescue AND the LLM SQL matches the public example (selectable)
  harmful     = run correct, LLM SQL matches the example but is wrong
Holdout results are aggregate counts only (no SQL is printed).

Usage: <venv>/bin/python dev/llm/eval_gen.py --split validation --adapter <dir>|none [--device cuda]
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1] / "submission"))
from eval import WORK, Oracle  # noqa: E402
from mp3_sql.common import result_fingerprint  # noqa: E402
from mp3_sql.sqlite_tool import execute_sql  # noqa: E402
from llm_generate import extract_sql  # noqa: E402

BASE = os.environ.get("MP3_BASE_MODEL", str(Path.home() / "mp3/models/Qwen3-0.6B"))
ap = argparse.ArgumentParser()
ap.add_argument("--split", choices=("validation", "holdout"), required=True)
ap.add_argument("--adapter", required=True)
ap.add_argument("--device", default="cuda")
ap.add_argument("--run", default="v2-nollm")
ap.add_argument("--max_new", type=int, default=256)
args = ap.parse_args()

tok = AutoTokenizer.from_pretrained(BASE, local_files_only=True, trust_remote_code=False)
dtype = torch.bfloat16 if args.device == "cuda" else torch.float32
model = AutoModelForCausalLM.from_pretrained(BASE, local_files_only=True, trust_remote_code=False,
                                             use_safetensors=True, torch_dtype=dtype)
if args.adapter != "none":
    from peft import PeftModel
    model = PeftModel.from_pretrained(model, args.adapter, is_trainable=False)
model = model.to(args.device).eval()

bank = "validation" if args.split == "validation" else "train"
oracle = Oracle(bank)
rows = {r["id"]: r for r in oracle.rows}
expected = json.loads((oracle.folder / "public_results.json").read_text())
prompts = [json.loads(l) for l in open(WORK / "llm" / "sft" / f"{args.split}_prompts.jsonl")]
run_ok = {d["id"]: d["passed"] for d in json.loads((WORK / "runs" / args.run / "records.json").read_text())}

stats = dict(n=0, parsed=0, matched=0, correct=0, rescue=0, safe_rescue=0, harmful=0, tokens=0)
started = time.time()
outputs = []
tok.padding_side = "left"
BATCH = 8 if args.device == "cuda" else 1
for i in range(0, len(prompts), BATCH):
    chunk = prompts[i:i + BATCH]
    texts = [tok.apply_chat_template(p["messages"], tokenize=False, add_generation_prompt=True,
                                     enable_thinking=False) for p in chunk]
    enc = tok(texts, return_tensors="pt", padding=True).to(args.device)
    with torch.inference_mode():
        gen = model.generate(**enc, max_new_tokens=args.max_new, do_sample=False,
                             temperature=None, top_p=None, top_k=None)
    for p, g in zip(chunk, gen[:, enc["input_ids"].shape[1]:]):
        text = tok.decode(g, skip_special_tokens=True)
        stats["tokens"] += int((g != tok.pad_token_id).sum())
        row = rows[p["id"]]
        sql = extract_sql(text)
        stats["n"] += 1
        rec = {"id": p["id"], "sql": sql}
        if sql:
            stats["parsed"] += 1
            meta = oracle.manifest["databases"][row["db_id"]]
            r = execute_sql(oracle.folder / meta["public_path"], sql, [t["name"] for t in meta["schema"]])
            match = bool(r["ok"] and result_fingerprint(r, row["ordered"]) == expected[row["id"]])
            correct = all(oracle.correct(row, sql))
            stats["matched"] += match
            stats["correct"] += correct
            stats["rescue"] += correct and not run_ok[p["id"]]
            stats["safe_rescue"] += correct and match and not run_ok[p["id"]]
            stats["harmful"] += match and not correct and run_ok[p["id"]]
            rec.update(match=match, correct=correct)
        outputs.append(rec)
oracle.save()
stats["seconds"] = round(time.time() - started, 1)
stats["run_correct"] = sum(run_ok[p["id"]] for p in prompts)
name = Path(args.adapter).parent.name + "-" + Path(args.adapter).name if args.adapter != "none" else "base"
out = WORK / "llm" / "gen_eval" / f"{name}-{args.split}.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({"stats": stats, "outputs": outputs}, indent=1))
print(name, args.split, json.dumps(stats))
