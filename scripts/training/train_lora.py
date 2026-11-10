#!/usr/bin/env python3
"""Generalized LoRA / QLoRA SFT trainer for LLMBuilder.

Trains ANY Hugging Face causal-LM as the base — the model is taken from
``--model`` and flows through every stage (tokenizer load, model load, LoRA
target-module detection, run manifest). Nothing in this script hardcodes a
particular base model. The default is the ping-server base,
``meta-llama/Llama-3.2-1B-Instruct``, but any ``--model`` works, e.g.::

    python scripts/training/train_lora.py --model sshleifer/tiny-gpt2 \\
        --dataset datasets/distillation_sft/seed_records.jsonl --smoke-test

NO-EXTERNAL-DATA RULE (Gary, 2026-11-07 — hard rule, overrides any plan):
the actual training data is ONLY the dataset given explicitly via
``--dataset`` (the Lucid corpus, ``datasets/lucid_corpus/`` — Track A, the
only track; Gary, 2026-11-08: Track B, the private "us" model, is OFF, do
not train a private Gary model). This script NEVER
scans ``datasets/``, NEVER reads ``datasets/acquired/`` (GSM8K, The Stack),
and refuses any ``--dataset`` path inside ``datasets/acquired/``. GSM8K stays
evaluation-only; The Stack stays held. Evaluation is offloaded to the
benchmark (Gate v2) and to live A/B against the stock base model — not to
data mixed into training.

Stack: TRL SFTTrainer + PEFT + bitsandbytes (QLoRA) + transformers +
accelerate + datasets. Standard, auditable — no Unsloth.

Defaults come from ``configs/training/sft_lora.yaml`` (r=64, alpha=128,
lr 2e-4, epochs 2). Two deliberate deviations from that file's placeholder
values, recorded here and in the config:
  * max_seq 2048, not 8192: 8192-token context is heavy on a free T4;
    2048 is the realistic first-run setting for Lucid SFT data. Override
    with ``--max-seq`` (or by editing the config).
  * grad_accum 32 (effective batch 32 = micro 1 x accum 32), not 16.

Modes:
  * ``--dry-run``  — validate config + dataset, resolve the tokenizer
    (downloads it if available), write the run manifest. Loads NO model
    weights, needs NO GPU. Exit 0 on a valid setup, non-zero with a clear
    error otherwise.
  * ``--smoke-test`` — a 1-step training run (``--max-steps 1``, at most 8
    rows unless ``--limit``/``--max-steps`` are given explicitly) that proves
    the training loop end to end and writes a checkpoint + adapter.
  * full run — QLoRA by default (4-bit NF4, ~2.5 GB VRAM, fits a free T4);
    ``--no-qlora`` for 16-bit LoRA instead.

Every run writes a Gate v2 run manifest (``run_manifest.json``) into the
output directory: model, dataset path + SHA-256 + row count, resolved
config values, output dir, timestamp, run id.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_MODEL = "meta-llama/Llama-3.2-1B-Instruct"
DEFAULT_DATASET = REPO_ROOT / "datasets" / "lucid_corpus" / "lucid_corpus.jsonl"
DEFAULT_CONFIG = REPO_ROOT / "configs" / "training" / "sft_lora.yaml"
DEFAULT_OUTPUT_BASE = REPO_ROOT / "exports" / "lora"

# Built-in fallbacks if the config file omits a key. These match
# configs/training/sft_lora.yaml; the config file is the source of truth.
DEFAULTS = {
    "lora_r": 64,
    "lora_alpha": 128,
    "lora_dropout": 0.05,
    "learning_rate": 2e-4,
    "epochs": 2,
    "max_seq": 2048,          # NOT the yaml's old 8192: T4 first-run default.
    "micro_batch": 1,
    "grad_accum": 32,         # effective batch 32 = 1 x 32
}

# Any dataset path containing one of these segments is refused outright.
FORBIDDEN_DATASET_SEGMENTS = ("datasets/acquired", "acquired/gsm8k", "acquired/the-stack")

# Candidate LoRA target modules, in preference order. Detection keeps only
# the ones actually present in the loaded model, so this works for Llama
# (q/k/v/o/gate/up/down_proj), GPT-2-style models (c_attn/c_proj/c_fc),
# and other causal LMs without hardcoding an architecture.
TARGET_MODULE_CANDIDATES = [
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
    "c_attn", "c_proj", "c_fc",
    "query", "key", "value", "dense",
]


class TrainerError(Exception):
    """A clear, user-facing failure (bad config, bad dataset, gated model)."""


# ── dataset handling ────────────────────────────────────────────────────────

def _stringify(value) -> str:
    """Coerce a prompt/target value to plain text.

    Handles the repo seed schema (``prompt``/``target`` strings), the older
    ``{input, target}`` shape where both are dicts (e.g. seed_records.jsonl:
    ``input`` = {task, context}, ``target`` = {analysis, confidence}), and
    generic dict/list values.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        # Prefer human-meaningful keys over a raw JSON dump.
        parts: list[str] = []
        for key in ("task", "question", "instruction", "context"):
            if isinstance(value.get(key), str) and value[key].strip():
                parts.append(value[key].strip())
        for key in ("analysis", "answer", "response", "text", "content", "output"):
            if isinstance(value.get(key), str) and value[key].strip():
                parts.append(value[key].strip())
        if parts:
            return "\n".join(parts)
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "\n".join(_stringify(v) for v in value if _stringify(v))
    return str(value).strip()


