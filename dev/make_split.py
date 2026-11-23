"""Fixed schema-level discovery/holdout split of the TRAIN split (R01).

Every train database goes wholly to one group, so holdout measures transfer to
unseen schemas, as test does. Assignment depends only on the db_id and a fixed
salt, never on outcomes. Writes dev/split.json.
"""
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

PKG = Path(os.environ.get("MP3_PKG", Path.home() / "mp3/MP3_SQL_student_package"))
sys.path.insert(0, str(PKG))
from mp3_sql.common import load_bank  # noqa: E402

SALT = "dase7506-mp3-split-v1"
rows, _, _ = load_bank("train")
tasks = Counter(r["db_id"] for r in rows)
groups = {"discovery": [], "holdout": []}
for db in sorted(tasks):
    h = int(hashlib.sha256(f"{SALT}|{db}".encode()).hexdigest()[:8], 16)
    groups["holdout" if h % 3 == 0 else "discovery"].append(db)
doc = {"salt": SALT, "rule": "sha256(salt|db_id)[:8] mod 3 == 0 -> holdout", **groups,
       "tasks": {g: sum(tasks[d] for d in dbs) for g, dbs in groups.items()}}
(Path(__file__).resolve().parent / "split.json").write_text(json.dumps(doc, indent=1) + "\n")
print({g: (len(dbs), doc["tasks"][g]) for g, dbs in groups.items()})
