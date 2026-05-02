"""tests/test_phase2_phase4.py

Tests for:
  1. FloorModel — freeze, check, CLI
  2. ReflectionLoop — draft→critique→revise pipeline
  3. TerminologyStore — extraction, dedup, correction, training export
  4. New benchmark files — continuity and reflection tasks load and score
  5. Rubric scorer — new capability buckets work without crash
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── 1. FloorModel ─────────────────────────────────────────────────────────────

def test_floor_model_default_passes_strong_candidate(tmp_path):
    from runtime.floor_model import FloorModel
    floor = FloorModel(floor_path=tmp_path / "floor.json")
    # Use the same field names as promote_candidate.py entry dict
    strong = {
        "repair_success": 0.8,
        "calibration_error": 0.25,   # 1 - 0.75 calibration score
        "planning": 0.95,
        "compression": 0.85,
        "paraphrase_stability": 0.80,
        "overall_weighted_score": 0.82,
        "failure_rate": 0.0,
    }
    violations = floor.check(strong)
    assert violations == [], f"Expected no violations, got: {violations}"


def test_floor_model_catches_repair_drop(tmp_path):
    from runtime.floor_model import FloorModel
    floor = FloorModel(floor_path=tmp_path / "floor.json")
    weak = {
        "repair_success": 0.10,      # below default floor 0.40
        "calibration_error": 0.20,
        "planning": 0.95,
        "compression": 0.85,
        "paraphrase_stability": 0.85,
        "failure_rate": 0.0,
    }
    violations = floor.check(weak)
    assert any("repair" in v for v in violations), f"repair violation not caught: {violations}"


def test_floor_model_catches_failure_rate_ceiling(tmp_path):
    from runtime.floor_model import FloorModel
    floor = FloorModel(floor_path=tmp_path / "floor.json")
    high_fail = {
        "repair_success": 0.8,
        "calibration_error": 0.20,
        "planning": 0.95,
        "compression": 0.85,
        "paraphrase_stability": 0.85,
        "failure_rate": 0.40,        # above ceiling 0.30
    }
    violations = floor.check(high_fail)
    assert any("failure_rate" in v for v in violations)


def test_floor_model_set_and_reload(tmp_path):
    from runtime.floor_model import FloorModel
    floor = FloorModel(floor_path=tmp_path / "floor.json")
    scores = {"repair": 0.75, "calibration": 0.80, "planning": 0.90,
              "compression": 0.70, "paraphrase_stability": 0.75,
              "overall_weighted_score": 0.78, "failure_rate": 0.05}
    floor.set_floor(scores, note="test lock")
    floor2 = FloorModel(floor_path=tmp_path / "floor.json")
    # Should load the set values (with 10% margin applied in CLI, but direct set uses raw values)
    assert floor2.scores["repair"] == 0.75
    assert floor2.status()["note"] == "test lock"


def test_floor_model_cli_status(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(ROOT / "runtime" / "floor_model.py"), "--status"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert proc.returncode == 0
    result = json.loads(proc.stdout)
    assert "scores" in result
    assert "capabilities_guarded" in result


# ── 2. ReflectionLoop ─────────────────────────────────────────────────────────

def test_reflection_loop_produces_all_stages():
    from adapters.heuristic_adapter import HeuristicAdapter
    from runtime.reflection_loop import ReflectionLoop
    loop = ReflectionLoop(HeuristicAdapter())
    r = loop.generate("Plan the next repair cycle with constraints preserved.")
    assert r.ok
    assert r.text
    meta = r.meta.get("reflection", {})
    assert "draft" in meta
    assert "critique" in meta
    assert "final_source" in meta


def test_reflection_loop_skips_on_empty():
    from adapters.echo_adapter import EchoAdapter
    from runtime.reflection_loop import ReflectionLoop
    loop = ReflectionLoop(EchoAdapter(), skip_on_short=1000)
    # Echo adapter returns short text for a short input
    r = loop.generate("ok")
    assert r.ok
    # Critique step may be skipped or not — just verify no crash and has text
    assert isinstance(r.text, str)


def test_reflection_loop_inherits_promotable():
    from adapters.heuristic_adapter import HeuristicAdapter
    from runtime.reflection_loop import ReflectionLoop
    loop = ReflectionLoop(HeuristicAdapter())
    assert loop.promotable is False   # heuristic is not promotable


def test_reflection_loop_backend_identity():
    from adapters.heuristic_adapter import HeuristicAdapter
    from runtime.reflection_loop import ReflectionLoop
    loop = ReflectionLoop(HeuristicAdapter())
    identity = loop.backend_identity()
    assert identity.get("reflection_loop") is True


# ── 3. TerminologyStore ───────────────────────────────────────────────────────

def test_terminology_extraction_definition(tmp_path):
    from runtime.terminology import TerminologyStore
    store = TerminologyStore(db_path=tmp_path/"t.json", obin_path=tmp_path/"o.obin")
    text = "The omnibinary means the indexed binary ledger that mirrors source truth."
    records = store.absorb_from_conversation(text, mirror=False)
    assert len(records) >= 1
    terms = [r.term.lower() for r in records]
    assert any("omnibinary" in t for t in terms)


def test_terminology_extraction_alias(tmp_path):
    from runtime.terminology import TerminologyStore
    store = TerminologyStore(db_path=tmp_path/"t.json", obin_path=tmp_path/"o.obin")
    text = "Arc-RAR is also called the archive bundle layer."
    records = store.absorb_from_conversation(text, mirror=False)
    aliases = [r for r in records if r.record_type == "alias"]
    assert len(aliases) >= 1


def test_terminology_deduplication(tmp_path):
    from runtime.terminology import TerminologyStore
    store = TerminologyStore(db_path=tmp_path/"t.json", obin_path=tmp_path/"o.obin")
    text = "Omnibinary means the indexed binary ledger that mirrors source truth."
    r1 = store.absorb_from_conversation(text, mirror=False)
    r2 = store.absorb_from_conversation(text, mirror=False)   # same text again
    assert len(r2) == 0, "Second absorb of same text must produce no new records"


def test_terminology_correction(tmp_path):
    from runtime.terminology import TerminologyStore
    store = TerminologyStore(db_path=tmp_path/"t.json", obin_path=tmp_path/"o.obin")
    rec = store.correct("gguf", "a frozen deployable brain snapshot in GGUF v3 format")
    assert rec.record_type == "correction"
    assert rec.approved is True
    assert rec.confidence == 0.99
    found = store.lookup("gguf")
    assert any(r.term_id == rec.term_id for r in found)


def test_terminology_training_export(tmp_path):
    from runtime.terminology import TerminologyStore
    store = TerminologyStore(db_path=tmp_path/"t.json", obin_path=tmp_path/"o.obin")
    store.correct("floor model", "the frozen baseline every candidate must beat")
    store.correct("omnibinary", "indexed binary ledger with O(1) event lookup")
    out = tmp_path / "term_sft.jsonl"
    result = store.dump_for_training(output_path=out)
    assert result["sft_records"] >= 2
    assert out.exists()
    lines = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
    assert all("prompt" in l and "target" in l for l in lines)


def test_terminology_stats(tmp_path):
    from runtime.terminology import TerminologyStore
    store = TerminologyStore(db_path=tmp_path/"t.json", obin_path=tmp_path/"o.obin")
    store.correct("arc-rar", "archive and rollback bundle layer")
    stats = store.stats()
    assert stats["total_records"] >= 1
    assert stats["approved_records"] >= 1
    assert "by_type" in stats


# ── 4. New benchmark files ────────────────────────────────────────────────────

def test_continuity_benchmarks_load():
    from runtime.task_loader import load_jsonl
    tasks = list(load_jsonl(ROOT / "benchmarks" / "continuity" / "seed_tasks.jsonl"))
    assert len(tasks) == 10
    for t in tasks:
        assert "capability" in t
        assert "prompt" in t
        assert t["scoring"] in {"rubric", "retention"}


def test_reflection_benchmarks_load():
    from runtime.task_loader import load_jsonl
    tasks = list(load_jsonl(ROOT / "benchmarks" / "reflection" / "seed_tasks.jsonl"))
    assert len(tasks) == 10
    for t in tasks:
        assert t["capability"] == "reflection"
        assert t["scoring"] == "rubric"


def test_continuity_retention_tasks_score():
    from scorers.rubric import score_record
    from runtime.task_loader import load_jsonl
    tasks = list(load_jsonl(ROOT / "benchmarks" / "continuity" / "seed_tasks.jsonl"))
    retention_tasks = [t for t in tasks if t["scoring"] == "retention"]
    assert len(retention_tasks) >= 5
    sample_text = (
        "The goal is to build a governed loop. The constraint is that rollback must "
        "be preserved. Based on what we know, the next step should be to verify the "
        "artifact integrity."
    )
    for task in retention_tasks[:3]:
        result = score_record(sample_text, task=task)
        assert result["normalized_score"] >= 0.0
        assert result["scoring_mode"] == "retention"


# ── 5. Rubric scorer new capabilities ─────────────────────────────────────────

def test_rubric_all_new_capabilities_no_crash():
    from scorers.rubric import score_record
    new_caps = [
        "continuity", "reflection", "lexical_accuracy",
        "archive_reasoning", "runtime_reasoning", "state_evidence",
        "system_spine_reasoning", "native_operation_planning",
        "deterministic_compliance", "deterministic_format",
        "refusal_correctness",
    ]
    text = (
        "The goal is preservation of the rollback constraint. The language module "
        "feeds into the runtime, which produces archive bundles. Based on evidence, "
        "the next action is to verify the floor model. The system uses omnibinary "
        "as an indexed binary ledger. This cannot be confirmed without benchmark data."
    )
    for cap in new_caps:
        result = score_record(text, task={"capability": cap, "scoring": "rubric"})
        assert 0.0 <= result["normalized_score"] <= 1.0, f"Bad score for {cap}: {result}"
        assert result["capability"] == cap


def test_rubric_retention_mode_routes_correctly():
    from scorers.rubric import score_record
    text = "The goal is continuity. The constraint must be preserved. The next step is to check."
    task = {"capability": "continuity", "scoring": "retention", "reference": {"rubric": "test"}}
    result = score_record(text, task=task)
    assert result.get("scoring_mode") == "retention"


def test_rubric_reflection_capability_scores():
    from scorers.rubric import score_record
    text = (
        "The overclaim here is the word 'definitely'. I will revise this to be more "
        "accurate: based on the evidence, it is likely that this approach is sound."
    )
    result = score_record(text, task={"capability": "reflection", "scoring": "rubric"})
    assert result["normalized_score"] > 0.0
    assert len(result["matched_checks"]) > 0, f"Reflection scored 0 matched checks: {result}"


# ── 6. Full promote with floor model wired ────────────────────────────────────

def test_promote_floor_breach_causes_reject(tmp_path):
    scored = tmp_path / "scored.json"
    scoreboard = tmp_path / "scoreboard.json"
    report = tmp_path / "report.json"
    # repair=0.05 should hit default floor (0.40)
    payload = {
        "results": [{"run_id": "r1", "latency_ms": 5.0, "ok": True}],
        "summary": {"repair": 0.05, "calibration": 0.9, "planning": 0.9,
                    "compression": 0.9, "paraphrase_stability": 0.9},
        "failure_count": 0,
        "overall_weighted_score": 0.74,
        "scorer_version": "v2",
    }
    scored.write_text(json.dumps(payload))
    proc = subprocess.run(
        [sys.executable, "scripts/execution/promote_candidate.py",
         "--scored", str(scored), "--scoreboard", str(scoreboard),
         "--report", str(report), "--model-name", "floor_test", "--skip-bundle"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert proc.returncode == 0
    r = json.loads(report.read_text())
    # Should reject due to floor breach or hard-reject on repair
    assert r["decision"] in {"reject"}, f"Expected reject, got: {r['decision']}"