def prompt_target(record: dict) -> tuple[str, str] | None:
    """Extract (prompt, target) from one seed-schema record, or None to skip."""
    if not isinstance(record, dict):
        return None
    if isinstance(record.get("messages"), list):
        user = [m for m in record["messages"]
                if isinstance(m, dict) and m.get("role") == "user"]
        asst = [m for m in record["messages"]
                if isinstance(m, dict) and m.get("role") == "assistant"]
        prompt = "\n".join(_stringify(m.get("content")) for m in user)
        target = "\n".join(_stringify(m.get("content")) for m in asst)
    else:
        prompt = _stringify(
            record.get("prompt") or record.get("instruction") or record.get("input") or ""
        )
        target = _stringify(
            record.get("target") or record.get("response") or record.get("output") or ""
        )
    prompt, target = prompt.strip(), target.strip()
    if not prompt or not target:
        return None
    return prompt, target


def check_dataset_path(path: Path) -> Path:
    """Resolve the dataset path and enforce the no-external-data rule."""
    resolved = path.expanduser().resolve()
    posix = resolved.as_posix()
    for segment in FORBIDDEN_DATASET_SEGMENTS:
        if segment in posix:
            raise TrainerError(
                f"REFUSED dataset path {resolved}: it is inside an acquired/external "
                f"dataset directory ({segment}). Training data must be the explicitly "
                f"passed Lucid corpus only (Track A — GSM8K is evaluation-only, The Stack is held). "
                f"Pass --dataset datasets/lucid_corpus/lucid_corpus.jsonl (or another "
                f"explicit non-acquired .jsonl file)."
            )
    if not resolved.exists():
        raise TrainerError(
            f"Dataset not found: {resolved}\n"
            f"  (If datasets/lucid_corpus/ does not exist yet, the corpus worker has "
            f"not delivered it. For a wiring test use "
            f"datasets/distillation_sft/seed_records.jsonl explicitly.)"
        )
    if resolved.suffix.lower() != ".jsonl":
        raise TrainerError(f"Dataset must be a .jsonl file, got: {resolved}")
    return resolved


def load_dataset_rows(path: Path, limit: int | None = None) -> tuple[list[dict], dict]:
    """Load + validate a .jsonl SFT file. Returns (rows, stats)."""
    rows: list[dict] = []
    skipped = 0
    total_lines = 0
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            if not line.strip():
                continue
            total_lines += 1
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise TrainerError(
                    f"Dataset {path} line {lineno} is not valid JSON: {exc}"
                ) from exc
            pair = prompt_target(record)
            if pair is None:
                skipped += 1
                continue
            prompt, target = pair
            rows.append({
                "id": record.get("id", f"row-{lineno}"),
                "prompt": prompt,
                "target": target,
            })
            if limit is not None and len(rows) >= limit:
                break
    if not rows:
        raise TrainerError(
            f"Dataset {path} yielded 0 usable prompt/target rows "
            f"({total_lines} lines read, {skipped} skipped for missing prompt/target). "
            f"Rows must have prompt/target (or input/target) fields."
        )
    stats = {
        "path": str(path),
        "sha256": sha256_file(path),
        "lines_read": total_lines,
        "rows_usable": len(rows),
        "rows_skipped": skipped,
        "mean_prompt_chars": sum(len(r["prompt"]) for r in rows) // len(rows),
        "mean_target_chars": sum(len(r["target"]) for r in rows) // len(rows),
    }
    return rows, stats


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ── config ──────────────────────────────────────────────────────────────────

