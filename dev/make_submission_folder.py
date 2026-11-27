"""Build the GitHub submission folder from the verified release ZIPs only.

Layout of <dest>:
  <contents of MP3_source_v3.zip>   README, REPORT.pdf, REPRODUCE, requirements, submission/, outputs/, dev/
  release/MP3_source_v3.zip         byte-identical copies of the verified ZIPs
  release/MP3_adapter_v3.zip
  release/SHA256SUMS
  release/package.json
Nothing outside the two verified ZIPs is copied, so the repository content is
exactly what was reproduced (outputs/reproduction.json).
Usage: python dev/make_submission_folder.py <release_dir> <dest>
"""
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

rel, dest = Path(sys.argv[1]), Path(sys.argv[2])
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
record = json.loads((rel / "package.json").read_text())
src_name = "MP3_source_v3.zip"
EXPECT = {"MP3_source_v3.zip": record["source_zip"]["sha256"],
          "MP3_adapter_v3.zip": record["adapter_zip"]["sha256"]}
for name, digest in EXPECT.items():
    assert (rel / name).is_file(), f"{rel / name} is missing"
    assert sha(rel / name) == digest, f"{name} does not match the verified hash"
assert not dest.exists() or not any(dest.iterdir()), f"{dest} is not empty"
dest.mkdir(parents=True, exist_ok=True)
prefix = "MP3_source_v3"
with zipfile.ZipFile(rel / src_name) as z:
    for info in z.infolist():
        if info.is_dir():
            continue
        target = dest / Path(info.filename).relative_to(prefix)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(z.read(info))
(dest / "release").mkdir()
for name in EXPECT:
    shutil.copy2(rel / name, dest / "release" / name)
(dest / "release" / "SHA256SUMS").write_text("".join(f"{d}  {n}\n" for n, d in EXPECT.items()), newline="\n")
shutil.copy2(rel / "package.json", dest / "release" / "package.json")
files = [p for p in dest.rglob("*") if p.is_file()]
print(f"{len(files)} files, {sum(p.stat().st_size for p in files) / 2**20:.1f} MiB in {dest}")
print("test-score.json sha256:", sha(dest / "outputs" / "test-score.json"))
print("REPORT.md present:", (dest / "REPORT.md").exists())
