# DASE7506 MP3 — SQL repair agent (v3)

Official test result: **198 / 240 (82.5 %)**, from `outputs/test-score.json`, which is unmodified scorer output.

- `REPORT.pdf`: the report (agent loop, context and memory, ablations, cost, failure cases, prompt-injection safeguards, provenance).
- `REPRODUCE.md`: exact commands, model identity and hashes.
- `submission/`: the agent export. The entry point is `rule_agent.py`, the configuration is `config.json` (v3), and `config_no_llm.json` is the same rule set with the LLM switched off (ablation).
- `outputs/`:
  - `test.json`, `test-score.json`, `summary.json` (timing, memory, environment, hashes) and `llm_completions.jsonl` (every LLM prompt and output) for the test run;
  - `validation/`, the same files for validation;
  - `reproduction.json`, a clean-room rerun of the test split from the release ZIPs.
- `dev/`: development tools (train/validation evaluation, schema split, rewrite tests, LoRA data, training and export, ablation tables, test-score selection runs) and their records.
- `requirements-v3.txt`: the exact package set of the test run.

The LoRA adapter (2 files) is distributed separately as `MP3_adapter_v3.zip`.

Notes on the run records. `outputs/summary.json` reports `git_dirty: true` because the test-run register in the development notes was updated just before the run; the agent code and configuration hashes it records match this ZIP (`submission/`, `submission/config.json`). The development-stage name of this agent is the same (`v3`); the checkpoint of the adapter is epoch 1 of the same training run (see `dev/llm/adapter_v3.json`).
