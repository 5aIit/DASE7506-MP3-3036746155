# Reproducing the v2 result (192 / 240 on test)

Everything runs offline on Linux x86_64 with 4 CPU threads. No GPU is needed for prediction.
Measured on Ubuntu 24.04 (WSL2), Python 3.11.18, SQLite 3.53.1: prediction 272 s and 4.8 GB peak RSS; scoring 7 s.

## 0. Inputs

| item | identity |
|---|---|
| official package | `MP3_SQL_student_package.zip`, sha256 `406d69507ccf955a53b35db1c1368bd7452565ebd928b47d0f6161fe35b99a61` |
| base model | `Qwen/Qwen3-0.6B`, revision `c1899de289a04d12100db370d81485cdf75e47ca` (`model.safetensors` sha256 `f47f71177f32bcd101b7573ec9171e6a57f4f4d31148d38e382306f42996874b`) |
| adapter ZIP | `adapter_model.safetensors` sha256 `9a0cf37229e658a61edde873aa8557458275f97bedc60e069dd3639a360fa665`, `adapter_config.json` sha256 `253710337a5466105e95413d55471d20ab19d50e8f51ab3fa6cab1d93810c457` |
| this source ZIP | `submission/` (agent export), `submission/config.json` (v2), `outputs/` (our results) |

## 1. Environment (from the official package's top-level directory)

```bash
unzip MP3_SQL_student_package.zip && cd MP3_SQL_student_package
python3.11 -m venv .venv && . .venv/bin/activate
python -m pip install -r requirements.txt                      # sqlglot==27.29.0
python -m pip install torch==2.7.1 --index-url https://download.pytorch.org/whl/cpu
python -m pip install transformers==4.53.2 peft==0.17.1 accelerate==1.10.1 \
                      safetensors==0.8.0 huggingface-hub==0.36.2
python -m mp3_sql.check_data
```

`requirements-v2.txt` in this ZIP lists the complete package set of our run.

## 2. Base model and adapter (one-time, needs network)

```bash
huggingface-cli download Qwen/Qwen3-0.6B --revision c1899de289a04d12100db370d81485cdf75e47ca \
  --local-dir $HOME/models/Qwen3-0.6B
mkdir -p $HOME/adapter-v2 && unzip MP3_adapter_v2.zip -d $HOME/adapter-v2   # the 2 adapter files
SRC=/path/to/unzipped/MP3_source_v2                                          # this ZIP
```

## 3. Prediction and scoring (offline)

```bash
export MP3_BASE_MODEL=$HOME/models/Qwen3-0.6B
export MP3_ADAPTER_DIR=$HOME/adapter-v2
export MP3_LLM_LOG=$PWD/outputs/llm_completions.jsonl    # every completion is logged here
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=4
mkdir -p outputs
PYTHONPATH="$SRC/submission" taskset -c 0-3 python -m mp3_sql.predict --split test \
  --method "$SRC/submission/rule_agent.py" --checkpoint "$SRC/submission/config.json" \
  --workers 1 --output outputs/test.json
python -m mp3_sql.score --split test --predictions outputs/test.json --output outputs/test-score.json
```

Expected result: `"correct": 192, "n": 240, "accuracy": 80.0`. Decoding is greedy, so the run is deterministic. The predictions match `outputs/test.json` in this ZIP apart from the `prediction_seconds` field; `outputs/reproduction.json` records our own clean-room rerun from the release ZIPs (made when this version was still labelled v3; same code, configuration and adapter).
Use `--split validation` for a quick check (about 30 s; expected 112 / 120).

## 4. No-LLM variant (ablation; 180 s / 2 GiB route)

```bash
PYTHONPATH="$SRC/submission" python -m mp3_sql.predict --split test \
  --method "$SRC/submission/rule_agent.py" --checkpoint "$SRC/submission/config_no_llm.json" \
  --output outputs/test-no-llm.json
```

This needs neither torch nor the model. It was not run on test, by our test-use protocol (REPORT.pdf §2).

## 5. Training the adapter (optional, GPU)

The scripts are in `dev/llm/`:
1. `make_sft.py v2-nollm all` builds the 1,143 SFT examples from train only. It needs dev run outputs of v2 with the LLM switched off on train/validation, which are made with `dev/eval.py --name v2-nollm --method submission/rule_agent.py --checkpoint submission/config_no_llm.json`.
2. `train_lora.py --name full-r16 --data train_all.jsonl` trains the adapter (CUDA torch 2.7.1+cu126).
3. `export_adapter.py <checkpoint>/epoch2 <dir>` writes and verifies the 2-file adapter.

The hyper-parameters and logs are in `dev/llm/training_log_full-r16.json`.
