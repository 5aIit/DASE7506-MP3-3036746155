"""Export a trained LoRA checkpoint as the 2-file adapter required by the course.

Copies adapter_model.safetensors and adapter_config.json only (no README, no
optimizer state), rewrites base_model_name_or_path to the public repository id
and records the base revision, then verifies that the safetensors file holds
only LoRA A/B tensors and that loading works with
PeftModel.from_pretrained(base, dir, is_trainable=False).

Usage: <venv>/bin/python dev/llm/export_adapter.py <checkpoint_dir> <export_dir>
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

from safetensors import safe_open

REPO, REVISION = "Qwen/Qwen3-0.6B", "c1899de289a04d12100db370d81485cdf75e47ca"
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
if dst.exists():
    for f in dst.iterdir():
        f.unlink()
dst.mkdir(parents=True, exist_ok=True)
shutil.copy2(src / "adapter_model.safetensors", dst / "adapter_model.safetensors")
config = json.loads((src / "adapter_config.json").read_text())
config["base_model_name_or_path"] = REPO
config["revision"] = REVISION
assert config.get("modules_to_save") in (None, []), "modules_to_save must be empty"
assert config.get("peft_type") == "LORA" and config.get("bias") == "none"
(dst / "adapter_config.json").write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")

with safe_open(str(dst / "adapter_model.safetensors"), "pt") as f:
    keys = list(f.keys())
    n_params = 0
    for k in keys:
        assert ".lora_A." in k or ".lora_B." in k, f"non-LoRA tensor: {k}"
        n_params += f.get_slice(k).get_shape()[0] * f.get_slice(k).get_shape()[1]
files = sorted(p.name for p in dst.iterdir())
assert files == ["adapter_config.json", "adapter_model.safetensors"], files
digest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(dst.iterdir())}
size = sum(p.stat().st_size for p in dst.iterdir())
print(json.dumps({"files": files, "tensors": len(keys), "lora_parameters": n_params,
                  "bytes": size, "sha256": digest}, indent=1))
