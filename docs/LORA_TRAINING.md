# LoRA / QLoRA training — runbook

Trainer: `scripts/training/train_lora.py`
Config: `configs/training/sft_lora.yaml`
Requirements: `requirements-lora.txt`
Base profiles: `configs/base_model_candidates.yaml` (`lora_bases:` section)

## What this is

A generalized LoRA/QLoRA SFT trainer. It fine-tunes a pretrained Hugging
Face causal LM on the "us" corpus so the model learns our facts, decisions,
voice, and work. The first target is the ping-server base,
`meta-llama/Llama-3.2-1B-Instruct`, but **the pipeline generalizes to any
model**: `--model` takes any Hugging Face model id, and the tokenizer load,
the model load, the LoRA target-module detection, and the run manifest all
use that value. Nothing in the trainer hardcodes Llama 3.2 1B.

Stack: TRL `SFTTrainer` + PEFT + bitsandbytes (QLoRA) + transformers +
accelerate + datasets. Standard and auditable — no Unsloth.

## The hard rule: no external datasets in training, ever

Gary, 2026-11-07: *"without pollution of external datasets in the actual
training ever."*

- Training data is **only** the dataset passed explicitly via `--dataset`
  (default `datasets/lucid_corpus/lucid_corpus.jsonl`, the Lucid corpus —
  Track A, the only track; Gary, 2026-11-08: Track B, the private "us"
  model, is OFF, do not train a private Gary model).
- The trainer **never scans `datasets/`** and **refuses** any `--dataset`
  path inside `datasets/acquired/` (GSM8K, The Stack). It exits non-zero
  with a clear error if you try.
