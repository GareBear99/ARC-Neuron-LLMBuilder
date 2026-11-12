#!/usr/bin/env python3
"""Modal adaptation of the Track A LoRA training path — DRAFT, NOT RUN.

Runs the SAME 152-step QLoRA fine-tune of meta-llama/Llama-3.2-1B-Instruct
on the 2,426-row Lucid corpus as the Colab notebook
(llmbuilder-colab-train.ipynb, cells 7–8), but as Modal functions on an L4
GPU instead of a Colab T4. The training code itself is unchanged:
``scripts/training/train_lora.py`` + ``configs/training/sft_lora_modal.yaml``
(the Modal config is identical to sft_lora.yaml except save_steps 25).

Layout mirrors the Colab run exactly, with Drive replaced by a Modal Volume:
    Colab: /content/drive/MyDrive/llmbuilder-lora/run1
    Modal: /llmbuilder/run1            (Volume "llmbuilder-lora")
    Colab: .../run1-merged
    Modal: /llmbuilder/run1-merged

DRAFT STATUS (2026-11-11): code prep only. Nothing here has been run,
deployed, or validated against a live Modal account. Gary's go-ahead is
needed for: the HF_TOKEN Modal Secret, the GPU choice, the save_steps value,
and the first `modal run`. See MODAL_TRAINING_PLAN.md.

Usage (from the repo root, after Gary approves — DO NOT run before then):
    modal volume create llmbuilder-lora --version=2
    modal secret create huggingface HF_TOKEN=<hf-token>   # Gary's HF token, never in code
    modal run scripts/training/modal_train.py             # full 152-step run
    modal run scripts/training/modal_train.py --resume-from /llmbuilder/run1/checkpoint-25
    modal run scripts/training/modal_train.py --smoke-test  # 1-step GPU smoke test
    modal run scripts/training/modal_train.py --merge-only   # merge adapter -> full bf16
    modal volume get llmbuilder-lora run1-merged <local-dir>  # download results
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import modal

# ── constants ───────────────────────────────────────────────────────────────

APP_NAME = "llmbuilder-lora"
VOLUME_NAME = "llmbuilder-lora"
SECRET_NAME = "huggingface"  # must contain HF_TOKEN (created by Gary, see plan)
VOLUME_MOUNT = "/llmbuilder"
REMOTE_ROOT = "/root/llmbuilder"  # repo snapshot inside the image
MODEL_ID = "meta-llama/Llama-3.2-1B-Instruct"
RUN_DIR = f"{VOLUME_MOUNT}/run1"  # same layout as Colab's .../llmbuilder-lora/run1
MERGED_DIR = f"{VOLUME_MOUNT}/run1-merged"

# GPU choice: L4 (Ada Lovelace, sm89, 24 GB) — see MODAL_TRAINING_PLAN.md for
# the cost reasoning. sm80+ means train_lora.py's sm75 fp32 patch no-ops.
GPU = "L4"
CPU_COUNT = 2
MEMORY_MB = 16384
# T4 did the full run in ~10–30 min; L4 is ~2–3x faster on bf16. 1 h is
# generous headroom for download + train + merge; Modal's default function
# timeout is only 300 s, so this MUST be set explicitly.
TIMEOUT_SECONDS = 3600

REPO_ROOT = Path(__file__).resolve().parents[2]

# ── image ───────────────────────────────────────────────────────────────────
# Pins mirror requirements-lora.txt exactly (same versions verified
# mutually compatible 2026-11-07), PLUS torch: the requirements file
# deliberately does NOT pin torch (Colab preinstalls its CUDA build), but a
# Modal image has no torch preinstalled, so it is added here as the same
# torch>=2.6,<3 range the requirements file documents.
# pip installs torch's CUDA wheel by default, which is what we want.
# The repo snapshot is added file-by-file (NOT the whole repo: the checkout
# is 2.1 GB, mostly local venvs) and laid out so train_lora.py's REPO_ROOT
# (= parents[2] of scripts/training/train_lora.py) resolves to
# /root/llmbuilder, keeping its default --dataset/--config paths working.
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        # torch is a RANGE, not a pinned patch: requirements-lora.txt says
        # torch>=2.6,<3 (bitsandbytes 0.50.2 needs >=2.4,<3; trl 1.17.1
        # needs >=2.6). pip installs torch's CUDA wheel by default.
        "torch>=2.6,<3",
        "trl==1.17.1",
        "peft==0.21.2",
        "transformers==5.22.2",
        "accelerate==1.15.0",
        "datasets==5.1.0",
        "bitsandbytes==0.50.2",
        "torchao>=0.16.0",
        "pyyaml==6.0.3",
        "sentencepiece==0.2.3",
        "tokenizers==0.23.3",
    )
    .add_local_dir(REPO_ROOT / "scripts" / "training", f"{REMOTE_ROOT}/scripts/training")
    .add_local_dir(REPO_ROOT / "configs" / "training", f"{REMOTE_ROOT}/configs/training")
    .add_local_file(
        REPO_ROOT / "datasets" / "lucid_corpus" / "lucid_corpus.jsonl",
        f"{REMOTE_ROOT}/datasets/lucid_corpus/lucid_corpus.jsonl",
    )
)

app = modal.App(APP_NAME)

volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True, version=2)
hf_secret = modal.Secret.from_name(SECRET_NAME)


def _run_trainer(argv: list[str], hf_home: str) -> int:
    """Run train_lora.py as a subprocess inside the container.

    A subprocess (rather than importing the trainer) keeps the Modal wrapper
    decoupled from the trainer's imports and matches the Colab notebook,
    which also shells out to the script. HF_HOME points at the Volume so
    the ~2.5 GB base-model download is cached across runs instead of
    re-downloaded every time.
    """
    env = {
        "HF_HOME": hf_home,
        # HF_TOKEN comes from the Modal Secret (env-injected, never in code).
        "PYTHONUNBUFFERED": "1",
    }
    print("[modal_train] running:", " ".join(argv), flush=True)
    proc = subprocess.run(
        [sys.executable, f"{REMOTE_ROOT}/scripts/training/train_lora.py", *argv],
        env={**os.environ, **env},
        check=False,
    )
    return proc.returncode


@app.function(
    image=image,
    gpu=GPU,
    cpu=CPU_COUNT,
    memory=MEMORY_MB,
    timeout=TIMEOUT_SECONDS,
    volumes={VOLUME_MOUNT: volume},
    secrets=[hf_secret],
)
def train(run_id: str | None = None, resume_from: str | None = None,
          save_steps: int | None = None, smoke_test: bool = False) -> dict:
    """Full Track A LoRA run (or a 1-step smoke test) on the Modal L4.

    Writes the adapter + run_manifest.json + checkpoints to /llmbuilder/run1
    on the Volume — the same layout as the Colab Drive run1. Volume commits
    happen in the background while the function runs, plus a final commit on
    container shutdown, so checkpoints survive even if the (preemptible)
    function is interrupted mid-run; pass the last checkpoint back as
    resume_from to continue.
    """
    import torch

    major, minor = torch.cuda.get_device_capability()
    print(f"[modal_train] GPU compute capability {major}.{minor} "
          f"(L4 is sm89 — the sm75 fp32 patch in train_lora.py no-ops, "
          f"bf16 fused-LM-head path stays on)", flush=True)
    argv = [
        "--model", MODEL_ID,
        "--dataset", f"{REMOTE_ROOT}/datasets/lucid_corpus/lucid_corpus.jsonl",
        "--config", f"{REMOTE_ROOT}/configs/training/sft_lora_modal.yaml",
        "--output-dir", RUN_DIR,
    ]
    if run_id:
        argv += ["--run-id", run_id]
    if save_steps:
        argv += ["--save-steps", str(save_steps)]
    if resume_from:
        argv += ["--resume-from-checkpoint", resume_from]
    if smoke_test:
        argv += ["--smoke-test"]
    rc = _run_trainer(argv, hf_home=f"{VOLUME_MOUNT}/hf-cache")
    volume.commit()
    if rc != 0:
        raise RuntimeError(f"train_lora.py exited with code {rc}")
    return {"ok": True, "output_dir": RUN_DIR, "run_id": run_id}


@app.function(
    image=image,
    gpu=GPU,
    cpu=CPU_COUNT,
    memory=MEMORY_MB,
    timeout=TIMEOUT_SECONDS,
    volumes={VOLUME_MOUNT: volume},
    secrets=[hf_secret],
)
def merge() -> dict:
    """Merge the run1 adapter into full bf16 weights (notebook cell 12).

    Mirrors llmbuilder-colab-train.ipynb cell 12 exactly, including the two
    stability fixes proven 2026-11-10 (vocab_size 128257; tokenizer_class
    LlamaTokenizerFast) so the merged model stays GGUF-convertible.
    Output: /llmbuilder/run1-merged on the Volume.
    """
    import json

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    base = AutoModelForCausalLM.from_pretrained(
        MODEL_ID, dtype=torch.bfloat16, device_map="auto", trust_remote_code=False
    )
    model = PeftModel.from_pretrained(base, RUN_DIR)
    merged = model.merge_and_unload()
    merged.save_pretrained(MERGED_DIR, safe_serialization=True)
    tok = AutoTokenizer.from_pretrained(RUN_DIR)
    tok.save_pretrained(MERGED_DIR)

    cfg_path = Path(MERGED_DIR) / "config.json"
    cfg = json.loads(cfg_path.read_text())
    cfg["vocab_size"] = 128257
    cfg_path.write_text(json.dumps(cfg, indent=2))
    tc_path = Path(MERGED_DIR) / "tokenizer_config.json"
    tc = json.loads(tc_path.read_text())
    tc["tokenizer_class"] = "LlamaTokenizerFast"
    tc_path.write_text(json.dumps(tc, indent=2))
    print(f"[modal_train] merged model saved to {MERGED_DIR}", flush=True)
    volume.commit()
    return {"ok": True, "merged_dir": MERGED_DIR}


@app.local_entrypoint()
def main(run_id: str | None = None, resume_from: str | None = None,
         save_steps: int | None = None, smoke_test: bool = False,
         merge_only: bool = False, train_and_merge: bool = False):
    """Local entrypoint: `modal run scripts/training/modal_train.py [flags]`.

    Default: train only. --merge-only skips training and merges the adapter
    already on the Volume. --train-and-merge runs train, then merge.
    """
    if merge_only:
        print(merge.remote())
        return
    print(train.remote(
        run_id=run_id, resume_from=resume_from,
        save_steps=save_steps, smoke_test=smoke_test,
    ))
    if train_and_merge:
        print(merge.remote())
