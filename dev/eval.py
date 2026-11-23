"""Development evaluation on TRAIN/VALIDATION only (R01).

Runs the official predictor and scorer on an exported agent, then reports
accuracy per schema group (discovery / holdout / validation), per public
example strength, false-positive vs no-match failures, the candidate-pool
upper bound, and gained/lost task ids against a previous run.

The test split is refused on purpose: test runs are milestone-only and are
launched by hand with the official commands (see 计划书.md §4).

Usage (inside WSL):
  ~/mp3/MP3_SQL_student_package/.venv312/bin/python dev/eval.py \
      --name v1 --method submission/rule_agent.py --checkpoint submission/config.json \
      [--compare v1] [--splits train validation] [--no-oracle]
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PKG = Path(os.environ.get("MP3_PKG", Path.home() / "mp3/MP3_SQL_student_package"))
WORK = Path(os.environ.get("MP3_WORK", Path.home() / "mp3/work"))
PYTHON = os.environ.get("MP3_PYTHON", str(PKG / ".venv312/bin/python"))
HERE = Path(__file__).resolve().parent
SPLIT_FILE = HERE / "split.json"

sys.path.insert(0, str(PKG))
from mp3_sql.common import load_bank, result_fingerprint  # noqa: E402
from mp3_sql.sqlite_tool import execute_sql  # noqa: E402


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def kind(row):
    n = row["example"]["row_count"]
    return "empty" if n == 0 else ("1row" if n == 1 else "multi")


def clean_hint(text):
    text = text.strip()
    m = re.fullmatch(r"```(?:sql|sqlite)?\s*\n?(.*?)\n?```", text, re.I | re.S)
    return m.group(1).strip() if m else text


def run(cmd, env=None):
    started = time.perf_counter()
    proc = subprocess.run(cmd, cwd=PKG, env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"command failed: {' '.join(map(str, cmd))}\n{proc.stderr[-3000:]}")
    return time.perf_counter() - started


class Oracle:
    """Three-instance correctness of arbitrary SQL; train/validation only."""

    def __init__(self, split):
        assert split in ("train", "validation"), "oracle is restricted to train/validation"
        self.rows, self.manifest, self.folder = load_bank(split)
        self.refs = json.loads((self.folder / f"{split}_references.json").read_text())
        self.path = WORK / "cache" / f"oracle-{split}.json"
        self.cache = json.loads(self.path.read_text()) if self.path.is_file() else {}
        self.lock = threading.Lock()

    def correct(self, row, sql):
        key = hashlib.sha256(f"{row['id']}\x00{sql}".encode()).hexdigest()
        if key in self.cache:
            return self.cache[key]
        tables = [t["name"] for t in self.manifest["databases"][row["db_id"]]["schema"]]
        out = []
        for case in self.refs["tasks"][row["id"]]:
            r = execute_sql(self.folder / case["path"], sql, tables)
            out.append(bool(r["ok"] and result_fingerprint(r, row["ordered"]) == case["expected"]))
        with self.lock:
            self.cache[key] = out
        return out

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.cache))


def analyse(split, pred_path, score_path, groups, use_oracle):
    rows, _, folder = load_bank(split)
    preds = {p["id"]: p for p in json.loads(Path(pred_path).read_text())["predictions"]}
    score = {q["id"]: q for q in json.loads(Path(score_path).read_text())["per_question"]}
    hints = json.loads((folder / "repair_hints.json").read_text())
    oracle = Oracle(split) if use_oracle else None

    def one(row):
        p = preds[row["id"]]
        events = [e for e in p["trace"] if e["tool"] in ("check", "execute")]
        final_checks = [e for e in events if e["tool"] == "check" and e["sql"] == p["sql"]]
        d = {"id": row["id"], "db": row["db_id"], "group": groups[row["db_id"]],
             "kind": kind(row), "passed": score[row["id"]]["passed"],
             "final_match": bool(final_checks and final_checks[-1]["observation"].get("matches_example")),
             "tool_calls": p["tool_calls"], "final_sql": p["sql"]}
        if oracle is not None:
            pool = {e["sql"] for e in events}
            hint_sqls = [clean_hint(h) for h in hints[row["id"]]["suggestions"]]
            d["checked_correct"] = any(all(oracle.correct(row, s)) for s in pool)
            d["hint_correct"] = any(all(oracle.correct(row, s)) for s in set(hint_sqls))
            d["draft_correct"] = all(oracle.correct(row, row["issue_sql"]))
            d["candidates"] = [{"tool": e["tool"], "sql": e["sql"],
                                "match": e["observation"].get("matches_example"),
                                "ok": e["observation"].get("ok"),
                                "row_count": e["observation"].get("row_count"),
                                "correct": oracle.correct(row, e["sql"])} for e in events]
        d["status"] = "ok" if d["passed"] else ("FP" if d["final_match"] else "NM")
        return d

    with ThreadPoolExecutor(8) as pool:
        out = list(pool.map(one, rows))
    if oracle is not None:
        oracle.save()
    return out


def table(records, label):
    n = len(records)
    c = Counter(d["status"] for d in records)
    line = (f"{label:11s} n={n:3d} correct={c['ok']:3d} ({100 * c['ok'] / max(n, 1):5.1f}%) "
            f"FP={c['FP']:3d} NM={c['NM']:3d} calls={sum(d['tool_calls'] for d in records) / max(n, 1):.2f}")
    if records and "checked_correct" in records[0]:
        line += f" pool_upper={sum(d['checked_correct'] for d in records):3d}"
    kinds = []
    for k in ("empty", "1row", "multi"):
        sub = [d for d in records if d["kind"] == k]
        kinds.append(f"{k}={sum(d['passed'] for d in sub)}/{len(sub)}")
    return line + "  [" + " ".join(kinds) + "]"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--method", type=Path, required=True)
    ap.add_argument("--checkpoint", type=Path)
    ap.add_argument("--splits", nargs="+", default=["train", "validation"],
                    choices=["train", "validation"])
    ap.add_argument("--compare", help="name of a previous run to diff against")
    ap.add_argument("--no-oracle", action="store_true")
    args = ap.parse_args()

    split_doc = json.loads(SPLIT_FILE.read_text())
    groups = {db: "discovery" for db in split_doc["discovery"]}
    groups.update({db: "holdout" for db in split_doc["holdout"]})
    method = args.method.resolve()
    out_dir = WORK / "runs" / args.name
    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "src").mkdir(parents=True)
    for f in sorted(method.parent.iterdir()):
        if f.is_file() and f.suffix in (".py", ".json"):
            shutil.copy2(f, out_dir / "src" / f.name)
    hashes = {f.name: sha(f) for f in sorted((out_dir / "src").iterdir())}

    env = {**os.environ, "PYTHONPATH": str(method.parent)}
    records, timing = [], {}
    for split in args.splits:
        for db_id in {r["db_id"] for r in load_bank(split)[0]}:
            groups.setdefault(db_id, "validation" if split == "validation" else "UNASSIGNED")
        pred = out_dir / f"{split}.json"
        score = out_dir / f"{split}-score.json"
        cmd = [PYTHON, "-m", "mp3_sql.predict", "--split", split, "--method", str(method),
               "--output", str(pred)]
        if args.checkpoint:
            cmd += ["--checkpoint", str(args.checkpoint.resolve())]
        t_pred = run(cmd, env)
        t_score = run([PYTHON, "-m", "mp3_sql.score", "--split", split, "--predictions", str(pred),
                       "--output", str(score)])
        timing[split] = {"predict_s": round(t_pred, 1), "score_s": round(t_score, 1)}
        records += analyse(split, pred, score, groups, not args.no_oracle)

    assert not any(d["group"] == "UNASSIGNED" for d in records), "split.json misses a train schema"
    (out_dir / "records.json").write_text(json.dumps(records, indent=1))
    by_group = {g: [d for d in records if d["group"] == g]
                for g in ("discovery", "holdout", "validation")}
    lines = [f"== run {args.name}  timing={timing}"]
    for g, recs in by_group.items():
        if recs:
            lines.append(table(recs, g))

    summary = {"name": args.name, "method": str(method), "hashes": hashes, "timing": timing,
               "groups": {g: {"n": len(r), "correct": sum(d["passed"] for d in r),
                              "calls": sum(d["tool_calls"] for d in r)}
                          for g, r in by_group.items() if r}}
    if args.compare:
        old = {d["id"]: d for d in json.loads(
            (WORK / "runs" / args.compare / "records.json").read_text())}
        lines.append(f"-- diff vs {args.compare}")
        verdict_ok, net_eval = True, 0
        summary["diff"] = {}
        for g, recs in by_group.items():
            shared = [d for d in recs if d["id"] in old]
            if not shared:
                continue
            gained = [d["id"] for d in shared if d["passed"] and not old[d["id"]]["passed"]]
            lost = [d["id"] for d in shared if not d["passed"] and old[d["id"]]["passed"]]
            net = len(gained) - len(lost)
            verdict_ok &= net >= 0
            if g != "discovery":
                net_eval += net
            summary["diff"][g] = {"gained": gained, "lost": lost}
            lines.append(f"{g:11s} +{len(gained)} -{len(lost)} net={net:+d}")
            for i in lost:
                lines.append(f"     LOST {i}")
        gate = verdict_ok and net_eval >= 3
        summary["gate_a"] = {"net_holdout_plus_val": net_eval, "no_group_regresses": verdict_ok,
                             "passed": gate}
        lines.append(f"gate A: holdout+val net={net_eval:+d}, no group regresses={verdict_ok} "
                     f"-> {'PASS' if gate else 'not yet'}")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    text = "\n".join(lines)
    (out_dir / "report.txt").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