- GSM8K stays **evaluation-only**. The Stack stays **held** (license review).
- Evaluation is offloaded to the continuous live running system (Gary,
  2026-11-07: *"hence why we suggest and offload test in a continuous live
  running system"*): the fine-tune is judged by the Gate v2 benchmark first,
  then served as an option and A/B-tested against the stock 1B on the same
  prompts in real use. No external test data is ever mixed into training.

## Config defaults (and why max_seq differs from the old placeholder)

From `configs/training/sft_lora.yaml`:

| Setting | Value | Notes |
|---|---|---|
| LoRA rank / alpha / dropout | 64 / 128 / 0.05 | As in the original scaffold |
| Learning rate | 2e-4 | Cosine schedule, warmup 0.03 |
| Epochs | 2 | SFT standard is 1–3 |
| Micro batch × grad accum | 1 × 32 | Effective batch **32** |
| **max_seq** | **2048** | **Changed from the old 8192 placeholder**: 8192-token context is heavy on a free T4; 2048 is the realistic first-run setting for "us" SFT data. Override with `--max-seq` (or by editing the config) once the first run is proven. |
| QLoRA | on by default | 4-bit NF4, double quant, bf16 compute — ~2.5 GB VRAM, fits a free T4. `--no-qlora` for 16-bit LoRA (~3.5 GB). |
| Gradient checkpointing | on | `use_reentrant=False` for PEFT compatibility |

Every run writes `run_manifest.json` into its output directory: model,
dataset path + SHA-256 + row count, resolved config values, output dir,
timestamp, run id, git HEAD. That is the Gate v2 run record.

## How `--model` generalizes (where the model id flows)

1. **CLI** — `--model <any HF id>` (default
   `meta-llama/Llama-3.2-1B-Instruct`).
2. **Tokenizer** — `AutoTokenizer.from_pretrained(args.model)`; the chat
   template is used when the tokenizer has one, otherwise a plain
   Instruction/Response format. Pad token falls back to EOS.
3. **Model** — `AutoModelForCausalLM.from_pretrained(args.model, ...)` with
   the QLoRA `BitsAndBytesConfig` (or bf16/fp32 when `--no-qlora`).
4. **LoRA targets** — detected from the loaded model's own modules
   (`q/k/v/o/gate/up/down_proj`, `c_attn/c_proj/c_fc`, …). A Llama gets
   its projection set; a GPT-2-style model gets `c_attn`/`c_proj`; no
   architecture is assumed.
5. **Manifest** — records the exact `--model` value, so a run is always
   traceable to its base.

Proof on this VM (no GPU): `--dry-run` was run with the default 1B model
and with `--model sshleifer/tiny-gpt2`; the tiny model resolved its own
tokenizer and a 1-step smoke training run wrote a checkpoint + adapter
(see Verification below). The 1B tokenizer could not be resolved here —
it is gated (see Blockers).

## Dataset schema

Rows are JSONL in the repo seed schema:

```json
{"id": "...", "source_repo": "...", "capability": "...", "domain": "...",
 "prompt": "...", "target": "...", "tags": [...],
 "promotion_lane": "candidate_v2_only", "notes": "..."}
```

The loader also tolerates the older `{input, target}` shape (dicts or
strings, as in `datasets/distillation_sft/seed_records.jsonl` and as
`collect_sft_corpus` does): dict `input` `{task, context}` and dict
`target` `{analysis, confidence}` are coerced to text. Rows missing a
prompt or a target are skipped and counted in the manifest.

## Running on a free Colab T4 (the real 1B run)

### 0. Blockers — Gary's steps, before anything else works

1. **Hugging Face account + Llama Community License.** The Llama 3.2 1B
   weights are gated: a HF account must accept the Llama Community License
   terms, then `huggingface-cli login` with that account's token in the
   Colab session. Without this, the download fails with 401. **Gary's
   call: whose HF account, and accept the license.**
2. **Colab sign-in.** A Google account + Colab session (T4 GPU runtime:
   Runtime → Change runtime type → T4 GPU). No account exists yet on
   Gary's behalf; he signs in, the prepared commands below do the rest.
3. **Drive for checkpoints.** Colab sessions are ephemeral (12 h cap,
   90-min idle timeout). Mount Drive first so checkpoints survive.

### 1. Set up (one Colab cell)

```python
# Mount Drive (checkpoints survive the session)
from google.colab import drive
drive.mount('/content/drive')

# Clone the repo (or upload it) and install the stack.
# Colab preinstalls CUDA torch — do NOT reinstall torch.
!git clone https://github.com/GareBear99/ARC-Neuron-LLMBuilder.git  # or your fork/path
%cd ARC-Neuron-LLMBuilder
!pip install -q -r requirements-lora.txt

# Log in to Hugging Face (gated Llama weights — needs Gary's account +
# license acceptance, see Blockers above)
!huggingface-cli login
```

### 2. Validate first — dry run (no weights, no GPU needed)

```bash
python scripts/training/train_lora.py --dry-run
# Expect: {"ok": true, "mode": "dry_run", "model": "meta-llama/Llama-3.2-1B-Instruct",
#          "dataset": {"rows_usable": 3674, ...}, ...}
# Non-zero exit + a clear ERROR means fix the setup before training.
```

### 3. Train run 1 (T4, ~10–30 min for the 3,674-row corpus)

```bash
python scripts/training/train_lora.py \
  --output-dir /content/drive/MyDrive/llmbuilder-lora/run1
```

Defaults are the first-run settings: QLoRA 4-bit, r=64, alpha=128,
lr 2e-4, 2 epochs, max_seq 2048, effective batch 32. The adapter +
tokenizer land in the output dir on Drive, with `run_manifest.json`
next to them.

Useful variations:

```bash
# Longer context once run 1 is proven
python scripts/training/train_lora.py --max-seq 4096 --output-dir /content/drive/MyDrive/llmbuilder-lora/run2

# 16-bit LoRA instead of QLoRA
python scripts/training/train_lora.py --no-qlora --output-dir /content/drive/MyDrive/llmbuilder-lora/run3

# A different base model — the pipeline generalizes
python scripts/training/train_lora.py --model meta-llama/Llama-3.2-3B-Instruct \
  --output-dir /content/drive/MyDrive/llmbuilder-lora/run-3b
```

### 4. Export the adapter

The output dir already contains the PEFT adapter (`adapter_model.safetensors`
+ `adapter_config.json`) and the tokenizer. To merge it into full weights
for GGUF export, use the repo's existing path (`scripts/export_gguf.sh` /
`gguf_io`, see `docs/TRAINING_STACK_AND_GGUF_PATH.md`) — merging is a
follow-up step, not part of this trainer.

### 5. Evaluate + gate (not training — other workers own this)

1. Benchmark the fine-tune on the 168-task suite; check all 10 protected
   floors (Gate v2). **Do not compare against v10's 0.9237** until the
   stock 1B has been run through the same benchmark — that is the true
   neural baseline.
2. A/B vs the stock 1B on the same prompts (knowledge of us, voice, work
   questions), in the live running system.
3. Gate v2 decision: promote to candidate, or iterate (more data /
   different rank / more epochs). No promotion without a measured
   improvement and no floor breach.

## Local verification (this VM, no GPU)

```bash
python3 -m venv .venv-lora
.venv-lora/bin/pip install --index-url https://download.pytorch.org/whl/cpu torch
.venv-lora/bin/pip install -r requirements-lora.txt

# Import chain
.venv-lora/bin/python -c "import torch, transformers, peft, trl, datasets, accelerate, bitsandbytes"

# Dry run against the real Lucid corpus (default --dataset)
.venv-lora/bin/python scripts/training/train_lora.py --dry-run

# Generalization proof: a different --model resolves that model, not the 1B
.venv-lora/bin/python scripts/training/train_lora.py --dry-run --model sshleifer/tiny-gpt2

# 1-step smoke training on the tiny CPU model (proves the loop end to end)
.venv-lora/bin/python scripts/training/train_lora.py --model sshleifer/tiny-gpt2 \
  --dataset datasets/distillation_sft/seed_records.jsonl --smoke-test --no-qlora \
  --grad-accum 1 --output-dir /tmp/lora-smoke-test
```

