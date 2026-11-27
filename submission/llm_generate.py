"""Optional live-LLM repair proposer (L line): Qwen/Qwen3-0.6B + submitted LoRA adapter.

Loaded once per process and reused across tasks. CPU, fp32, 4 threads by
default. Local, safetensors-only loading with trust_remote_code=False:
  MP3_BASE_MODEL  directory of Qwen/Qwen3-0.6B at rev c1899de289a04d12100db370d81485cdf75e47ca
  MP3_ADAPTER_DIR directory with adapter_model.safetensors + adapter_config.json
  MP3_LLM_LOG     JSONL path for the completion log (default: llm_completions.jsonl
                  in the working directory). Every completion is logged with the
                  prompt, generated text, token counts, seconds and model/adapter hashes.
Generated text is untrusted: only a single read-only SELECT that sqlglot
parses is ever returned, and the controller still submits it only after an
official check.
"""
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path

from submission import _candidate

REVISION = "c1899de289a04d12100db370d81485cdf75e47ca"
_LOCK = threading.Lock()
_STATE = {}


def extract_sql(text):
    if not isinstance(text, str):
        return None
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    fence = re.search(r"```(?:sql|sqlite)?\s*\n?(.*?)```", text, re.I | re.S)
    if fence:
        text = fence.group(1)
    text = text.strip().rstrip(";").strip()
    return _candidate(text)


def schema_consistent(sql, schema):
    """Cheap static filter before spending an official check on generated SQL:
    every table must exist, and every column must exist in a table the query
    references (qualified columns: in that alias's table). Aliases defined in
    the SELECT list are allowed. Unknown schema -> no filtering."""
    if not isinstance(schema, list):
        return True
    from sqlglot import exp
    from submission import _parse
    tree = _parse(sql)
    if tree is None:
        return False
    tables = {t["name"].casefold(): {c["name"].casefold() for c in t.get("columns", [])}
              for t in schema if isinstance(t, dict) and "name" in t}
    aliases, used = {}, set()
    for t in tree.find_all(exp.Table):
        name = t.name.casefold()
        if name not in tables:
            if any(isinstance(c, exp.CTE) and c.alias_or_name.casefold() == name for c in tree.find_all(exp.CTE)):
                continue
            return False
        aliases[t.alias_or_name.casefold()] = name
        used.add(name)
    outputs = {e.alias.casefold() for e in tree.find_all(exp.Alias) if e.alias}
    subquery_aliases = {s.alias.casefold() for s in tree.find_all(exp.Subquery) if s.alias}

    def scope_tables(select):
        """Tables visible to a SELECT: its own FROM/JOINs plus enclosing SELECTs'."""
        names, node = set(), select
        while node is not None:
            if isinstance(node, exp.Select):
                for t in node.find_all(exp.Table):
                    if t.find_ancestor(exp.Select) is node and t.name.casefold() in tables:
                        names.add(t.name.casefold())
            node = node.parent
        return names

    for col in tree.find_all(exp.Column):
        name = col.name.casefold()
        if col.is_star or not name:
            continue
        if col.table:
            qual = col.table.casefold()
            if qual in subquery_aliases:
                continue
            if qual not in aliases or name not in tables[aliases[qual]]:
                return False
        else:
            select = col.find_ancestor(exp.Select)
            visible = scope_tables(select) if select is not None else used
            if not any(name in tables[t] for t in visible) and name not in outputs:
                return False
    return True


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _load():
    with _LOCK:
        if _STATE:
            return _STATE
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        base = os.environ.get("MP3_BASE_MODEL")
        adapter = os.environ.get("MP3_ADAPTER_DIR")
        if not base or not Path(base).is_dir():
            raise RuntimeError("Set MP3_BASE_MODEL to the local Qwen/Qwen3-0.6B directory")
        torch.set_num_threads(int(os.environ.get("MP3_LLM_THREADS", "4")))
        device = os.environ.get("MP3_LLM_DEVICE", "cpu")
        tok = AutoTokenizer.from_pretrained(base, local_files_only=True, trust_remote_code=False)
        model = AutoModelForCausalLM.from_pretrained(
            base, local_files_only=True, trust_remote_code=False, use_safetensors=True,
            torch_dtype=torch.float32 if device == "cpu" else torch.bfloat16)
        identity = {"base": "Qwen/Qwen3-0.6B", "base_revision": REVISION,
                    "base_weights_sha256": _sha(Path(base) / "model.safetensors"), "adapter": None}
        if adapter:
            from peft import PeftModel
            weights = Path(adapter) / "adapter_model.safetensors"
            if not weights.is_file():
                raise RuntimeError("MP3_ADAPTER_DIR must contain adapter_model.safetensors")
            model = PeftModel.from_pretrained(model, adapter, is_trainable=False)
            identity["adapter"] = {"dir": str(adapter), "sha256": _sha(weights),
                                   "config_sha256": _sha(Path(adapter) / "adapter_config.json")}
        model = model.to(device).eval()
        _STATE.update(tok=tok, model=model, torch=torch, device=device, identity=identity,
                      log=os.environ.get("MP3_LLM_LOG") or "llm_completions.jsonl")
        return _STATE