def load_config(path: Path) -> dict:
    if not path.exists():
        raise TrainerError(f"Config file not found: {path}")
    try:
        import yaml
    except ImportError as exc:
        raise TrainerError(
            "PyYAML is required to read the config (pip install -r requirements-lora.txt)"
        ) from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise TrainerError(f"Config {path} did not parse as a YAML mapping.")
    return data


def resolve_settings(args: argparse.Namespace, cfg: dict) -> dict:
    """Merge config file + CLI overrides. CLI wins; config wins over built-ins.

    NOTE: this trainer reads ONLY the ``trainer:`` section of the config.
    It deliberately does NOT read any ``dataset_inputs`` list — the dataset
    is always the explicit ``--dataset`` argument (no-external-data rule).
    """
    trainer = cfg.get("trainer") or {}
    if not isinstance(trainer, dict):
        raise TrainerError(f"Config {args.config}: 'trainer:' section must be a mapping.")
    settings = {
        "model": args.model,
        "dataset": str(args.dataset),
        "config": str(args.config),
        "qlora": not args.no_qlora,
        "lora_r": args.lora_r if args.lora_r is not None else int(trainer.get("rank", DEFAULTS["lora_r"])),
        "lora_alpha": args.lora_alpha if args.lora_alpha is not None else int(trainer.get("alpha", DEFAULTS["lora_alpha"])),
        "lora_dropout": float(trainer.get("dropout", DEFAULTS["lora_dropout"])),
        "learning_rate": args.lr if args.lr is not None else float(trainer.get("learning_rate", DEFAULTS["learning_rate"])),
        "epochs": args.epochs if args.epochs is not None else float(trainer.get("epochs", DEFAULTS["epochs"])),
        "max_seq": args.max_seq if args.max_seq is not None else int(trainer.get("max_seq_length", DEFAULTS["max_seq"])),
        "micro_batch": args.micro_batch if args.micro_batch is not None else int(trainer.get("micro_batch_size", DEFAULTS["micro_batch"])),
        "grad_accum": args.grad_accum if args.grad_accum is not None else int(trainer.get("grad_accumulation", DEFAULTS["grad_accum"])),
        "max_steps": args.max_steps,
        "limit": args.limit,
        "output_dir": str(args.output_dir) if args.output_dir else None,
        "run_id": args.run_id or None,
    }
    if settings["lora_r"] <= 0 or settings["lora_alpha"] <= 0:
        raise TrainerError("LoRA rank and alpha must be positive.")
    if settings["learning_rate"] <= 0:
        raise TrainerError("Learning rate must be positive.")
    if settings["max_seq"] < 128:
        raise TrainerError("max_seq must be >= 128.")
    settings["effective_batch"] = settings["micro_batch"] * settings["grad_accum"]
    return settings


def model_slug(model_id: str) -> str:
    return model_id.strip().replace("/", "__").replace("\\", "_")


def default_run_id(model_id: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    return f"lora-{model_slug(model_id)}-{stamp}"


# ── tokenizer / formatting ──────────────────────────────────────────────────

def resolve_tokenizer(model_id: str):
    """Load ONLY the tokenizer (no model weights). Used by --dry-run."""
    from transformers import AutoTokenizer

    try:
        tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=False)
    except Exception as exc:
        raise TrainerError(
            f"Could not resolve tokenizer for model {model_id!r}: {exc}\n"
            f"  If this is a gated model (e.g. meta-llama/Llama-3.2-1B-Instruct), "
            f"the base weights download needs a Hugging Face account that has "
            f"accepted the Llama Community License, plus `huggingface-cli login`. "
            f"That is a blocker for the real 1B run, not a trainer bug — verify "
            f"with a public model instead, e.g. --model sshleifer/tiny-gpt2."
        ) from exc
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    return tokenizer


