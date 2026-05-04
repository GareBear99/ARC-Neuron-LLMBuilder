"""tests/test_audit_remediation.py

Regression tests for the audit remediation changes:

1. Rubric keyword-soup guard — keyword dumps must score 0.0 on content
   checks regardless of how many relevant keywords they contain.
2. Rubric soup flag propagates through score_record and _score_retention.
3. Genuine prose responses are NOT flagged as soup.
4. Reasoning benchmark diversity — no two tasks may share the same prompt
   template (no more scenario-N variants).
5. Quantization benchmark diversity — same.
6. Benchmark integrity — every task must have a unique id and non-empty prompt.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# ── rubric helpers ────────────────────────────────────────────────────────────

import sys
sys.path.insert(0, str(ROOT))
from scorers.rubric import score_record, _is_keyword_soup, _is_substantial

KEYWORD_SOUP = (
    "constraint preserve boundary interface risk tradeoff regression failure mode "
    "validate test evidence verify observability plan steps first then smallest "
    "minimal targeted narrow preserve interfaces public api without breaking fact "
    "inference given unknown reject not acceptable only if conditionally conflict "
    "contradiction tradeoff threatens missing evidence not shown unverified assumption "
    "too broad scope blast radius patch fix change guard rollback minimal targeted "
    "surgical narrow test regression validate assert goal objective task blocker risk "
    "next action do this follow-up likely uncertain confidence may bounded evidence "
    "based on from the prompt given only"
)

GOOD_PROSE = (
    "Not acceptable as written. The proposal threatens rollback safety which is a "
    "direct conflict with the governed-change contract. Specifically, the fact that "
    "constraints A and B are preserved does not verify that observability boundaries "
    "remain intact. Reject the fix unless it can be conditionally bound to preserve "
    "the rollback path and instrumentation. Validate with evidence before proceeding."
)

# Capabilities where short direct answers are valid — soup guard is intentionally
# not applied to these (they are in SOUP_EXEMPT_CAPABILITIES in the rubric).
SOUP_EXEMPT_CAPS = {"calibration", "paraphrase_stability", "intelligence", "out_of_domain",
                    "instruction_following", "quantization_retention"}

# Capabilities where the soup guard IS applied and soup must score 0.0
# These caps use common checks which soup guard blocks.
# planning and repair are now SOUP_EXEMPT (action-oriented, not analytical)
# so soup responses score non-zero on them — they are intentionally excluded.
CAPABILITY_FAMILIES = [
    "reasoning",
    "compression", "continuity", "reflection",
]


# ── 1. keyword-soup detection ─────────────────────────────────────────────────

def test_keyword_soup_detected_on_wordlist():
    """A long run-on keyword dump with no sentence punctuation must be flagged."""
    assert _is_keyword_soup(KEYWORD_SOUP), "word-list dump must be flagged as soup"


def test_keyword_soup_not_detected_on_prose():
    assert not _is_keyword_soup(GOOD_PROSE), "genuine prose must NOT be flagged as soup"


def test_keyword_soup_detected_on_empty():
    assert _is_keyword_soup(""), "empty string must be flagged"


def test_keyword_soup_detected_on_single_word():
    assert _is_keyword_soup("constraint"), "single word must be flagged"


def test_keyword_soup_not_detected_on_long_prose():
    long_prose = GOOD_PROSE * 3
    assert not _is_keyword_soup(long_prose)


# ── 2. soup guard zeroes content checks ───────────────────────────────────────

@pytest.mark.parametrize("capability", CAPABILITY_FAMILIES)
def test_soup_scores_zero_on_capability(capability):
    result = score_record(KEYWORD_SOUP, {"capability": capability})
    assert result["keyword_soup_detected"] is True, f"{capability}: soup not detected"
    assert result["normalized_score"] == 0.0, (
        f"{capability}: keyword soup scored {result['normalized_score']}, expected 0.0"
    )


# ── 3. good prose scores non-zero ────────────────────────────────────────────

@pytest.mark.parametrize("capability", ["reasoning", "planning", "critique"])
def test_prose_scores_nonzero(capability):
    result = score_record(GOOD_PROSE, {"capability": capability})
    assert result["keyword_soup_detected"] is False
    assert result["normalized_score"] > 0.0, (
        f"{capability}: genuine prose scored 0.0 — rubric too strict"
    )


# ── 4. soup flag present in score_record output ───────────────────────────────

def test_soup_flag_present_in_result():
    result = score_record(GOOD_PROSE, {"capability": "reasoning"})
    assert "keyword_soup_detected" in result, "keyword_soup_detected missing from score_record output"


def test_soup_flag_present_in_retention_result():
    from scorers.rubric import _score_retention
    result = _score_retention(GOOD_PROSE, {"capability": "continuity"})
    assert "keyword_soup_detected" in result, "keyword_soup_detected missing from _score_retention output"


# ── 5. benchmark diversity — no scenario-N templates ─────────────────────────

def _load_tasks(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def _template(prompt: str) -> str:
    """Normalise numbers so 'scenario 1' and 'scenario 2' share a template."""
    return re.sub(r'\d+', 'N', prompt.strip())


@pytest.mark.parametrize("bench_file", [
    ROOT / "benchmarks" / "reasoning" / "seed_tasks.jsonl",
    ROOT / "benchmarks" / "quantization_retention" / "seed_tasks.jsonl",
])
def test_benchmark_no_template_duplicates(bench_file: Path):
    tasks = _load_tasks(bench_file)
    templates = [_template(t["prompt"]) for t in tasks]
    unique = set(templates)
    assert len(unique) == len(tasks), (
        f"{bench_file.name}: {len(tasks)} tasks but only {len(unique)} unique templates. "
        f"Duplicated: {[t for t in templates if templates.count(t) > 1][:3]}"
    )


# ── 6. all benchmark tasks have unique ids and non-empty prompts ──────────────

@pytest.mark.parametrize("bench_file", sorted(
    (ROOT / "benchmarks").rglob("*.jsonl")
))
def test_benchmark_task_ids_unique(bench_file: Path):
    tasks = _load_tasks(bench_file)
    if not tasks:
        pytest.skip("empty benchmark file")
    ids = [t.get("id", "") for t in tasks]
    assert len(ids) == len(set(ids)), f"{bench_file}: duplicate task ids: {[i for i in ids if ids.count(i)>1]}"


@pytest.mark.parametrize("bench_file", sorted(
    (ROOT / "benchmarks").rglob("*.jsonl")
))
def test_benchmark_prompts_non_empty(bench_file: Path):
    tasks = _load_tasks(bench_file)
    for t in tasks:
        assert t.get("prompt", "").strip(), f"{bench_file}: task {t.get('id')} has empty prompt"


# ── 7. incumbent model does not return identical output for all reasoning tasks ─

def test_reasoning_tasks_produce_diverse_responses():
    """The model must not return the exact same string for every task."""
    from adapters.exemplar_adapter import ExemplarAdapter
    adapter = ExemplarAdapter(
        artifact=str(ROOT / "exports/candidates/arc_governed_v6_conversation/exemplar_train/exemplar_model.json")
    )
    tasks = _load_tasks(ROOT / "benchmarks" / "reasoning" / "seed_tasks.jsonl")
    responses = [adapter.generate(t["prompt"], context={"capability": "reasoning"}).text for t in tasks]
    unique_responses = set(responses)
    assert len(unique_responses) > 1, (
        f"All {len(responses)} reasoning tasks returned identical output — "
        "benchmark cannot distinguish model behaviours"
    )