def generate(messages, *, task_id, purpose, max_new_tokens=256):
    """One greedy completion; returns (sql_or_None, raw_text)."""
    s = _load()
    torch, tok, model = s["torch"], s["tok"], s["model"]
    text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True,
                                   enable_thinking=False)
    enc = tok(text, return_tensors="pt").to(s["device"])
    started = time.perf_counter()
    with _LOCK, torch.inference_mode():
        out = model.generate(**enc, max_new_tokens=min(max_new_tokens, 2048), do_sample=False,
                             temperature=None, top_p=None, top_k=None)
    new = out[0, enc["input_ids"].shape[1]:]
    raw = tok.decode(new, skip_special_tokens=True)
    if s["log"]:
        record = {"task_id": task_id, "purpose": purpose, "identity": s["identity"],
                  "prompt": messages, "generated": raw, "prompt_tokens": int(enc["input_ids"].shape[1]),
                  "new_tokens": int(new.shape[0]), "seconds": round(time.perf_counter() - started, 3)}
        with _LOCK, open(s["log"], "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return extract_sql(raw), raw


def generate_beams(messages, *, task_id, purpose, beams=6, max_new_tokens=256):
    """Deterministic beam search returning `beams` completions (each counts as one
    completion toward the per-task limit). Returns [(sql_or_None, raw_text), ...]
    in beam-score order. Beam search uses no random numbers, so results do not
    depend on a sampling seed."""
    s = _load()
    torch, tok, model = s["torch"], s["tok"], s["model"]
    text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True,
                                   enable_thinking=False)
    enc = tok(text, return_tensors="pt").to(s["device"])
    started = time.perf_counter()
    with _LOCK, torch.inference_mode():
        out = model.generate(**enc, max_new_tokens=min(max_new_tokens, 2048), do_sample=False,
                             num_beams=beams, num_return_sequences=beams, early_stopping=True,
                             temperature=None, top_p=None, top_k=None)
    seconds = round(time.perf_counter() - started, 3)
    results = []
    for rank, seq in enumerate(out):
        new = seq[enc["input_ids"].shape[1]:]
        new = new[new != tok.pad_token_id]
        raw = tok.decode(new, skip_special_tokens=True)
        results.append((extract_sql(raw), raw))
        if s["log"]:
            record = {"task_id": task_id, "purpose": purpose, "identity": s["identity"],
                      "decoding": {"num_beams": beams, "rank": rank}, "prompt": messages,
                      "generated": raw, "prompt_tokens": int(enc["input_ids"].shape[1]),
                      "new_tokens": int(new.shape[0]), "seconds": seconds if rank == 0 else 0.0}
            with _LOCK, open(s["log"], "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return results