def format_example(prompt: str, target: str, tokenizer) -> str:
    """Render one SFT pair as training text.

    Uses the tokenizer's chat template when one exists (instruct models),
    otherwise a plain Instruction/Response block. Always appends EOS.
    """
    eos = tokenizer.eos_token or ""
    chat_template = getattr(tokenizer, "chat_template", None)
    if chat_template:
        try:
            text = tokenizer.apply_chat_template(
                [
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": target},
                ],
                tokenize=False,
                add_generation_prompt=False,
            )
            if text and text.strip():
                return text if text.endswith(eos) else text + eos
        except Exception:
            pass  # fall through to the plain format
    text = f"### Instruction:\n{prompt}\n\n### Response:\n{target}"
    return text + eos if eos else text


def build_text_dataset(rows: list[dict], tokenizer):
    """Build a HF Dataset with a single 'text' column for SFTTrainer."""
    from datasets import Dataset

    texts = [format_example(r["prompt"], r["target"], tokenizer) for r in rows]
    return Dataset.from_dict({"text": texts})


# ── manifest ────────────────────────────────────────────────────────────────

def write_manifest(output_dir: Path, settings: dict, dataset_stats: dict,
                   extra: dict | None = None) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        import subprocess
        git_head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
            capture_output=True, text=True, timeout=10,
        ).stdout.strip() or None
    except Exception:
        git_head = None
    manifest = {
        "schema": "llmbuilder-lora-run-manifest/v1",
        "run_id": settings["run_id"],
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "model": settings["model"],
        "dataset": {
            "path": dataset_stats["path"],
            "sha256": dataset_stats["sha256"],
            "rows_usable": dataset_stats["rows_usable"],
            "rows_skipped": dataset_stats["rows_skipped"],
        },
        "config": {
            "config_file": settings["config"],
            "lora_r": settings["lora_r"],
            "lora_alpha": settings["lora_alpha"],
            "lora_dropout": settings["lora_dropout"],
            "learning_rate": settings["learning_rate"],
            "epochs": settings["epochs"],
            "max_seq": settings["max_seq"],
            "micro_batch": settings["micro_batch"],
            "grad_accum": settings["grad_accum"],
            "effective_batch": settings["effective_batch"],
            "qlora": settings["qlora"],
            "max_steps": settings["max_steps"],
        },
        "output_dir": str(output_dir),
        "git_head": git_head,
        "data_policy": (
            "Training data is ONLY the explicit --dataset file. No external "
            "datasets (GSM8K evaluation-only, The Stack held) were read, scanned, "
            "or mixed into this run."
        ),
    }
    if extra:
        manifest.update(extra)
    path = output_dir / "run_manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


# ── dry run ─────────────────────────────────────────────────────────────────

def cmd_dry_run(args: argparse.Namespace, settings: dict, dataset_path: Path) -> int:
    rows, stats = load_dataset_rows(dataset_path, limit=settings["limit"])
    tokenizer = resolve_tokenizer(settings["model"])
    sample = format_example(rows[0]["prompt"], rows[0]["target"], tokenizer)
    output_dir = Path(settings["output_dir"]) if settings["output_dir"] else (
        DEFAULT_OUTPUT_BASE / settings["run_id"]
    )
    manifest_path = write_manifest(
        output_dir, settings, stats,
        extra={"mode": "dry_run", "tokenizer_resolved": True,
               "sample_text_preview": sample[:400]},
    )
    print(json.dumps({
        "ok": True,
        "mode": "dry_run",
        "run_id": settings["run_id"],
        "model": settings["model"],
        "tokenizer": tokenizer.__class__.__name__,
        "vocab_size": len(tokenizer),
        "dataset": stats,
        "config": {k: settings[k] for k in (
            "lora_r", "lora_alpha", "lora_dropout", "learning_rate", "epochs",
            "max_seq", "micro_batch", "grad_accum", "effective_batch", "qlora")},
        "manifest": str(manifest_path),
    }, indent=2))
    return 0


# ── training ────────────────────────────────────────────────────────────────

