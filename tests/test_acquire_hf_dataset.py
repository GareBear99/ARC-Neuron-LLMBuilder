"""tests/test_acquire_hf_dataset.py

Unit tests for the HF acquisition lane (scripts/ops/acquire_hf_dataset.py).
No network access: converters, license gate, dedupe, and manifest logic are
tested with hand-built rows. The real-hub proof run is recorded in the
acquisition manifest, not in this file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ops.acquire_hf_dataset import (  # noqa: E402
    convert_gsm8k,
    convert_oasst1,
    convert_ultrachat,
    license_status,
    normalise_license,
    record_hash,
    strip_gsm8k_annotations,
    write_manifest,
)

# Hand-checkable case: the first GSM8K train record (Natalia clips).
NATALIA_QUESTION = (
    "Natalia sold clips to 48 of her friends in April, and then she sold "
    "half as many clips in May. How many clips did Natalia sell altogether "
    "in April and May?"
)
NATALIA_ANSWER_RAW = (
    "Natalia sold 48/2 = <<48/2=24>>24 clips in May.\n"
    "Natalia sold 48+24 = <<48+24=72>>72 clips altogether.\n"
    "#### 72"
)
NATALIA_ANSWER_CLEAN = (
    "Natalia sold 48/2 = 24 clips in May.\n"
    "Natalia sold 48+24 = 72 clips altogether.\n"
    "#### 72"
)


def test_strip_gsm8k_annotations_removes_calculator_marks():
    assert strip_gsm8k_annotations(NATALIA_ANSWER_RAW) == NATALIA_ANSWER_CLEAN
    assert "<<" not in strip_gsm8k_annotations(NATALIA_ANSWER_RAW)


def test_convert_gsm8k_first_record_matches_by_hand():
    rec = convert_gsm8k(
        {"question": NATALIA_QUESTION, "answer": NATALIA_ANSWER_RAW}, 0
    )
    assert rec is not None
    assert rec["id"] == "gsm8k_train_000001"
    assert rec["prompt"] == NATALIA_QUESTION
    assert rec["target"] == NATALIA_ANSWER_CLEAN
    assert rec["target"].endswith("#### 72")
    assert rec["capability"] == "reasoning"
    assert rec["domain"] == "arithmetic"
    assert rec["source_repo"] == "openai/gsm8k"
    assert rec["promotion_lane"] == "candidate_v2_only"
    assert "v2_candidate_only" in rec["tags"]


def test_convert_gsm8k_drops_empty_rows():
    assert convert_gsm8k({"question": "", "answer": "#### 1"}, 0) is None
    assert convert_gsm8k({"question": "Q?", "answer": ""}, 0) is None
    assert convert_gsm8k({}, 0) is None


def test_record_hash_dedupes_case_and_whitespace_variants():
    h1 = record_hash("  What is 2+2? ", "4")
    h2 = record_hash("what is 2+2?", "4")
    h3 = record_hash("What is 2+2?", "5")
    assert h1 == h2
    assert h1 != h3


def test_license_gate_permissive():
    assert license_status("MIT") == "permissive"
    assert license_status("apache-2.0") == "permissive"
    assert license_status("Apache 2.0") == "permissive"
    assert license_status("CC-BY-4.0") == "permissive"
    assert license_status("cc-by-sa-4.0") == "permissive"
    assert license_status("CC0-1.0") == "permissive"


def test_license_gate_held_and_unknown():
    # Non-commercial / copyleft-with-conditions / mixed corpora must hold.
    assert license_status("cc-by-nc-4.0") == "held"
    assert license_status("gpl-3.0") == "held"
    assert license_status("other") == "unknown"
    assert license_status(None) == "unknown"
    assert license_status("") == "unknown"
    assert normalise_license("Apache 2.0") == "apache2.0"
    assert normalise_license("apache-2.0") == "apache2.0"
    assert license_status("multiple licenses") == "held"


def test_convert_oasst1_pair_shape():
    rec = convert_oasst1({"prompt": "Hello", "response": "Hi there."}, 0)
    assert rec is not None
    assert rec["prompt"] == "Hello"
    assert rec["target"] == "Hi there."
    assert rec["promotion_lane"] == "candidate_v2_only"
    assert convert_oasst1({"prompt": "", "response": "x"}, 0) is None


def test_convert_ultrachat_first_turn_only():
    rec = convert_ultrachat(
        {"data": [
            {"role": "user", "content": "What is the capital of France?"},
            {"role": "assistant", "content": "Paris."},
            {"role": "user", "content": "And of Spain?"},
            {"role": "assistant", "content": "Madrid."},
        ]},
        0,
    )
    assert rec is not None
    assert rec["prompt"] == "What is the capital of France?"
    assert rec["target"] == "Paris."
    assert convert_ultrachat({"data": []}, 0) is None


def test_write_manifest_round_trips(tmp_path):
    payload = {"schema_version": "acquire-hf/1.0", "counts": {"converted": 3}}
    path = tmp_path / "manifest.json"
    write_manifest(path, payload)
    assert json.loads(path.read_text(encoding="utf-8")) == payload


def test_acquire_holds_nonpermissive_license_without_downloading(tmp_path, monkeypatch):
    """License gate fires before any download: no JSONL, held manifest, exit 2."""
    import scripts.ops.acquire_hf_dataset as lane

    monkeypatch.setattr(
        lane, "fetch_dataset_info",
        lambda hf_id: {"license": "cc-by-nc-4.0", "revision": "deadbeef", "downloads": 0},
    )
    called = []
    monkeypatch.setattr(
        lane, "quarantine_parquet_files",
        lambda *a, **k: called.append(True) or [],
    )
    out = tmp_path / "held"
    with pytest.raises(SystemExit) as exc:
        lane.acquire("openai/gsm8k", "main", "train", 10, out)
    assert exc.value.code == 2
    assert called == []  # no download attempted
    assert not (out / "gsm8k.jsonl").exists()
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["quarantine_status"] == "held-license-review"
    assert manifest["checks"]["license"] == "held"
    assert manifest["counts"]["converted"] == 0


def test_acquire_holds_unknown_converter_with_receipt(tmp_path, monkeypatch):
    """Permissive license but no converter: held manifest, exit 2, no JSONL."""
    import scripts.ops.acquire_hf_dataset as lane

    monkeypatch.setattr(
        lane, "fetch_dataset_info",
        lambda hf_id: {"license": "mit", "revision": "deadbeef", "downloads": 0},
    )
    out = tmp_path / "noconv"
    with pytest.raises(SystemExit) as exc:
        lane.acquire("someorg/no-converter-dataset", None, "train", 10, out)
    assert exc.value.code == 2
    assert not list(out.glob("*.jsonl"))
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["quarantine_status"] == "held-no-converter"
    assert manifest["checks"]["license"] == "pass"
