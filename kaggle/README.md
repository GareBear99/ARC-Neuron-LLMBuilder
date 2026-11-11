# Kaggle training package — LLMBuilder LoRA re-train

Prepared locally 2026-11-11. **Ready to upload the moment a Kaggle API token exists.**
No Kaggle account, token, upload, or run has happened — this is the package only.

## The GPU pool — the architecture (Gary, 2026-11-11)

GPUs are interchangeable **handoff workers** in a pool, occupying **open
parallel slots**. The CPU runs **in parallel underneath**, holding the run
up the whole time as the safety net — it does **not** occupy a GPU slot.
The parallel slots stay open, so a GPU worker can jump into one when
needed. Colab T4, Kaggle GPU, any GPU added later — all the same kind of
worker in the same pool.

**The hierarchy:**

1. **A GPU runs normally** (Colab T4 right now).
2. **If it dies**, the CPU is already holding the live run in parallel,
   and the next GPU worker (Kaggle) jumps into an open slot and takes
   the **live state straight from the CPU** — no checkpoint involved in
   that step.
3. **ONLY if worse comes to worst** — the live hold is gone too — does
   the **checkpoint** step in as the fallback. Checkpoints are the
   **last resort**, not the handoff.

Kaggle is the GPU worker that jumps in after a GPU death. When the Colab
T4 (or any GPU) dies, the CPU catches the run and holds it alive, and
then Kaggle's GPU jumps in to take over the GPU work — from the CPU's
live state, not a fresh start, not a checkpoint. The CPU holds the run
until Kaggle's GPU is in; then the GPU work continues there.

## What the live state is

At any step N, the complete training state needed to continue exactly
from step N — nothing re-run, nothing skipped:

- LoRA adapter weights (the trainable parameters)
- Optimizer state (paged_adamw_8bit moments)
- LR scheduler state (cosine schedule position)
- RNG state (python / numpy / torch — so data order and dropout continue)
- Trainer state: global step N, epoch, log history, total steps (152)
- Data position: derived from the step + the restored RNG (the trainer
  skips already-consumed batches in the resumed epoch)

That is the same *content* as a checkpoint directory. The difference is
**provenance and freshness**: the live state is the CPU's in-memory copy,
current to the exact step where the GPU died; a disk checkpoint is a
snapshot from the last `save_steps` boundary, stale by up to 24 steps.
That is why the live state is the handoff and the checkpoint is only the
last resort.

## The live-state bundle (the GPU-death handoff unit)

When a GPU dies, the CPU hold serializes its live state into a portable
bundle with `tools/export_state.py --kind live-state`:

- Zip: `llmbuilder-live-state-<STEP>.zip`
- Inside: a `live-state/` dir holding the adapter weights,
  `adapter_config.json`, `optimizer.pt`, `scheduler.pt`,
  `rng_state.pth`, `trainer_state.json`, `training_args.bin` (when
  present), plus the marker `live_state.json` (schema
  `llmbuilder-live-state/v1`: run id, source worker, step, epoch,
  total steps, model, dataset sha256, created timestamp, and the sha256
  of every file in the bundle).
- The receiving worker verifies the bundle before trusting it: the
  marker step must match `trainer_state.json` global_step, and every
  file hash must match. A bundle that fails verification is discarded.

Transfer to Kaggle: the bundle is uploaded as a Kaggle dataset
(`llmbuilder-live-state`) and attached to the notebook. The notebook's
state-intake cell finds it (zip or extracted dir), verifies it, and
reports the live step. The continue-from-live-state execution — the
loader that picks the GPU work up from the live state — is **wired**
(notebook cell 9, 2026-11-11): the live-state dir has exactly the
checkpoint content the trainer restores, and the pinned transformers
5.22.2 `_load_from_checkpoint` checks only for weight files in the dir
(no `checkpoint-*` name check), so the notebook resumes from the
live-state dir via the trainer's existing `--resume-from-checkpoint`
— no `train_lora.py` edit. The run continues from the live state
(steps LIVE_STEP+1-152). This is NOT a checkpoint resume: the state
came from the CPU holder, not from a disk checkpoint.

## The checkpoint (last resort only)