def _filtered_kwargs(cls_or_fn, kwargs: dict) -> dict:
    """Keep only kwargs the target callable actually accepts (TRL API drift)."""
    try:
        params = inspect.signature(cls_or_fn).parameters
    except (TypeError, ValueError):
        return kwargs
    return {k: v for k, v in kwargs.items() if k in params}


def detect_target_modules(model) -> list[str]:
    names = {name for name, _ in model.named_modules()}
    found: list[str] = []
    for cand in TARGET_MODULE_CANDIDATES:
        if any(n == cand or n.endswith("." + cand) for n in names):
            found.append(cand)
    if not found:
        print("[train_lora] WARNING: no known projection modules detected; "
              "falling back to ['q_proj', 'v_proj'].", file=sys.stderr)
        return ["q_proj", "v_proj"]
    return found


def cmd_train(args: argparse.Namespace, settings: dict, dataset_path: Path) -> int:
    import torch
    from transformers import AutoModelForCausalLM

    rows, stats = load_dataset_rows(dataset_path, limit=settings["limit"])
    tokenizer = resolve_tokenizer(settings["model"])
    train_ds = build_text_dataset(rows, tokenizer)

    has_cuda = torch.cuda.is_available()
    print(f"[train_lora] model={settings['model']} rows={len(rows)} "
          f"cuda={has_cuda} qlora={settings['qlora']}")
    if not has_cuda:
        print("[train_lora] WARNING: no GPU — CPU training is only for smoke "
              "tests on tiny models, not for a real 1B run.", file=sys.stderr)

    quant_config = None
    if settings["qlora"]:
        from transformers import BitsAndBytesConfig
        quant_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )

    dtype = torch.bfloat16 if has_cuda else torch.float32
    model_kwargs: dict = {
        "trust_remote_code": False,
        "dtype": dtype,  # `torch_dtype` is deprecated in transformers 5.x
        "attn_implementation": "sdpa" if has_cuda else "eager",
    }
    if quant_config is not None:
        model_kwargs["quantization_config"] = quant_config
    if has_cuda:
        model_kwargs["device_map"] = "auto"

    model = AutoModelForCausalLM.from_pretrained(settings["model"], **model_kwargs)
    model.config.use_cache = False

    if settings["qlora"]:
        from peft import prepare_model_for_kbit_training
        model = prepare_model_for_kbit_training(
            model, use_gradient_checkpointing=True
        )

    from peft import LoraConfig

    target_modules = detect_target_modules(model)
    print(f"[train_lora] LoRA target modules: {target_modules}")
    peft_config = LoraConfig(
        r=settings["lora_r"],
        lora_alpha=settings["lora_alpha"],
        lora_dropout=settings["lora_dropout"],
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=target_modules,
    )
    # NOTE: do NOT wrap the model with get_peft_model() here — TRL 1.x
    # rejects a PeftModel passed together with a peft_config. The base
    # model + peft_config go to SFTTrainer, which does the wrapping.

    from trl import SFTConfig, SFTTrainer

    output_dir = Path(settings["output_dir"]) if settings["output_dir"] else (
        DEFAULT_OUTPUT_BASE / settings["run_id"]
    )
    sft_kwargs: dict = {
        "output_dir": str(output_dir),
        "per_device_train_batch_size": settings["micro_batch"],
        "gradient_accumulation_steps": settings["grad_accum"],
        "num_train_epochs": settings["epochs"],
        "learning_rate": settings["learning_rate"],
        "lr_scheduler_type": "cosine",
        # TRL 1.x SFTConfig has warmup_steps, not warmup_ratio. 20 steps is
        # ~3% of a ~625-step first run (3,674 rows, eff. batch 32, 2 epochs).
        "warmup_steps": 20,
        "logging_steps": 1 if settings["max_steps"] else 10,
        "save_steps": 500,
        "save_strategy": "steps",
        "bf16": has_cuda,
        "gradient_checkpointing": True,
        "gradient_checkpointing_kwargs": {"use_reentrant": False},
        "optim": "paged_adamw_8bit" if settings["qlora"] else "adamw_torch",
        "max_length": settings["max_seq"],
        "packing": False,
        "report_to": [],
        "seed": 42,
        "dataloader_num_workers": 0,
        "remove_unused_columns": False,
        "dataset_text_field": "text",
    }
    if settings["max_steps"]:
        sft_kwargs["max_steps"] = settings["max_steps"]
    sft_config = SFTConfig(**_filtered_kwargs(SFTConfig, sft_kwargs))

    trainer_kwargs: dict = {
        "model": model,
        "args": sft_config,
        "train_dataset": train_ds,
        "peft_config": peft_config,
        "processing_class": tokenizer,
    }
    trainer = SFTTrainer(**_filtered_kwargs(SFTTrainer.__init__, trainer_kwargs))
    trainer.model.print_trainable_parameters()

    result = trainer.train()
    train_loss = None
    for entry in reversed(trainer.state.log_history):
        if "loss" in entry:
            train_loss = entry["loss"]
            break

    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    manifest_path = write_manifest(
        output_dir, settings, stats,
        extra={"mode": "train", "target_modules": target_modules,
               "train_loss": train_loss,
               "global_step": trainer.state.global_step},
    )
    print(json.dumps({
        "ok": True,
        "mode": "train",
        "run_id": settings["run_id"],
        "model": settings["model"],
        "output_dir": str(output_dir),
        "train_loss": train_loss,
        "global_step": trainer.state.global_step,
        "manifest": str(manifest_path),
    }, indent=2))
    return 0


