#!/usr/bin/env python3
"""Pool state export — package a training state dir into a portable bundle.

The LLMBuilder GPU pool (Gary, 2026-11-11): GPUs are interchangeable
handoff workers occupying open parallel slots; the CPU runs in parallel
underneath holding the run up the whole time as the safety net (it does
NOT occupy a GPU slot). When a GPU dies, the next GPU worker jumps into
an open slot and takes over the GPU work.

This tool packages a training state dir into a portable bundle (a zip).
It has TWO kinds — they are different mechanisms, do not mix them:

* ``live-state`` — the CPU's LIVE hold at GPU-death time. Source = the
  CPU hold's live state dir (its in-memory training state, serialized at
  the death moment, current to the exact step where the GPU died).
  Marker = ``live_state.json``. Bundle name:
  ``llmbuilder-live-state-<STEP>.zip``.
  This is the GPU-DEATH handoff: CPU live hold -> next GPU worker
  (Kaggle jumps into an open slot and takes the live state straight
  from the CPU). NO checkpoint is involved in that step.

* ``checkpoint`` — a periodic disk snapshot (``checkpoint-<N>`` in the run
  output dir, written every ``save_steps``). Marker = ``handoff.json``.
  Bundle name: ``llmbuilder-checkpoint-<STEP>.zip``.
  This is for COLD-START workers ONLY — a worker that was never in the
  parallel run and joins fresh, resuming from the latest checkpoint
  (``--resume-from-checkpoint``). It is NOT the GPU-death mechanism.

What a bundle contains (both kinds — same content, different provenance):
the full state dir: LoRA adapter weights (``adapter_model.safetensors``),
``adapter_config.json``, optimizer state (``optimizer.pt``), scheduler
state (``scheduler.pt``), RNG state (``rng_state.pth``),
``trainer_state.json`` (global step, epoch, log history), and
``training_args.bin`` when present. Plus the marker json at the root of
the bundled dir, which records the step, run id, source worker, kind,
and the sha256 of every file in the bundle.

The marker is what the receiving worker verifies before it trusts the
bundle: step must match ``trainer_state.json`` global_step, and every
file hash must match. A bundle that fails verification is discarded —
never resume from an unverified bundle.

Usage (run on the machine that holds the state — the Mac, or a VM):

    # GPU death: the CPU hold serializes its live state to a dir, then:
    python3 tools/export_state.py --kind live-state \\
        --source-dir /path/to/cpu-live-state --run-id <run-id> \\
        --source-worker cpu-hold --out /path/to/llmbuilder-live-state-50.zip

    # Cold start: package the latest disk checkpoint:
    python3 tools/export_state.py --kind checkpoint \\
        --source-dir /path/to/run1/checkpoint-50 --run-id <run-id> \\
        --source-worker colab-t4 --out /path/to/llmbuilder-checkpoint-50.zip

    # Or let it find the latest checkpoint in a run dir:
    python3 tools/export_state.py --kind checkpoint \\
        --run-dir /path/to/run1 --run-id <run-id> \\
        --source-worker colab-t4 --out-dir /path/to/out

Exit 0 on success (prints a JSON summary); non-zero with a clear error
on any verification failure. No secrets are read, written, or printed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_LIVE_STATE = "llmbuilder-live-state/v1"
SCHEMA_HANDOFF = "llmbuilder-checkpoint-handoff/v1"

# Files a state dir MUST contain to be a resumable/continuable unit.
# Adapter weights: safetensors preferred, .bin accepted.
REQUIRED_FILES = (
    "adapter_config.json",
    "optimizer.pt",
    "scheduler.pt",
    "rng_state.pth",
    "trainer_state.json",
)
ADAPTER_WEIGHT_NAMES = ("adapter_model.safetensors", "adapter_model.bin")
# Nice-to-have, not required.
OPTIONAL_FILES = ("training_args.bin", "tokenizer_config.json")


class ExportError(Exception):
    """A clear, user-facing failure (bad state dir, verification failure)."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_latest_checkpoint(run_dir: Path) -> Path:
    """Pick the highest-step checkpoint-<N> dir in a run dir."""
    cands = []
    for p in run_dir.iterdir():
        if p.is_dir() and p.name.startswith("checkpoint-"):
            try:
                cands.append((int(p.name.split("-", 1)[1]), p))
            except (IndexError, ValueError):
                continue
    if not cands:
        raise ExportError(f"No checkpoint-<N> dir found in {run_dir}")
    cands.sort(key=lambda t: t[0])
    return cands[-1][1]


