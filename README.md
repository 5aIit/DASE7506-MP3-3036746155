# DASE7506 MP3 — SQL repair agent (v2)

Official test result: **192 / 240 (80.0 %)**, from `outputs/test-score.json`, which is unmodified scorer output.

- `REPORT.pdf`: the report (agent loop, context and memory, ablations, cost, failure cases, prompt-injection safeguards, provenance).
- `REPRODUCE.md`: exact commands, model identity and hashes.
- `submission/`: the agent export. The entry point is `rule_agent.py`, the configuration is `config.json` (v2), and `config_no_llm.json` is the same configuration with the LLM switched off (ablation).
- `outputs/`:
  - `test.json`, `test-score.json`, `summary.json` (timing, memory, environment, hashes) and `llm_completions.jsonl` (every LLM prompt and output) for the test run;
  - `validation/`, the same files for validation;
  - `reproduction.json`, a clean-room rerun of the test split from the release ZIPs.
- `dev/`: development tools (train/validation evaluation, schema split, rewrite tests, LoRA data, training and export, ablation tables) and their records.
- `requirements-v2.txt`: the exact package set of the test run.

The LoRA adapter (2 files) is distributed separately as `MP3_adapter_v2.zip`.

Naming note: during development this version was labelled `v3`. The raw run records in `outputs/` are kept unmodified, so they still show the original paths (`adapter-v3`, `MP3_source_v3.zip`). The agent code, configuration and adapter weights are byte-identical to the ones used in those runs (hashes in `outputs/summary.json`).