## Verification results — 2026-11-07 (this VM, no GPU)

> Historical note (Gary, 2026-11-08): this section records verification
> run 2026-11-07 against the "us" corpus, before Gary corrected the plan
> to Track A only (Lucid corpus). The trainer default is now
> `datasets/lucid_corpus/lucid_corpus.jsonl`. The results below are kept
> as a record of what was verified then; re-run the dry run against the
> Lucid corpus before the first real training run.

All run on this VM (Python 3.12.3, 4 CPUs, ~660 MB RAM free, no GPU).
The `datasets/us_corpus/` corpus **did exist** by verification time
(3,674 rows, built by the corpus worker), so the dry run verified against
the real us corpus — the `seed_records.jsonl` fallback was not needed
except for the tiny-model smoke test.

- **Install:** `requirements-lora.txt` installed cleanly into `.venv-lora/`
  (torch 2.15.0+cpu installed first from the PyTorch CPU index, then the
  requirements file — pip confirmed torch 2.15.0+cpu satisfies
  `torch>=2.6.0`, so no CUDA torch was pulled). Resolved versions:
  trl 1.17.1, peft 0.21.2, transformers 5.22.2, accelerate 1.15.0,
  datasets 5.1.0, bitsandbytes 0.50.2, pyyaml 6.0.3, sentencepiece 0.2.3,
  tokenizers 0.23.3, huggingface_hub 2.4.0. Pins verified mutually
  compatible by this install (no resolver conflicts).
- **Import chain:** `torch, transformers, peft, trl, datasets, accelerate,
  bitsandbytes` all import cleanly on CPU. One non-fatal warning:
  bitsandbytes reports `Failed to load CPU gemm_4bit_forward from
  kernels-community: No module named 'kernels'` — the optional CPU 4-bit
  kernel is absent; QLoRA on a GPU does not use that path.
- **Dataset loader:** `us_corpus.jsonl` → 3,674/3,674 rows usable,
  0 skipped, SHA-256
  `a68f111fbac29143ff6c1ccd4821929a2efd32de8a51cb548edde3f11c324c49`.
  `seed_records.jsonl` (old `{input: dict, target: dict}` shape) → 20/20
  usable — dict coercion works.
- **Guard:** `--dataset datasets/acquired/gsm8k/gsm8k.jsonl` → REFUSED,
  exit 2. Missing dataset → clear error, exit 2.
- **`--dry-run` (default 1B model):** exit 2 — **gated**: `401 Client
  Error` on `meta-llama/Llama-3.2-1B-Instruct`. The 1B tokenizer/weights
  need a HF account that accepted the Llama Community License. This is
  the known blocker for the real run, not a trainer bug.
- **`--dry-run --model sshleifer/tiny-gpt2` (generalization proof):**
  exit 0. Resolved **GPT2Tokenizer, vocab 50257** — the tiny model, not
  the 1B. Dataset 3,674 rows, config r=64/alpha=128/lr 2e-4/epochs 2/
  max_seq 2048/effective batch 32/QLoRA on. Manifest written with the
  model id, dataset SHA-256, and git HEAD.
- **Smoke test** (`--model sshleifer/tiny-gpt2 --smoke-test --no-qlora`,
  seed_records, 8 rows): **exit 0**. LoRA targets auto-detected as
  `['c_attn', 'c_proj', 'c_fc']` (GPT-2 style — proves detection is
  model-agnostic, not Llama-hardcoded). Trainable params 4,096 / 106,810
  (3.83%). 1 step, train_loss **10.68**, grad_norm 0.025. Adapter written
  (`adapter_model.safetensors` + `adapter_config.json`, r=64, alpha=128,
  base `sshleifer/tiny-gpt2`) + tokenizer + `checkpoint-1/` (optimizer,
  scheduler, trainer state) + `run_manifest.json`. Loss 10.68 on step 1
  is the expected starting loss for an untrained tiny model; a 1-step run
  proves the loop end to end, not learning.
- **Static:** `python -m py_compile` OK, `--help` works, both YAML
  configs load.
- **Bugs found by verification and fixed in the trainer:** (1) TRL 1.17.1
  rejects a pre-wrapped `PeftModel` passed with `peft_config` — the
  trainer now passes the base model + `peft_config` and lets SFTTrainer
  wrap it. (2) `torch_dtype` is deprecated in transformers 5.x — now
  uses `dtype`. (3) TRL 1.x `SFTConfig` has no `warmup_ratio` — now uses
  `warmup_steps: 20` (~3% of a ~625-step first run).