# ── CLI ─────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Generalized LoRA/QLoRA SFT trainer (any HF causal-LM base).",
        epilog="Training data is ONLY the explicit --dataset file. External "
               "datasets (datasets/acquired/) are never read and are refused.",
    )
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help="Any Hugging Face causal-LM id (default: %(default)s). "
                        "The tokenizer, model, and manifest all use this value.")
    p.add_argument("--dataset", default=str(DEFAULT_DATASET),
                   help="Explicit .jsonl SFT file (default: %(default)s). "
                        "Never scans datasets/; paths under datasets/acquired/ "
                        "are refused.")
    p.add_argument("--output-dir", default=None,
                   help="Output dir (default: exports/lora/<run-id>).")
    p.add_argument("--config", default=str(DEFAULT_CONFIG),
                   help="YAML config (default: %(default)s).")
    p.add_argument("--run-id", default=None,
                   help="Run id (default: lora-<model-slug>-<UTC timestamp>).")
    p.add_argument("--max-seq", type=int, default=None,
                   help="Max sequence length (default: config value, 2048 for "
                        "the T4 first run — NOT the old 8192 placeholder).")
    p.add_argument("--max-steps", type=int, default=None,
                   help="Cap training steps (e.g. 1 for a smoke test).")
    p.add_argument("--epochs", type=float, default=None)
    p.add_argument("--lr", type=float, default=None)
    p.add_argument("--micro-batch", type=int, default=None)
    p.add_argument("--grad-accum", type=int, default=None)
    p.add_argument("--lora-r", type=int, default=None)
    p.add_argument("--lora-alpha", type=int, default=None)
    p.add_argument("--limit", type=int, default=None,
                   help="Use at most N dataset rows (smoke tests).")
    p.add_argument("--no-qlora", action="store_true",
                   help="16-bit LoRA instead of 4-bit QLoRA.")
    p.add_argument("--dry-run", action="store_true",
                   help="Validate config + dataset and resolve the tokenizer "
                        "only. No model weights, no GPU.")
    p.add_argument("--smoke-test", action="store_true",
                   help="1-step training run on a few rows (sets --max-steps 1 "
                        "and --limit 8 unless given explicitly).")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.smoke_test:
        if args.max_steps is None:
            args.max_steps = 1
        if args.limit is None:
            args.limit = 8
    try:
        dataset_path = check_dataset_path(Path(args.dataset))
        cfg = load_config(Path(args.config))
        settings = resolve_settings(args, cfg)
        if settings["run_id"] is None:
            settings["run_id"] = default_run_id(settings["model"])
        if args.dry_run:
            return cmd_dry_run(args, settings, dataset_path)
        return cmd_train(args, settings, dataset_path)
    except TrainerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except ImportError as exc:
        print(f"ERROR: missing dependency: {exc}\n"
              f"  pip install -r requirements-lora.txt", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
