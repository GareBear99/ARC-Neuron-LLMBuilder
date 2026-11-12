# Modal training plan — Track A LoRA on Modal (DRAFT, 2026-11-11)

Status: **code prep only**. Nothing here has been run, deployed, or validated
against a live Modal account. No GPU work, no Modal runs, no commits.
Gary's go-ahead is needed before any `modal run` (see "Needs Gary").

## Why Modal, why now

- The Colab CPU training is stalled at step 0/152 (~2.5 h, no pace), and its
  `save_steps=500` means no intermediate checkpoint exists to switch from.
- Modal signup is DONE (account gdoman99, Starter, $1.00 of $30/mo used).
- The Nov 10 Colab T4 run proved the recipe (final loss 0.810375, 152 steps,
  45,088,768 trainable params). This plan replays that recipe on a Modal L4.

## What was built (VM repo only, uncommitted draft)

| File | Change |
|---|---|
| `scripts/training/modal_train.py` (new) | Modal app: `train()` + `merge()` functions + `local_entrypoint`. L4 GPU, Volume `llmbuilder-lora`, Secret `huggingface`. |
| `configs/training/sft_lora_modal.yaml` (new) | Same as `sft_lora.yaml` except `save_steps: 25`. |
| `scripts/training/train_lora.py` (edited, +35/−3) | `save_steps` configurable (config `trainer.save_steps` / CLI `--save-steps`, default 500 = proven Colab value); new CLI `--resume-from-checkpoint`; both recorded in `run_manifest.json`. |
| `exports/lora/modal-draft-dryrun/run_manifest.json` | Validation artifact from the dry-run below (untracked). |

## GPU + cost reasoning

- **GPU: L4** (`gpu="L4"`). Ada Lovelace, sm89, 24 GB VRAM. sm80+ means
  `train_lora.py`'s sm75 fp32 patch (`_patch_fused_lm_head_for_sm75`) is a
  verified no-op — it returns early when `major >= 8`, and L4 is 8.9, so the
  fast bf16 fused-LM-head path stays on. QLoRA 1B needs ~2.5 GB VRAM; 24 GB
  is ample headroom. T4 was NOT chosen: it is sm75 (the patched path) and
  slower. A100 ($2.10–2.50/hr) is overkill for a 1B QLoRA run.
- **Rates** (Modal's published per-second rate card, as captured by
  third-party trackers Oct–Nov 2026 — the live modal.com/pricing text fetch
  did not render the numeric GPU table, so confirm L4 in the dashboard
  before the first run): L4 $0.000222/s ≈ **$0.80/hr**; CPU $0.0000131/core/s;
  memory $0.00000222/GiB/s.
- **Estimated run cost**: 2 CPU + 16 GiB + L4 ≈ $1.02/hr all-in. T4 did the
  full run in ~10–30 min; L4 is ~2–3x faster on bf16, so expect ~10–20 min
  of training + ~2–3 min first-run model download → **~$0.35–0.55 for the
  first full run**. A full 1-hour worst case is ~$1.02. Well inside the
  ~$29 of remaining Starter credits.
- **Do NOT pin a region**: Modal's pricing page lists region selection at
  1.15–1.75x base prices. The app sets no region.
- **Preemption**: Modal Functions are preemptible by default (per Modal's
  pricing FAQ; interruptions are rare). Non-preemptible costs 3x — NOT
  used. Instead, `save_steps: 25` + `--resume-from-checkpoint` covers an
  interruption: checkpoints at 25/50/75/100/125/150 + final 152.
- **Storage/egress**: Volumes include up to 1 TiB free on Starter; 1 TiB/mo
  free egress. Run artifacts are ~4 GB total — negligible.

## How data / model / checkpoints flow

- **Dataset**: the 2,426-row Lucid corpus (`datasets/lucid_corpus/lucid_corpus.jsonl`,
  2.08 MB, SHA-256 in the manifest) is baked into the image with
  `add_local_file` — a fixed snapshot, versioned with the image. The
  trainer's no-external-data rule still applies: `--dataset` is explicit,
  `datasets/acquired/` is refused. The whole repo is NOT baked in (the
  checkout is 2.1 GB, mostly local venvs) — only `scripts/training/`,
  `configs/training/`, and the corpus file.
- **Model**: `meta-llama/Llama-3.2-1B-Instruct` downloads from the HF Hub at
  runtime inside the container, authenticated by `HF_TOKEN` from the Modal
  Secret `huggingface` (env-injected, never in code or files). `HF_HOME` is
  set to `/llmbuilder/hf-cache` on the Volume, so the ~2.5 GB download is
  cached across runs instead of re-downloaded.
- **Checkpoints / outputs**: everything lands on Volume `llmbuilder-lora`
  (v2) at `/llmbuilder/run1` — adapter, `run_manifest.json`, and
  `checkpoint-25/50/...` — the same layout as Colab's
  `MyDrive/llmbuilder-lora/run1`. Modal commits Volumes in the background
  during the run and on shutdown; the app also calls `volume.commit()`
  explicitly. `merge()` writes `/llmbuilder/run1-merged` (full bf16 model).
