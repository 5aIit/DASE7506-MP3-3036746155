"""Build the two submission ZIPs from the repository (whitelist only).

  MP3_source_v3.zip : README, REPORT.pdf, REPRODUCE, requirements-v3.txt,
                      submission/ (agent export), outputs/, dev/ (tools + records)
  MP3_adapter_v3.zip: exactly adapter_model.safetensors + adapter_config.json

Checks: submission/ code and config hashes equal those recorded by the test run
(outputs/summary.json), the source export is <= 16 MiB, the adapter ZIP holds
exactly the two files (<= 512 MiB), and no file contains obvious credentials.
Usage: python dev/package.py <adapter_dir> <out_dir>
"""
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
adapter_dir, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
out_dir.mkdir(parents=True, exist_ok=True)
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()

summary = json.loads((ROOT / "outputs" / "summary.json").read_text())
for name, digest in summary["hashes"]["submission"].items():
    assert sha(ROOT / "submission" / name) == digest, f"submission/{name} changed since the test run"
assert sha(ROOT / "submission" / "config.json") == summary["hashes"]["config"], "config.json changed"
assert sha(ROOT / "outputs" / "test.json") == summary["hashes"]["predictions"]
assert sha(ROOT / "outputs" / "test-score.json") == summary["hashes"]["score"]

files = [ROOT / n for n in ("README.md", "REPORT.pdf", "REPRODUCE.md", "requirements-v3.txt")]
for folder in ("submission", "outputs", "dev"):
    files += sorted(p for p in (ROOT / folder).rglob("*")
                    if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")
SECRET = re.compile(r"(sk-[A-Za-z0-9-]{16,}|ghp_[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{20,}|"
                    r"AKIA[0-9A-Z]{16}|BEGIN (?:RSA|OPENSSH) PRIVATE KEY|password\s*=)", re.I)
for p in files:
    text = p.read_bytes().decode("utf-8", errors="ignore")
    assert not SECRET.search(text), f"possible credential in {p}"
size = sum(p.stat().st_size for p in files)
assert size <= 16 * 2**20, f"source export {size} bytes > 16 MiB"

src_zip = out_dir / "MP3_source_v3.zip"
with zipfile.ZipFile(src_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for p in files:
        z.write(p, "MP3_source_v3/" + p.relative_to(ROOT).as_posix())

adapter = [adapter_dir / "adapter_model.safetensors", adapter_dir / "adapter_config.json"]
assert sorted(p.name for p in adapter_dir.iterdir()) == sorted(p.name for p in adapter)
ad_zip = out_dir / "MP3_adapter_v3.zip"
with zipfile.ZipFile(ad_zip, "w", zipfile.ZIP_STORED) as z:
    for p in adapter:
        z.write(p, p.name)
assert ad_zip.stat().st_size <= 512 * 2**20

record = {"source_zip": {"files": len(files), "uncompressed_bytes": size, "bytes": src_zip.stat().st_size,
                         "sha256": sha(src_zip)},
          "adapter_zip": {"files": [p.name for p in adapter], "bytes": ad_zip.stat().st_size,
                          "sha256": sha(ad_zip), "member_sha256": {p.name: sha(p) for p in adapter}},
          "test_result": {k: summary[k] for k in ("correct", "n", "accuracy")},
          "git_commit_of_test_run": summary["git_commit"]}
(out_dir / "package.json").write_text(json.dumps(record, indent=1) + "\n")
print(json.dumps(record, indent=1))