A periodic disk snapshot (`checkpoint-<N>` in the run output dir,
written every `save_steps`). The `save_steps: 25` fix stands, so those
fallback checkpoints land at 25/50/75/100/125/150 + final 152.

Packaged the same way, with `tools/export_state.py --kind checkpoint`:
zip `llmbuilder-checkpoint-<STEP>.zip`, marker `handoff.json` (schema
`llmbuilder-checkpoint-handoff/v1`). The notebook resumes from it with
`--resume-from-checkpoint` — the trainer restores adapter, optimizer,
scheduler, RNG and step count, and runs only the remaining steps.
Verified against the pinned transformers 5.22.2 Trainer source
(`_load_from_checkpoint` loads the PEFT adapter via `load_adapter`;
`_load_optimizer_and_scheduler` restores optimizer + scheduler;
`TrainerState.load_from_json` restores the step count; `_run_epoch`
skips already-trained batches).

Use it ONLY when the live hold is gone too (worst case), or for a
cold-start worker that was never in the parallel run. It is the safety
net under the safety net — not the handoff. Do not present
checkpoint-resume as the way a GPU jumps in after a death.

## What it is

The same Track A LoRA re-train as the proven Nov 10 Colab T4 run,
packaged for Kaggle's free GPU (2× T4 16 GB, 12-hour sessions,
~30 GPU-hours/week, 20 GB output). QLoRA 4-bit NF4, r=64, alpha=128,
lr 2e-4, 2 epochs, max_seq 2048, micro 1 × accum 32, **152 total steps**,
corpus 2,426 rows (Lucid knowledge only — no external data, ever).
`save_steps: 25`, so fallback checkpoints land at steps
25/50/75/100/125/150 + final 152 in `/kaggle/working/run1`.

Why Kaggle: Modal's GPU (L4 and T4) refuses without a payment method on
file (`InvalidError('Please add a payment method to use L4/T4 GPU
functions.')`) and Gary will NOT add a card. Colab's T4 is available
again (checked ~12:18 PST Nov 11) and is the parallel path; Kaggle is
the first no-card alternative and the GPU worker that jumps in after a
GPU death.

## Layout

```
kaggle-llmbuilder/
  README.md                  — this file
  tools/
    export_state.py          — pool state export: package a state dir into
                               a portable bundle (--kind live-state for the
                               GPU-death handoff, --kind checkpoint for the
                               last-resort fallback)
  dataset/                   — Kaggle Dataset payload (upload as one dataset)
    dataset-metadata.json    — id: YOUR-KAGGLE-USERNAME/llmbuilder-lora-run
    scripts/training/train_lora.py
    configs/training/sft_lora.yaml
    configs/training/sft_lora_kaggle.yaml   — the run config (save_steps 25)
    requirements-lora.txt    — pinned training stack (torch NOT pinned: Kaggle
                               preinstalls the CUDA build, same rule as Colab)
    datasets/lucid_corpus/lucid_corpus.jsonl   — 2,426 rows, sha256
                               dc5cdeaf0890691e794a075a7a9bdb80a7e1a4460826fa48c8764f432b322cb8
    datasets/lucid_corpus/manifest.json
    datasets/lucid_corpus/README.md
  notebook/
    llmbuilder-lora-train.ipynb   — 11 cells: env check, copy+verify, pip
                               install, HF token from Kaggle Secret, dry-run,
                               smoke test, STATE INTAKE (live state / last-
                               resort checkpoint), mode-aware FULL RUN,
                               post-run verify + zip
    kernel-metadata.json     — id: YOUR-KAGGLE-USERNAME/llmbuilder-lora-train,
                               enable_gpu + enable_internet, attaches the dataset
```

The repo-relative layout is kept inside the dataset on purpose:
`train_lora.py` resolves `REPO_ROOT` as parents[2] of its own path, so its
default `--dataset` / `--config` paths work. The notebook still passes all
paths explicitly. `/kaggle/input` is read-only, so the notebook copies the
dataset into `/kaggle/working/llmbuilder` before training.

## What is still blocked