- **Download results**: `modal volume get llmbuilder-lora run1-merged <dir>`
  (frontend download caps at 16 MB, so the CLI is the route for the ~2.5 GB
  merged model). GGUF conversion stays a later step, as in the notebook.
- **Hyperparameters**: identical to the Nov 10 T4 run (r=64, alpha=128,
  dropout 0.05, lr 2e-4 cosine, epochs 2, max_seq 2048, micro 1 × accum 32,
  QLoRA NF4 double-quant, warmup 20, seed 42). The ONE deliberate change is
  `save_steps` 500 → 25 (see config comment for why).
- **Timeout**: 3600 s. Modal's default function timeout is 300 s, which
  would kill a training run — this MUST stay set.
- **Progress**: no ping key is configured on Modal, so the trainer's progress
  callback stays off (zero behavior change); logs stream via `modal run`.

## Validation done (VM only, no GPU, no Modal)

- `py_compile` clean on both Python files; YAML parses (`save_steps: 25`).
- CPU dry-run with the Modal config + tiny-gpt2 (`.venv-lora`):
  `train_lora.py --model sshleifer/tiny-gpt2 --config
  configs/training/sft_lora_modal.yaml --run-id modal-draft-dryrun --dry-run`
  → exit 0, 2,426 rows usable / 0 skipped, manifest records
  `save_steps: 25`, `resume_from_checkpoint: null`, all Nov 10 hyperparameters.
- NOT validated (cannot be, without a live run): the Modal app file itself
  (`modal` is not installed in this VM, so it is syntax-checked only, not
  import-tested), the image build, the L4 runtime, the HF gated-model
  download via Secret, or resume. The first `--smoke-test` run is the
  validation for all of that — see below.

## Needs Gary (in order)

1. **HF_TOKEN Modal Secret** — create it (dashboard, or
   `modal secret create huggingface HF_TOKEN=<token>`). The token must be
   from an HF account that accepted the Llama Community License (gated
   model). The Colab secret's token is the same one. Never paste it into
   code or files.
2. **Payment method on file?** — Modal's GPU guide says "Using a GPU
   requires having a valid payment method on file", and the dashboard notes
   adding one "unlocks the remaining $29". The first GPU run may fail until
   a card is added. Adding it is Gary's call; the run itself should still
   be covered by the free credits.
3. **GPU confirmation** — L4 at ~$0.80/hr, ~$0.35–0.55 for the run. Confirm
   the L4 rate in the dashboard (the pricing-page text fetch didn't render
   the GPU table).
4. **save_steps = 25** — the one deliberate deviation from the Nov 10 run.
   Also Gary's call: whether the Colab config should get 25 too (the
   currently-running CPU training reads the hardcoded 500, so changing the
   file would NOT affect it — it would only matter on a restart).
5. **Deploy / run go-ahead** — first a 1-step `--smoke-test`, then the full run.

## Exact commands (when Gary approves — do NOT run before then)

```bash
cd ~/workspace/ARC-Neuron-LLMBuilder   # repo root; the app resolves paths from its own location
modal volume create llmbuilder-lora --version=2
modal secret create huggingface HF_TOKEN=<garys-hf-token>   # or via dashboard
# 1-step GPU smoke test (validates image, secret, GPU, trainer end to end):
modal run scripts/training/modal_train.py --smoke-test
# Full 152-step run (~$0.35–0.55):
modal run scripts/training/modal_train.py
# If interrupted, resume from the last checkpoint on the Volume:
modal run scripts/training/modal_train.py --resume-from /llmbuilder/run1/checkpoint-25
# Merge adapter -> full bf16 model (notebook cell 12, incl. vocab/tokenizer fixes):
modal run scripts/training/modal_train.py --merge-only
# Or train + merge in one invocation:
modal run scripts/training/modal_train.py --train-and-merge
# Download results:
modal volume get llmbuilder-lora run1-merged ./run1-merged
modal volume get llmbuilder-lora run1/run_manifest.json .
```

## Known gaps / blockers in the current trainer (found while porting)

- **`save_steps` was hardcoded 500** — fixed in this draft (configurable,
  Modal default 25). With 152 total steps, 500 meant no intermediate
  checkpoint at all, which is also why the CPU run has nothing to resume from.
- **No resume flag existed** — fixed in this draft (`--resume-from-checkpoint`,
  passed to `trainer.train(resume_from_checkpoint=...)`).
- **Manifest has no git HEAD on Modal** — `write_manifest` runs
  `git rev-parse HEAD` in the repo root; the image has no `.git`, so
  `git_head` will be `null` on Modal runs. Everything else (model, dataset
  SHA, rows, config) is still recorded. Acceptable; the image snapshot is
  the version record.
- **First-run image build downloads torch + the stack** (~10 min of CPU-billed
  build time, roughly $0.10–0.20, cached afterwards). Not a blocker.
