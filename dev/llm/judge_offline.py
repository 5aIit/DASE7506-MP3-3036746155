"""Offline estimate for an LLM judge among checked, public-matching candidates.

For tasks where the run checked >= 2 distinct candidates that match the public
example, score each candidate SQL by its log-probability under the LoRA model
given the original-draft prompt (the SFT format), and compare picking the
highest-scoring one against the run's own choice. Uses candidate pools from
dev/pool.py (train/validation only). Prints counts only.

Usage: train-venv/bin/python dev/llm/judge_offline.py --adapter <dir> --groups holdout validation
"""
import argparse
import json
import os
import sys
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

HERE = Path(__file__).resolve().parent


def tidy(sql):
    """Same target normalisation as dev/llm/make_sft.py: collapse whitespace outside quotes."""
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


WORK = Path(os.environ.get("MP3_WORK", Path.home() / "mp3/work"))
BASE = os.environ.get("MP3_BASE_MODEL", str(Path.home() / "mp3/models/Qwen3-0.6B"))
ap = argparse.ArgumentParser()
ap.add_argument("--adapter", required=True)
ap.add_argument("--groups", nargs="+", default=["holdout", "validation"])
ap.add_argument("--run", default="v2b")
args = ap.parse_args()

tok = AutoTokenizer.from_pretrained(BASE, local_files_only=True, trust_remote_code=False)
model = AutoModelForCausalLM.from_pretrained(BASE, local_files_only=True, trust_remote_code=False,
                                             use_safetensors=True, torch_dtype=torch.bfloat16)
from peft import PeftModel  # noqa: E402
model = PeftModel.from_pretrained(model, args.adapter, is_trainable=False).cuda().eval()

prompts = {}
for name in ("holdout_prompts.jsonl", "validation_prompts.jsonl"):
    for line in open(WORK / "llm" / "sft" / name):
        r = json.loads(line)
        prompts[r["id"]] = r["messages"]


@torch.inference_mode()
def logprob(messages, sql):
    prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True,
                                     enable_thinking=False)
    p = tok(prompt, add_special_tokens=False)["input_ids"]
    t = tok(tidy(sql) + "<|im_end|>", add_special_tokens=False)["input_ids"]
    ids = torch.tensor([p + t]).cuda()
    logits = model(input_ids=ids).logits[0, len(p) - 1:-1].float()
    lp = torch.log_softmax(logits, -1).gather(1, torch.tensor(t).cuda()[:, None]).squeeze(1)
    return lp.sum().item(), lp.mean().item()


tasks = [json.loads(l) for s in ("train", "validation") for l in open(WORK / "pool" / f"{args.run}-{s}.jsonl")]
for group in args.groups:
    ts = [t for t in tasks if t["group"] == group and t["id"] in prompts]
    rows = []
    for t in ts:
        cands = {c["sql"]: c for c in t["candidates"] if c["source"] == "checked"
                 and c["feedback"] and c["feedback"].get("matches_example")}
        final = next((c for c in t["candidates"] if c["is_final"]), None)
        if len(cands) < 2 or final is None or final["sql"] not in cands:
            continue
        scored = [(logprob(prompts[t["id"]], s), c) for s, c in cands.items()]
        rows.append((final, scored))
    print(f"== {group}: tasks with >=2 matched checked candidates: {len(rows)} "
          f"(run correct on {sum(f['correct'] for f, _ in rows)}, any correct on "
          f"{sum(any(c['correct'] for _, c in sc) for _, sc in rows)})")
    for kind, idx in (("sum", 0), ("mean", 1)):
        for margin in (0.0, 0.5, 1.0, 2.0, 4.0):
            gain = loss = 0
            for final, scored in rows:
                fscore = next(s[idx] for s, c in scored if c is final)
                best_s, best = max(scored, key=lambda x: x[0][idx])
                pick = best if best_s[idx] > fscore + margin else final
                gain += pick["correct"] and not final["correct"]
                loss += final["correct"] and not pick["correct"]
            print(f"   {kind:4s} margin={margin:<4} +{gain} -{loss} net={gain - loss:+d}")
