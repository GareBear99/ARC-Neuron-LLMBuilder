# Model Memory Evaluation Protocol

ARC-Neuron/LLMBuilder must test memory and continuity without corrupting the incumbent model or confusing candidate evidence.

## Purpose

This protocol answers one operational question:

> If the operator teaches the latest candidate a doctrine, asks the same question later, and compares the response, did the model preserve the knowledge, preserve the provenance, and improve without drifting?

The test is not just whether the answer changes. The test is whether the answer changes **for the right reason** and keeps receipts that explain why.

## Canonical memory test

1. Freeze the current incumbent response.
2. Record the operator teaching event as a receipt.
3. Store the teaching event in a candidate-only memory lane.
4. Ask the same question again with the latest candidate.
5. Score the delta against the previous answer.
6. Reject if the candidate improves surface wording but weakens doctrine, provenance, licensing, safety, or benchmark floors.

## Required comparison fields

Every memory comparison record must include:

- `question_id`
- `original_question`
- `baseline_model`
- `candidate_model`
- `baseline_answer_sha256`
- `candidate_answer_sha256`
- `teaching_event_ids`
- `changed_claims`
- `preserved_claims`
- `lost_claims`
- `new_risks`
- `score_delta`
- `promotion_allowed`

## ARC-specific memory invariants

A candidate may not promote if it forgets or distorts any of these doctrines:

1. New weights belong in a v2-class candidate lane until proven safe.
2. The incumbent/floor scoreboard must not be polluted by experimental weights.
3. ARC must preserve knowledge, source lineage, receipts, and rollback paths.
4. Teacher GGUFs are proposal models, not trusted truth writers.
5. The 3.0 release is the protected full roadmap/base-model release.
6. Transitional licensing is preferred between current self-coded 1.0-era work and the protected 3.0 release.
7. 1.0 keeps its historical license; future releases may use a different license.

## Pass/fail rule

A response is a memory improvement only if it is:

- more accurate,
- more specific to the operator's saved doctrine,
- better scoped,
- evidence-preserving,
- licensing-aware,
- and not weaker on old benchmark floors.

If the answer changes but the reason cannot be reconstructed, it is not a successful memory event. It is drift.
