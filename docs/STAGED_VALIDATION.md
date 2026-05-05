# Staged validation protocol — operator-sourced learning signal

This document defines the six acceptance stages LLMBuilder uses to validate
that live-deployment data from the
[ARC GitHub AI Operator](https://github.com/GareBear99/gh-ai-operator)
is actually improving the `critique` capability. Each stage has an explicit
pass criterion and an explicit failure mode. No stage passes by assertion.

The intent is alignment with established engineering-validation practice:
evidence-first, measurable, auditable, with adversarial review folded in at
every step.

## Stage 1 — Contract correctness (schema)

**Claim**: every record the operator emits conforms to this repository's
`data/<capability>/seed_examples.jsonl` schema without translation.

**Evidence required**:
- `scripts/ingest_operator_reviews.py --strict` exits 0 on the emitted
  JSONL line.
- The record satisfies `tests/test_basic.py::test_training_record_schema_matches_llmbuilder_seed`
  (operator-side) **and** the schema assertions baked into the round-trip CI.

**Failure mode**: schema drift on either side turns CI red.

**Status on main**: **PASSED**. Verified automatically by
`gh-ai-operator/.github/workflows/loop-integration.yml` on every push.

## Stage 2 — Representativeness of the sample

**Claim**: operator-sourced records span the full difficulty range, not a
single easy/medium cluster, and carry a diversity of verdicts.

**Evidence required**:
- Across the first 50 records:
  - At least one record at each `difficulty ∈ {easy, medium, hard}`.
  - At least three distinct verdict labels present.
  - At least three distinct `provenance.target_url` values (not the same
    repo 50 times).

**Failure mode**: corpus dominated by a single repo/difficulty signals the
model will overfit to one shape of critique.

**Status on main**: pending sufficient ingested records.

## Stage 3 — Provenance auditability

**Claim**: every training record can be traced back to a specific live-deployment
event in public auditable form.

**Evidence required**:
- Each record has `provenance.source`, `provenance.emitted_at`, and
  `provenance.target_url` fields populated.
- Each record's corresponding GitHub Actions run in `gh-ai-operator` still
  exists and holds the `llmbuilder-training-export` artifact.
- Where a Portfolio issue triggered the run, that issue is linked in
  `docs/OPERATOR_EVIDENCE.md`.

**Failure mode**: an unverifiable record in the training corpus. If a record's
origin cannot be cited, it must be quarantined from Gate v2 runs.

**Status on main**: **PASSED** for the records present today (entry #1,
FreeEQ8). Enforced going forward by `scripts/ingest_operator_reviews.py`
schema validation.

## Stage 4 — Self-consistency across identical targets

**Claim**: two independent operator runs over the same target at the same
commit produce the same coarse verdict and an overlapping finding set.

**Evidence required**:
- Re-trigger `gh-ai-operator`'s `ai-review-dispatch.yml` twice against the
  same `target_url`.
- Verdict label matches exactly.
- Finding text Jaccard overlap ≥ 0.7 over finding strings.

**Failure mode**: the operator is non-deterministic above its acceptable
noise floor; Gate v2 cannot rely on its signal.

**Status on main**: pending two runs against a stable target after the
live-deployment PATs are set.

## Stage 5 — A/B proof of learning on the critique slice

**Claim**: training a candidate on the operator-enriched corpus yields a
measurably better critique-slice score than training on the curated seed
alone, without regressing other capabilities.

**Protocol**:
1. Freeze a snapshot of `data/critique/seed_examples.jsonl` → baseline
   corpus **B**.
2. Append `data/critique/operator_reviews.jsonl` (≥ 50 records) → enriched
   corpus **E**.
3. Train two identical candidates under identical RNG, arch, and compute
   budget. Only the training data differs.
4. Score both candidates against the 142-task benchmark, recording the
   per-capability slice breakdown.
5. Compute **Δ_critique = E_score − B_score** on the `critique` slice.

**Pass criteria**:
- `Δ_critique > 0`, i.e. strictly better on the target slice.
- `max_regression` across all other capability slices ≤ **0.5 pp**.
- No hard-reject floor violation (Gate v2 discipline applies).

**Failure mode**: if `Δ_critique ≤ 0` or regression ceiling is breached, the
operator-sourced corpus does not improve the model and should be ablated
from the promotion path. Corrections lane records get weighted up and the
protocol re-runs.

**Status on main**: pending ≥ 50 ingested records.

## Stage 6 — Blind evaluation against a human baseline

**Claim**: the candidate trained on operator-enriched data produces critique
outputs that a human reviewer judges at least as useful as the baseline
candidate, evaluated blind.

**Protocol**:
1. Hold out 10 public repositories not present in either corpus.
2. Have both candidates (baseline B and enriched E) produce a critique for
   each held-out repo.
3. Present the 20 critiques in randomized order to a human reviewer who is
   blind to which candidate produced which critique.
4. Reviewer scores each critique on three axes: *specificity*,
   *usefulness*, *absence of invention*.
5. Compute win-rate for E over B across the 10 repos on each axis.

**Pass criteria**:
- E wins on at least 6 of 10 repos on **specificity**.
- E wins on at least 6 of 10 repos on **usefulness**.
- E's *invention-rate* is less than or equal to B's (the enriched model is
  not hallucinating more).

**Failure mode**: if E does not dominate in at least two of three axes, the
enriched corpus is not clearly better and the promotion is rejected.

**Status on main**: pending completion of stages 2–5.

## Summary table

| Stage | Claim | Status |
|---|---|---|
| 1 | Contract correctness | **PASSED** (automated on every push) |
| 2 | Sample representativeness | pending ≥ 50 records |
| 3 | Provenance auditability | **PASSED** for entry #1 |
| 4 | Self-consistency | pending two identical-target runs |
| 5 | A/B learning on critique slice | pending stages 2 + 4 |
| 6 | Blind evaluation vs human | pending stage 5 |

## Reporting

Each stage's result must be reproducible from an explicit command or
workflow run. Results are appended to `docs/OPERATOR_EVIDENCE.md` as they
are earned, with the date, the Portfolio issue(s) involved, and the
commands/run IDs that produced the measurement.

Stages 1–3 are under automated test today; stages 4–6 require the live-
deployment secrets to be set and sufficient ingested records to accumulate
before they can be exercised.
