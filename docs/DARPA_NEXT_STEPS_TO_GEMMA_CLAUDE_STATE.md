# DARPA-Style Next Steps Toward Gemma/Claude-Class Behavior

This document defines the professional path from the current ARC-Neuron/LLMBuilder production candidate to a stronger local model program. It does **not** claim ARC-Neuron is already frontier-class. It defines the governed ladder needed to approach that behavior safely.

## Current honest baseline

- Current reproducible incumbent: `arc_governed_v10_wave4` at 0.9237.
- v11.3/wave5 is candidate/staging until promotion evidence regenerates from shipped files and Gate v2 passes.
- Current native models are tiny/small reference brains and governance proof artifacts, not Claude/Gemini/Gemma-scale checkpoints.

## Mission objective

Reach a model-development loop that can produce increasingly capable local candidates while preserving:

- lineage,
- data provenance,
- benchmark context,
- model receipts,
- license boundaries,
- rollback paths,
- and old capability floors.

## Phase 0 — freeze the truth spine

Before any new dataset or weights are introduced:

1. Freeze current incumbent and floor model.
2. Freeze benchmark pack and scoring rubric.
3. Freeze dataset manifests.
4. Freeze promotion receipts.
5. Freeze license state.
6. Generate a source hash manifest.

This establishes the pre-3.0 reference checkpoint.

## Phase 1 — create v2 candidate isolation

Experimental datasets and new weights must live in:

```text
models/candidates/v2/
datasets/v2/
benchmarks/v2/
receipts/v2/
scoreboards/v2/
```

They may not overwrite the incumbent or floor lanes.

## Phase 2 — build the dataset rings

Use dataset rings instead of one uncontrolled mixture:

| Ring | Purpose | Trust |
|---|---|---|
| Ring 0 | ARC-native docs, receipts, operator corrections | highest |
| Ring 1 | general instruction following | medium |
| Ring 2 | reasoning, planning, tool-use, code repair | medium |
| Ring 3 | lexical simplicity, empathy, support language | restricted |
| Ring 4 | technical domain knowledge | medium |
| Ring 5 | refusal, licensing, safety, PII, dataset law | high-value guardrail |

## Phase 3 — train small first

Do not attempt a large release first. The correct ladder is:

1. small local candidate,
2. deterministic training recipe,
3. benchmark run,
4. candidate-vs-incumbent comparison,
5. floor breach check,
6. archive/reject/promote receipt,
7. repeat for three stable cycles.

Only then scale model size and dataset volume.

## Phase 4 — add critique/revise behavior

Gemma/Claude-style usefulness comes from more than raw answers. ARC candidates should train the shape:

```text
intent -> constraints -> draft -> critique -> revised answer -> receipt
```

This is the ARC-native form of high-quality assistant behavior.

## Phase 5 — memory regression

Each learned doctrine must be retested by asking the same or equivalent question later. The model should change only when the saved doctrine justifies the change.

See `docs/MODEL_MEMORY_EVALUATION_PROTOCOL.md`.

## Phase 6 — 3.0 protected release

The 3.0 release should only happen when all of the following are true:

- v2 candidate lane beats or matches protected floors,
- dataset manifests are complete,
- license boundaries are explicit,
- trained weights have receipts,
- benchmark and scoreboard are reproducible,
- rollback bundle exists,
- and public docs accurately distinguish proof-of-loop, candidate model, and actual released weights.
