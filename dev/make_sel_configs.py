"""Single-change variants of the v2 configuration for test-score selection."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
base = json.loads((ROOT / "submission" / "config.json").read_text())
VARIANTS = {
    "beam": {"llm_beams": True},
    "early": {"llm_early": True},
    "except": {"except_nomatch": True},
    "k1": {"llm_reserve": 1},
    "k3": {"llm_reserve": 3},
    "k4": {"llm_reserve": 4},
    "mc6": {"max_completions": 6},
    "distinct": {"drop_distinct": True},
    "count": {"count_star": True},
    "like": {"like_to_equality": True},
    "ground": {"ground_values": True},
    "weak": {"llm_on_weak": True, "llm_replace_weak": True},
}
out = ROOT / "dev" / "configs" / "sel"
out.mkdir(parents=True, exist_ok=True)
for name, change in VARIANTS.items():
    (out / f"{name}.json").write_text(json.dumps({**base, **change}, indent=2) + "\n")
print(" ".join(VARIANTS))
