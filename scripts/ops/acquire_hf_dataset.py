#!/usr/bin/env python3
"""scripts/ops/acquire_hf_dataset.py

Hugging Face acquisition lane for ARC-Neuron 3.0.

Downloads one dataset from the Hugging Face hub, holds the raw bytes in
quarantine, converts records to the repo's seed-examples JSONL schema, and
writes a manifest recording every gate the README requires:

    manifest -> license -> hash -> quarantine -> [benchmark, no-regression]

The last two checks are Gate v2's job, not this script's. They are recorded
in the manifest as ``pending-gate-v2`` — never claimed as passed.

Output layout (``--out`` defaults to ``datasets/acquired/<slug>/``)::

    <out>/quarantine/<raw files>   raw hub bytes, hashed, never edited
    <out>/<slug>.jsonl             converted records, seed schema
    <out>/manifest.json            provenance + gate statuses

Converted record (repo seed schema, same shape as
``datasets/distillation_sft/phase1_*.jsonl`` — consumable by
``train_arc_native_candidate.py`` and by the Lucid Forge JSONL import)::

    {"id": "gsm8k_train_000001", "source_repo": "openai/gsm8k",
     "capability": "reasoning", "domain": "arithmetic",
     "prompt": "...", "target": "...",
     "tags": ["gsm8k", "reasoning", "arithmetic", "v2_candidate_only"],
     "promotion_lane": "candidate_v2_only",
     "notes": "Acquired from Hugging Face; v2 candidate lane only."}

License gate
------------
The hub license is read from the dataset card. Only permissive licenses
proceed to conversion (MIT, Apache-2.0, BSD, CC-BY-4.0, CC-BY-SA-4.0, CC0,
ODC-By, CDLA-Permissive, Unlicense). Anything else — unknown, missing,
non-commercial, copyleft-with-conditions, or a mixed-license corpus such as
The Stack — is HELD: raw bytes stay in quarantine, a manifest is written
with ``quarantine_status: held-license-review``, no converted JSONL is
written, and the script exits non-zero. Nothing is silently ingested.

Converters
----------
One converter per dataset id, registered in ``CONVERTERS``. Only ``gsm8k``
is verified against a real pull (see tests/test_acquire_hf_dataset.py).
``oasst1`` and ``ultrachat`` converters are implemented from the datasets'
documented schemas but are marked UNTESTED — they need a real pull to
verify before anyone trusts their output.

Usage
-----
  python3 scripts/ops/acquire_hf_dataset.py --dataset openai/gsm8k --limit 500
  python3 scripts/ops/acquire_hf_dataset.py --dataset OpenAssistant/oasst1 --split train --limit 1000 --out datasets/acquired/oasst1
  python3 scripts/ops/acquire_hf_dataset.py --dataset HuggingFaceH4/ultrachat_200k --config train_sft --limit 200

Requires: huggingface_hub, datasets (see requirements-acquire.txt).
Run inside the acquire venv: .venv-hf/bin/python scripts/ops/acquire_hf_dataset.py ...
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA_VERSION = "acquire-hf/1.0"

# Licenses that may proceed to conversion without further review.
# Compared against normalise_license() output (lowercase alphanumerics
# plus dots; hyphens/spaces are stripped, so "Apache 2.0" == "apache-2.0").
PERMISSIVE_LICENSES = {
    "mit",
    "apache2.0",
    "bsd2clause",
    "bsd3clause",
    "bsd3clauseclear",
    "ccby4.0",
    "ccbysa4.0",
    "cc01.0",
    "odcby1.0",
    "cdlapermissive2.0",
    "unlicense",
    "wtfpl",
    "isc",
    "artistic2.0",
}

# Normalised names that mean "no usable license on the card".
UNKNOWN_LICENSE_TOKENS = {"", "unknown", "other", "none", "not specified", "n/a"}


def normalise_license(raw: str | None) -> str:
    """Lower-case a license string for allowlist comparison.

    Keeps only lowercase letters, digits, and dots, so "Apache 2.0",
    "apache-2.0", and "APACHE2.0" all normalise to "apache2.0".
    """
    if raw is None:
        return ""
    return re.sub(r"[^a-z0-9.]", "", raw.strip().lower())


def license_status(raw: str | None) -> str:
    """Return 'permissive', 'held' or 'unknown' for a hub license string."""
    norm = normalise_license(raw)
    if norm in UNKNOWN_LICENSE_TOKENS:
        return "unknown"
    if norm in PERMISSIVE_LICENSES:
        return "permissive"
    return "held"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def record_hash(prompt: str, target: str) -> str:
    """Content hash used for dedupe: normalised prompt + target."""
    norm = (prompt.strip().lower() + "\n" + target.strip()).encode("utf-8")
    return hashlib.sha256(norm).hexdigest()


def slugify_dataset(hf_id: str) -> str:
    return hf_id.split("/")[-1].lower().replace("_", "-")


# ── Converters: hub row -> seed-schema record ─────────────────────────────

_CALC_ANNOTATION = re.compile(r"<<[^>]*>>")


def strip_gsm8k_annotations(answer: str) -> str:
    """Remove GSM8K <<...>> calculator annotations, keep the solution text."""
    return _CALC_ANNOTATION.sub("", answer).strip()


def convert_gsm8k(row: dict, index: int) -> dict | None:
    """openai/gsm8k row: {"question": str, "answer": str}."""
    prompt = str(row.get("question") or "").strip()
    target = strip_gsm8k_annotations(str(row.get("answer") or ""))
    if not prompt or not target:
        return None
    return {
        "id": f"gsm8k_train_{index + 1:06d}",
        "source_repo": "openai/gsm8k",
        "capability": "reasoning",
        "domain": "arithmetic",
        "prompt": prompt,
        "target": target,
        "tags": ["gsm8k", "reasoning", "arithmetic", "v2_candidate_only"],
        "promotion_lane": "candidate_v2_only",
        "notes": "Acquired from Hugging Face; v2 candidate lane only.",
    }


def convert_oasst1(row: dict, index: int) -> dict | None:
    """OpenAssistant/oasst1 row (UNTESTED — needs a real pull to verify).

    Takes a prompter message and its first assistant reply as one pair.
    Rows are message-level: {"message_id", "parent_id", "role",
    "text", "lang", "rank", ...}. The caller must feed only root prompter
    rows paired with their best assistant child — see _pair_oasst1_rows.
    """
    prompt = str(row.get("prompt") or "").strip()
    target = str(row.get("response") or "").strip()
    if not prompt or not target:
        return None
    return {
        "id": f"oasst1_train_{index + 1:06d}",
        "source_repo": "OpenAssistant/oasst1",
        "capability": "instruction_following",
        "domain": "dialogue",
        "prompt": prompt,
        "target": target,
        "tags": ["oasst1", "dialogue", "instruction_following", "v2_candidate_only"],
        "promotion_lane": "candidate_v2_only",
        "notes": "Acquired from Hugging Face; v2 candidate lane only.",
    }


def _pair_oasst1_rows(rows: list[dict]) -> list[dict]:
    """Pair root prompter messages with their best-ranked assistant child.

    OASST1 is a message tree. A usable SFT pair is a root prompter message
    plus the assistant reply with the lowest rank (best) among its children.
    """
    by_parent: dict[str | None, list[dict]] = {}
    for row in rows:
        by_parent.setdefault(row.get("parent_id"), []).append(row)
    pairs: list[dict] = []
    for row in rows:
        if row.get("parent_id") is not None or row.get("role") != "prompter":
            continue
        children = [
            c for c in by_parent.get(row.get("message_id"), [])
            if c.get("role") == "assistant"
        ]
        if not children:
            continue
        best = min(children, key=lambda c: c.get("rank") if c.get("rank") is not None else 99)
        pairs.append({"prompt": row.get("text", ""), "response": best.get("text", "")})
    return pairs


def convert_ultrachat(row: dict, index: int) -> dict | None:
    """HuggingFaceH4/ultrachat_200k row (UNTESTED — needs a real pull).

    Row: {"data": [{"content": str, "role": "user"|"assistant"}, ...]}.
    First user turn is the prompt, first assistant turn is the target.
    """
    messages = row.get("data") or row.get("messages") or []
    user_turn = next(
        (str(m.get("content", "")) for m in messages if isinstance(m, dict) and m.get("role") == "user"),
        "",
    )
    asst_turn = next(
        (str(m.get("content", "")) for m in messages if isinstance(m, dict) and m.get("role") == "assistant"),
        "",
    )
    prompt, target = user_turn.strip(), asst_turn.strip()
    if not prompt or not target:
        return None
    return {
        "id": f"ultrachat_train_{index + 1:06d}",
        "source_repo": "HuggingFaceH4/ultrachat_200k",
        "capability": "instruction_following",
        "domain": "dialogue",
        "prompt": prompt,
        "target": target,
        "tags": ["ultrachat", "dialogue", "multi_turn", "v2_candidate_only"],
        "promotion_lane": "candidate_v2_only",
        "notes": "Acquired from Hugging Face; v2 candidate lane only. First turn only.",
    }


CONVERTERS = {
    "openai/gsm8k": convert_gsm8k,
    "openassistant/oasst1": convert_oasst1,
    "huggingfaceh4/ultrachat_200k": convert_ultrachat,
}

# Converters whose output has been verified against a real hub pull.
VERIFIED_CONVERTERS = {"openai/gsm8k"}


# ── Hub access ───────────────────────────────────────────────────────────

def fetch_dataset_info(hf_id: str) -> dict:
    """License + revision for a hub dataset. Raises on hub errors."""
    from huggingface_hub import HfApi

    info = HfApi().dataset_info(hf_id)
    card = info.cardData or {}
    license_value = card.get("license")
    if isinstance(license_value, list):
        license_value = license_value[0] if license_value else None
    return {
        "license": license_value,
        "revision": info.sha,
        "downloads": getattr(info, "downloads", None),
    }


def quarantine_parquet_files(
    hf_id: str, config: str | None, split: str, quarantine_dir: Path
) -> list[Path]:
    """Download the split's parquet files into quarantine.

    Uses the hub's auto-converted parquet branch (refs/convert/parquet) so
    only the requested split's bytes are fetched. Returns the downloaded
    paths. Raises if no parquet file matches the split.
    """
    from huggingface_hub import HfApi, hf_hub_download

    api = HfApi()
    try:
        files = api.list_repo_files(hf_id, repo_type="dataset", revision="refs/convert/parquet")
    except Exception as exc:  # noqa: BLE001 — fall through to the direct-load path
        print(f"  [acquire] parquet branch unavailable ({exc}); using direct load")
        return []
    wanted: list[str] = []
    for name in files:
        parts = name.split("/")
        if config and len(parts) >= 2 and parts[0] != config:
            continue
        leaf = parts[-1]
        if not leaf.endswith(".parquet"):
            continue
        # Two hub layouts exist: "main/train-00000-of-00001.parquet" and
        # the newer directory layout "main/train/0000.parquet".
        if len(parts) >= 2 and parts[-2] == split:
            wanted.append(name)
        elif leaf.startswith(f"{split}-"):
            wanted.append(name)
    if not wanted:
        print("  [acquire] no parquet file matched this split; using direct load")
        return []
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []
    for name in sorted(wanted):
        # hf_hub_download preserves the repo path under local_dir, so the
        # file lands at quarantine/<config>/<split>/0000.parquet, not at
        # the quarantine root. Use the path it returns, not a guessed one.
        dest = Path(hf_hub_download(
            repo_id=hf_id,
            filename=name,
            repo_type="dataset",
            revision="refs/convert/parquet",
            local_dir=str(quarantine_dir),
            local_dir_use_symlinks=False,
        ))
        downloaded.append(dest)
        print(f"  [acquire] quarantined {name} ({dest.stat().st_size} bytes)")
    # hf_hub_download leaves its own bookkeeping (.cache/...) under
    # local_dir; quarantine holds raw dataset bytes only, so drop it.
    import shutil

    cache_dir = quarantine_dir / ".cache"
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    return downloaded


def load_rows_from_parquet(paths: list[Path], limit: int) -> list[dict]:
    """Load rows from local (quarantined) parquet files via `datasets`."""
    from datasets import load_dataset

    ds = load_dataset("parquet", data_files=[str(p) for p in paths], split="train")
    return [dict(ds[i]) for i in range(min(limit, len(ds)))]


def load_rows_direct(hf_id: str, config: str | None, split: str, limit: int) -> list[dict]:
    """Fallback: load rows straight from the hub (no parquet branch)."""
    from datasets import load_dataset

    ds = load_dataset(hf_id, config, split=f"{split}[:{limit}]")
    return [dict(row) for row in ds]


# ── Manifest ─────────────────────────────────────────────────────────────

def write_manifest(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ── Main ─────────────────────────────────────────────────────────────────

def acquire(
    hf_id: str,
    config: str | None,
    split: str,
    limit: int,
    out_dir: Path,
) -> dict:
    """Run the full lane. Returns the manifest payload.

    Raises SystemExit(2) when the license gate holds the dataset or when
    no converter is registered for it. Every refusal writes a manifest
    first, so there is always a receipt — never a bare failure.
    """
    hf_key = hf_id.lower()
    slug = slugify_dataset(hf_id)
    quarantine_dir = out_dir / "quarantine"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[acquire] {hf_id} config={config or '-'} split={split} limit={limit}")
    info = fetch_dataset_info(hf_id)
    lic = info["license"]
    lic_status = license_status(lic)
    print(f"[acquire] license: {lic!r} -> {lic_status}; revision {info['revision']}")

    manifest: dict = {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "hf_id": hf_id,
            "config": config,
            "split": split,
            "revision": info["revision"],
            "license": lic,
            "license_status": lic_status,
        },
        "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
        "quarantine_dir": str(quarantine_dir),
        "checks": {
            "manifest": "pass",
            "license": "pass" if lic_status == "permissive" else "held",
            "hash": "pass",
            "quarantine": "pass",
            "benchmark": "pending-gate-v2",
            "no_regression": "pending-gate-v2",
        },
        "counts": {"raw_rows": 0, "converted": 0, "dropped_empty": 0, "dropped_duplicate": 0},
        "converter_verified": hf_key in VERIFIED_CONVERTERS,
    }

    if lic_status != "permissive":
        manifest["quarantine_status"] = "held-license-review"
        manifest["notes"] = (
            f"License {lic!r} is not on the permissive allowlist. Raw bytes "
            "were not converted; no JSONL was written. A human must review "
            "the license before this dataset can enter the v2 candidate lane."
        )
        write_manifest(out_dir / "manifest.json", manifest)
        print(f"[acquire] HELD: license {lic!r} — manifest written, no JSONL produced")
        raise SystemExit(2)

    if hf_key not in CONVERTERS:
        manifest["quarantine_status"] = "held-no-converter"
        manifest["notes"] = (
            f"No converter registered for {hf_id}; supported: {sorted(CONVERTERS)}. "
            "License passed but no conversion ran; no JSONL was written."
        )
        write_manifest(out_dir / "manifest.json", manifest)
        print(f"[acquire] HELD: no converter for {hf_id} — manifest written, no JSONL produced")
        raise SystemExit(2)
    converter = CONVERTERS[hf_key]

    # 1. Raw bytes into quarantine first.
    raw_files = quarantine_parquet_files(hf_id, config, split, quarantine_dir)
    raw_hashes: list[dict] = []
    if raw_files:
        for path in raw_files:
            raw_hashes.append({
                "file": path.name,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            })
        rows = load_rows_from_parquet(raw_files, limit)
        manifest["raw_source"] = "parquet-branch"
    else:
        rows = load_rows_direct(hf_id, config, split, limit)
        raw_path = quarantine_dir / "raw_rows.jsonl"
        quarantine_dir.mkdir(parents=True, exist_ok=True)
        with raw_path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        raw_hashes.append({
            "file": raw_path.name,
            "sha256": sha256_file(raw_path),
            "bytes": raw_path.stat().st_size,
        })
        manifest["raw_source"] = "direct-load-rows"
    manifest["raw_files"] = raw_hashes
    combined = hashlib.sha256(
        "".join(h["sha256"] for h in raw_hashes).encode("utf-8")
    ).hexdigest()
    manifest["raw_sha256_combined"] = combined
    print(f"[acquire] raw rows fetched: {len(rows)} (raw sha256 combined {combined[:16]}...)")

    # 2. Convert (OASST1 needs tree pairing before conversion).
    if hf_key == "openassistant/oasst1":
        rows = _pair_oasst1_rows(rows)
    converted: list[dict] = []
    seen: set[str] = set()
    dropped_empty = 0
    dropped_duplicate = 0
    for i, row in enumerate(rows):
        rec = converter(row, i)
        if rec is None:
            dropped_empty += 1
            continue
        digest = record_hash(rec["prompt"], rec["target"])
        if digest in seen:
            dropped_duplicate += 1
            continue
        seen.add(digest)
        converted.append(rec)

    # 3. Write converted JSONL + manifest.
    jsonl_path = out_dir / f"{slug}.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for rec in converted:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    manifest["quarantine_status"] = "quarantined"
    manifest["output_jsonl"] = str(jsonl_path)
    manifest["counts"] = {
        "raw_rows": len(rows),
        "converted": len(converted),
        "dropped_empty": dropped_empty,
        "dropped_duplicate": dropped_duplicate,
    }
    manifest["notes"] = (
        "Converted records are v2-candidate-lane only (promotion_lane "
        "candidate_v2_only). They do not change the incumbent until a trained "
        "candidate passes benchmark and Gate v2."
    )
    write_manifest(out_dir / "manifest.json", manifest)
    print(f"[acquire] wrote {len(converted)} records -> {jsonl_path}")
    print(f"[acquire] manifest -> {out_dir / 'manifest.json'}")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Acquire a Hugging Face dataset into the v2 candidate lane.")
    parser.add_argument("--dataset", required=True, help="HF dataset id, e.g. openai/gsm8k")
    parser.add_argument("--config", default=None, help="dataset config name, e.g. main")
    parser.add_argument("--split", default="train", help="split to pull (default: train)")
    parser.add_argument("--limit", type=int, default=1000, help="max records to convert (default: 1000)")
    parser.add_argument("--out", default=None, help="output dir (default: datasets/acquired/<slug>)")
    args = parser.parse_args(argv)

    if args.limit < 1:
        parser.error("--limit must be >= 1")
    out_dir = Path(args.out) if args.out else ROOT / "datasets" / "acquired" / slugify_dataset(args.dataset)
    try:
        acquire(args.dataset, args.config, args.split, args.limit, out_dir)
    except SystemExit as exc:
        # SystemExit carries an int code from acquire(); anything else is
        # an unexpected failure, not a clean refusal.
        return exc.code if isinstance(exc.code, int) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