**The Kaggle API token (Gary's step).** No Kaggle account or token exists
yet (checked memory, Secure Vault, and `/Users/gary/projects/` ~12:17 PST
Nov 11 — nothing). Gary is signing up in his Brave now (Google,
gdoman99@gmail.com — same pattern as the Modal signup); the token gets
saved in `/Users/gary/projects/` like Modal's was. Do NOT paste the token
in chat.

Also needed at run time (in the Kaggle notebook UI, not in any file):
- A Kaggle Secret named **`HF_TOKEN`** (Add-ons → Secrets) whose value is
  the Hugging Face token for the account that accepted the Llama 3.2 1B
  license. The notebook reads it from the secret and only ever prints the
  HF username.
- GPU enabled: notebook Settings → Accelerator → **GPU T4**. (Kaggle GPU
  access needs phone verification on the account.)
- Internet enabled (in `kernel-metadata.json` already) — needed to
  download the base weights from Hugging Face.

**The CPU live hold (separate work, not this package).** The live-state
handoff needs a CPU process holding the live run in parallel — that is
the continuity layer, a separate coordinator's job, and it does not
exist yet. Until it does, no live state can be produced, and the
continue-from-live-state execution cannot be wired or validated. See
"What is wired / not wired".

## How to upload + run (once the token exists)

```bash
# 0. Put Gary's kaggle.json at ~/.kaggle/kaggle.json and lock it down:
#    mkdir -p ~/.kaggle && cp /Users/gary/projects/kaggle.json ~/.kaggle/kaggle.json
#    chmod 600 ~/.kaggle/kaggle.json
#    pip install kaggle

# 1. Replace the username placeholder in BOTH metadata files:
#    dataset/dataset-metadata.json and notebook/kernel-metadata.json
#    YOUR-KAGGLE-USERNAME -> Gary's Kaggle username

# 2. Upload the dataset (code + corpus, ~2.3 MB):
cd ~/workspace/kaggle-llmbuilder
kaggle datasets create -p dataset/

# 3. Push the notebook:
kaggle kernels push -p notebook/

# 4. In the Kaggle web UI: open the notebook, add the HF_TOKEN secret,
#    confirm Accelerator = GPU T4, then Run All.
#    - Fresh start (no state attached): full 152-step run, ~67 min.
#    - Last-resort checkpoint attached: resumes from that step, runs only
#      the remaining steps. See "Handoff procedures" below.
```

Web-UI alternative (no CLI): Kaggle → Create → New Notebook → upload
`notebook/llmbuilder-lora-train.ipynb`; Datasets → New Dataset → upload
the `dataset/` contents; attach the dataset to the notebook, add the
HF_TOKEN secret, set Accelerator to GPU T4, Run All.

## Handoff procedures

### A. GPU death — Kaggle jumps in from the CPU's live state (PRIMARY)

This is the handoff. It needs the CPU live hold to exist (it does not
yet — see "What is wired / not wired").

1. A GPU dies. The CPU is already holding the live run in parallel.
2. The CPU hold serializes its live state at the death moment:
   `python3 tools/export_state.py --kind live-state --source-dir <cpu-live-state-dir> --run-id <run-id> --source-worker cpu-hold --out llmbuilder-live-state-<STEP>.zip`
   (the tool refuses an incomplete state dir — it must contain adapter,
   optimizer, scheduler, RNG and trainer_state, or the bundle is not a
   lossless continuation).
3. Upload the bundle as a Kaggle dataset (`llmbuilder-live-state`) and
   attach it to the notebook (in the Kaggle UI, or by adding it to
   `dataset_sources` in `kernel-metadata.json` before pushing).
4. Run All. The state-intake cell finds the bundle, verifies it (marker
   step == trainer_state global_step, every file hash matches), and
   reports the live step. The GPU work then continues from that live
   state on Kaggle.
5. Verify the jump-in: the first training log after the intake shows a
   step greater than the live step (e.g. live step 50 → first log step
   51), and no step is re-run or skipped.

### B. Worst case — the live hold is gone too (LAST RESORT)

Only if the live state is unavailable (the CPU hold died with the GPU,
or the worker was never in the parallel run):

1. Find the latest fallback checkpoint in the run output dir
   (`run1/checkpoint-<N>`, highest N — the save_steps=25 fix means one
   lands every 25 steps).
2. Package it:
   `python3 tools/export_state.py --kind checkpoint --run-dir <run-dir> --run-id <run-id> --source-worker <worker> --out-dir <out-dir>`
   (picks the latest checkpoint; refuses an incomplete or mislabeled
   dir).
3. Upload the bundle as a Kaggle dataset (`llmbuilder-checkpoint`) and
   attach it to the notebook.
4. Run All. The state-intake cell finds the checkpoint, verifies it,
   and the run resumes from it with `--resume-from-checkpoint` — only
   the remaining steps run (e.g. from step 50: steps 51–152).
5. Verify the resume: the first training log shows a step greater than
   the checkpoint step, and the final adapter + manifest land in
   `/kaggle/working/run1`.

### C. Any other GPU worker (the general path)

The same procedure, with that worker's own upload path — the bundle
format and the marker verification are destination-agnostic. A worker
that joins the pool takes the live state from the CPU if it is jumping
in after a GPU death (procedure A), or the latest checkpoint if the live
hold is gone (procedure B). The checkpoint is never the handoff; it is
always the last resort.

## Expected outputs (in /kaggle/working, saved as notebook output)

- `/kaggle/working/run1/checkpoint-{25,50,75,100,125,150}` — adapter +
  optimizer state (~150–250 MB each, ~1.5 GB total)
- `/kaggle/working/run1/` — final adapter (`adapter_model.safetensors` +
  `adapter_config.json`), tokenizer, `run_manifest.json`
- `/kaggle/working/llmbuilder-lora-run1.zip` — final adapter + tokenizer +
  manifest only (download from the notebook Output tab)

## What is wired / not wired (honest status, 2026-11-11)

**Wired:**
- The checkpoint path (last resort): `save_steps: 25` in the run
  config, so fallback checkpoints land at 25/50/75/100/125/150. The
  trainer's `--resume-from-checkpoint` restores adapter, optimizer,
  scheduler, RNG and step count — verified against the pinned
  transformers 5.22.2 Trainer source, not assumed.
- The export tool (`tools/export_state.py`): packages a state dir into
  a verified portable bundle in both kinds, refuses incomplete or
  mislabeled state dirs. Tested on synthetic state dirs (both kinds
  export cleanly; incomplete and mislabeled dirs are refused).
- The notebook state-intake cell: detects + verifies a live-state
  bundle and a checkpoint bundle (zip or extracted dir), picks the
  highest step of each kind, and lets the live state win when both are
  attached. Tested on synthetic input (live 50 + checkpoint 25;
  tampered bundle rejected; empty input → fresh; checkpoint-only →
  last-resort mode).
- The notebook mode-aware run cell: fresh start, last-resort
  checkpoint resume, and the live-state jump-in — when live state is
  attached the notebook resumes from the live-state dir via the
  trainer's existing `--resume-from-checkpoint` (steps LIVE_STEP+1-152).
  Verified in simulation against a holder-produced bundle (intake
  accepts it, cell 9 resumes from it, no fresh run, no checkpoint
  fallback) and against the pinned transformers 5.22.2 source (no
  `checkpoint-*` name check in `_load_from_checkpoint`).
- The CPU live hold (`~/workspace/colab-training-checks/live_state_holder.py`):
  a VM-side service, SPSC ring in + triple-buffer latest live-state
  snapshot, STAGNANT (holds only, does not train). It adopts each new
  checkpoint, converts it into a verified live-state bundle
  (`llmbuilder-live-state/v1`), holds the latest in memory, and serves
  it to the next GPU. Inherent shutdown: when the job finishes it
  releases the hold and exits on its own — nothing left on. Verified
  on synthetic state dirs (adopt, hold advances, incomplete state
  refused, shutdown on step 152 and on JOB_DONE).
- The dual watch (`~/workspace/colab-training-checks/dual_watch.py`):
  monitors the Kaggle GPU worker AND the CPU holder in parallel, same
  cycle, one log row for both. Verdicts BOTH_RUNNING / GPU_AHEAD /
  HOLDER_STALE / GPU_DEAD / GPU_UNKNOWN / DONE — all verified.

**Not wired (still):**
- The end-to-end GPU-death jump-in on a LIVE run (Kaggle GPU dies →
  CPU holds → Kaggle jumps in from live state and finishes). The holder,
  the loader, and the dual watch are built and verified on synthetic
  state; the live-run proof is the swap test (run to checkpoint-25,
  stop, Kaggle jumps in from the holder's live state, proven by step
  100). Until that test passes on a live run, the jump-in is built but
  not yet proven live. The last-resort checkpoint resume (procedure B)
  IS runnable today and is the safety net underneath.

## Validation done locally (2026-11-11, no Kaggle account)

- Notebook JSON parses and validates with `nbformat` (11 cells); all
  code cells parse as Python.
- `train_lora.py` copy byte-identical to the repo file; `py_compile`
  clean; `--help` lists `--resume-from-checkpoint`.
- `sft_lora_kaggle.yaml` parses; `trainer.save_steps == 25`, rank 64,
  alpha 128, lr 2e-4, epochs 2, max_seq 2048.
- Corpus copy sha256 matches the manifest
  (`dc5cdeaf…b322cb8`) and row count is 2,426.
- Export tool: live-state export (step 50) and checkpoint export
  (step 50, explicit dir and `--run-dir` latest-pick) all exit 0 with
  correct bundles + markers; an incomplete state dir and a mislabeled
  checkpoint dir are both refused (exit 2, clear error).
- Intake cell (executed against synthetic `/kaggle/input` trees):
  live 50 (zip) + checkpoint 25 (dir) → live wins, both verified;
  tampered live-state bundle → rejected on hash mismatch; empty input
  → all None (fresh); checkpoint-only → last-resort mode at step 25.
- Resume mechanics verified against the pinned transformers 5.22.2
  Trainer source (downloaded wheel): `_load_from_checkpoint` loads
  the PEFT adapter via `load_adapter`; `_load_optimizer_and_scheduler`
  restores optimizer + scheduler; `TrainerState.load_from_json`
  restores the step count; `_run_epoch` skips already-trained batches.
  Crucially, `train(resume_from_checkpoint=<path>)` uses the path
  verbatim — there is NO `checkpoint-*` name check anywhere in the
  resume path, so a live-state dir (same content, different name) is
  a valid resume target. That is what lets the notebook resume from
  live state with no `train_lora.py` edit.
- Live-state loader (notebook cell 9, 2026-11-11): executed cells 8+9
  in simulation against a holder-produced live-state-25 bundle — the
  intake verifies it (MODE: LIVE STATE, step 25) and cell 9 calls the
  trainer with `--resume-from-checkpoint <live-state-dir>`,
  `--save-steps 25`, label "LIVE STATE jump-in (steps 26-152)". No
  RuntimeError, no fresh run, no checkpoint fallback.
- CPU live holder (`live_state_holder.py`, 2026-11-11): adopt /
  status / serve / watch all verified on synthetic state dirs — adopt
  holds step 25, an incomplete dir is refused (exit 2, hold stays at
  25), the hold advances to step 50, adopting step 152 releases the
  holder and exits on its own (JOB_DONE, nothing left on), and watch
  mode adopts checkpoint-25 then checkpoint-50 as they land and exits
  on its own when a JOB_DONE marker appears. The holder's bundle
  passes the notebook intake verification exactly.
- Dual watch (`dual_watch.py`, 2026-11-11): all six verdicts verified
  (GPU_UNKNOWN / BOTH_RUNNING / GPU_AHEAD / HOLDER_STALE / GPU_DEAD /
  DONE), including the HOLDER_STALE trigger on the 2nd consecutive
  GPU-ahead check and GPU_DEAD exiting 2.
- No secret value appears anywhere in this package (grep-checked for
  the HF token pattern and for `kaggle.json` contents — the notebook
  references the secret only by the name `HF_TOKEN`).
- NOT validated (needs the token + Kaggle, and for procedure A the CPU
  live hold): CLI auth, dataset upload, kernel push, GPU allocation,
  the actual training run, the live-state continue, the end-to-end
  GPU-death jump-in.