def verify_state_dir(source: Path, kind: str) -> dict:
    """Check the state dir has everything a worker needs; return its facts."""
    if not source.is_dir():
        raise ExportError(f"State dir is not a directory: {source}")
    missing = [f for f in REQUIRED_FILES if not (source / f).is_file()]
    if missing:
        raise ExportError(
            f"State dir {source} is INCOMPLETE — missing: {', '.join(missing)}. "
            "A bundle without optimizer/scheduler/RNG/trainer_state cannot "
            "continue a run losslessly; do not export it."
        )
    adapter = None
    for name in ADAPTER_WEIGHT_NAMES:
        if (source / name).is_file():
            adapter = name
            break
    if adapter is None:
        raise ExportError(
            f"State dir {source} has no adapter weights "
            f"({' or '.join(ADAPTER_WEIGHT_NAMES)}). Not a resumable state dir."
        )
    try:
        trainer_state = json.loads((source / "trainer_state.json").read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise ExportError(f"trainer_state.json unreadable in {source}: {exc}")
    step = trainer_state.get("global_step")
    if not isinstance(step, int) or step < 0:
        raise ExportError(
            f"trainer_state.json in {source} has no valid global_step "
            f"(got {step!r}). Cannot determine the step this state is at."
        )
    if kind == "checkpoint":
        # The dir name must agree with the step it claims.
        expect = f"checkpoint-{step}"
        if source.name != expect:
            raise ExportError(
                f"Checkpoint dir name {source.name!r} disagrees with "
                f"trainer_state.json global_step {step} (expected {expect!r}). "
                "Refusing to export a mislabeled checkpoint."
            )
    files = {}
    for name in sorted(p.name for p in source.iterdir() if p.is_file()):
        files[name] = sha256_file(source / name)
    return {
        "step": step,
        "epoch": trainer_state.get("epoch"),
        "max_steps": trainer_state.get("max_steps"),
        "adapter_weights": adapter,
        "files": files,
    }


def build_marker(kind: str, facts: dict, run_id: str, source_worker: str,
                 model: str | None, dataset_sha256: str | None) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    base = {
        "run_id": run_id,
        "source_worker": source_worker,
        "step": facts["step"],
        "epoch": facts["epoch"],
        "total_steps": facts["max_steps"],
        "model": model,
        "dataset_sha256": dataset_sha256,
        "created_utc": now,
        "files": facts["files"],
    }
    if kind == "live-state":
        return {
            "schema": SCHEMA_LIVE_STATE,
            "kind": "live-state",
            "note": (
                "Live state from the CPU's parallel hold, serialized at "
                "GPU-death time — current to the exact step where the GPU "
                "died. This is the GPU-death handoff (CPU live hold -> next "
                "GPU worker). It is NOT a disk checkpoint."
            ),
            **base,
        }
    return {
        "schema": SCHEMA_HANDOFF,
        "kind": "checkpoint",
        "note": (
            "Periodic disk snapshot (checkpoint-N, written every save_steps). "
            "For COLD-START workers ONLY — a worker that was never in the "
            "parallel run, resuming from the latest checkpoint. NOT the "
            "GPU-death mechanism (that is the CPU's live state)."
        ),
        **base,
    }


def export_state(kind: str, source: Path, run_id: str, source_worker: str,
                 out: Path, model: str | None,
                 dataset_sha256: str | None) -> dict:
    facts = verify_state_dir(source, kind)
    marker_name = "live_state.json" if kind == "live-state" else "handoff.json"
    marker = build_marker(kind, facts, run_id, source_worker, model,
                          dataset_sha256)
    # The dir inside the zip: live-state/ for live state, checkpoint-N/ for
    # a checkpoint (keeps the checkpoint's own name so the receiving worker
    # can tell at a glance which step it is).
    inner_dir = "live-state" if kind == "live-state" else source.name
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(facts["files"]):
            z.write(source / name, f"{inner_dir}/{name}")
        z.writestr(f"{inner_dir}/{marker_name}",
                   json.dumps(marker, indent=2))
    bundle_sha = sha256_file(out)
    return {
        "ok": True,
        "kind": kind,
        "step": facts["step"],
        "run_id": run_id,
        "source_worker": source_worker,
        "source_dir": str(source),
        "bundle": str(out),
        "bundle_sha256": bundle_sha,
        "inner_dir": inner_dir,
        "marker": marker_name,
        "files": sorted(facts["files"]),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Export a training state dir into a portable bundle "
                    "(live-state for the GPU-death handoff, checkpoint for "
                    "cold-start workers).",
    )
    p.add_argument("--kind", required=True, choices=("live-state", "checkpoint"),
                   help="live-state: the CPU hold's live state at GPU-death "
                        "time. checkpoint: a periodic disk snapshot, for "
                        "cold-start workers only.")
    p.add_argument("--source-dir", default=None,
                   help="State dir to export (a live-state dir, or a "
                        "checkpoint-<N> dir).")
    p.add_argument("--run-dir", default=None,
                   help="Run output dir (checkpoint kind only): find the "
                        "latest checkpoint-<N> inside it.")
    p.add_argument("--run-id", required=True,
                   help="Run id this state belongs to (from run_manifest.json).")
    p.add_argument("--source-worker", required=True,
                   help="Worker the state came from, e.g. cpu-hold, colab-t4, "
                        "kaggle-gpu.")
    p.add_argument("--model", default=None,
                   help="Base model id (recorded in the marker).")
    p.add_argument("--dataset-sha256", default=None,
                   help="Corpus sha256 (recorded in the marker).")
    p.add_argument("--out", default=None,
                   help="Output zip path. Default: "
                        "llmbuilder-<kind>-<step>.zip in the current dir.")
    p.add_argument("--out-dir", default=None,
                   help="Output dir (with --run-dir); the bundle name is "
                        "derived from kind + step.")
    args = p.parse_args(argv)

    try:
        if args.source_dir and args.run_dir:
            raise ExportError("Give exactly one of --source-dir / --run-dir.")
        if args.run_dir:
            if args.kind != "checkpoint":
                raise ExportError("--run-dir only makes sense for --kind checkpoint "
                                  "(a live state has no run dir to scan).")
            source = find_latest_checkpoint(Path(args.run_dir))
        elif args.source_dir:
            source = Path(args.source_dir)
        else:
            raise ExportError("Give --source-dir or --run-dir.")
        # Re-verify the step for the default bundle name (cheap: read the
        # trainer_state.json only).
        facts = verify_state_dir(source, args.kind)
        if args.out:
            out = Path(args.out)
        else:
            base = (f"llmbuilder-live-state-{facts['step']}.zip"
                    if args.kind == "live-state"
                    else f"llmbuilder-checkpoint-{facts['step']}.zip")
            out = Path(args.out_dir or ".") / base
        result = export_state(args.kind, source, args.run_id,
                              args.source_worker, out, args.model,
                              args.dataset_sha256)
        print(json.dumps(result, indent=2))
        return 0
    except ExportError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
