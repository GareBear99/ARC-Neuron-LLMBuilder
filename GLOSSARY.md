# Glossary

Every ARC-specific term used across the project, alphabetized. This doubles as onboarding and as a search index.

## A

**Adapter**
The standardized interface for a model backend. Any class implementing `adapters.base.ModelAdapter` can be driven by the canonical pipeline. Built-ins: `exemplar`, `heuristic`, `echo`, `command`, `llama_cpp_http`, `openai_compatible`.

**ANCF (ARC Neuron Canonical Format)**
A binary envelope wrapping a GGUF file with embedded JSON metadata. Layout: 4-byte magic `ANCF`, 4-byte version, 8-byte meta-len, 8-byte gguf-len, metadata bytes, GGUF bytes. Used for canonical model-artifact storage.

**Arc-RAR bundle**
A ZIP archive containing a promoted candidate's full lineage: manifests, receipts, PyTorch checkpoint, GGUF export, exemplar artifact, and a SHA-256 index. Readable in isolation via `runtime.learning_spine.read_arc_rar_manifest`.

**Archive-only**
A Gate v2 decision state. The candidate did not beat the incumbent (or violated a regression ceiling) but is preserved in the scoreboard for future analysis. The incumbent is untouched.

**Attribution boundary**
The governance principle that each component, capability, and decision must trace back to a single owner. Merging two receipts into one breaks attribution and is rejected.

## B

**Benchmark suite**
The 142-task evaluation set organized across 14 capability families: reasoning, planning, compression, paraphrase_stability, calibration, english_understanding, critique, out_of_domain, quantization_retention, repair, instruction_following, intelligence, continuity, reflection. (Rebuilt in v2.0.0-audited — 4 benchmark files replaced with genuine diverse tasks.)

**Block size**
The context window length of a transformer tier. Tiny=64, Small=128, Base=256. All measured in tokens (which for the byte-level native models are raw bytes).

## C

**Candidate**
A newly trained model not yet promoted. Has a receipt, a PyTorch checkpoint, a GGUF export, and an exemplar artifact, but has not yet passed Gate v2.

**Canonical conversation pipeline**
The single path every user interaction must take: `user prompt → adapter.generate() → ConversationRecord → auto-tag → Omnibinary mirror → session history → return`. Implemented in `runtime/conversation_pipeline.py`.

**Cognition Core**
The model-growth lab. Owns training, benchmarking, scoring, and gate logic. Its canonical repo is [arc-cognition-core](https://github.com/GareBear99/arc-cognition-core).

**Continuity shell**
The deterministic runtime that preserves state, directives, and receipts across sessions. Its canonical repo is [arc-lucifer-cleanroom-runtime](https://github.com/GareBear99/arc-lucifer-cleanroom-runtime).

**Contradiction flag**
When the language module encounters a new high-trust term value that differs from an existing same-trust-or-higher record, it marks the new record `contradicts=<prior_id>` and does not auto-approve it.

## D

**Decision state**
One of four Gate v2 outcomes: `promote`, `archive_only (tie)`, `archive_only (regression)`, `reject`.

**Distillation wave**
A training run that uses SFT pairs harvested from prior conversation, reflection, and terminology activity as its corpus.

## E

**Event ID**
The SHA-256-addressable identifier for any event in the Omnibinary ledger. Always retrievable in O(1) via the sidecar `.idx` file.

**Exemplar adapter**
A cosine-retrieval adapter over training records. Given a prompt, returns the top-k closest training targets. Default adapter for the native governed lane.

## F

**Floor model**
A never-below baseline locked from the current incumbent with a 10% safety margin. Every future candidate must clear it on every guarded capability. Managed by `runtime/floor_model.py`.

**Frozen role**
One of the seven roles in the ARC ecosystem (ARC-Core, Cleanroom Runtime, Cognition Core, Language Module, OmniBinary, Arc-RAR, LLMBuilder). Roles never swap responsibilities.

## G

**Gate v2**
The regression-aware promotion gate. Four layers: hard-reject floor, floor model, regression ceilings, beat-the-incumbent. Implemented in `scripts/execution/promote_candidate.py`.

**Governance invariants**
Ten rules that hold across every Gate v2 run. Listed in [GOVERNANCE_DOCTRINE.md](./GOVERNANCE_DOCTRINE.md#the-governance-invariants).

**GGUF**
Binary inference format from the GGML ecosystem, used for local model deployment with llama.cpp and compatible runtimes. ARC-Neuron LLMBuilder emits GGUF v3 via `arc_tiny/gguf_io.py`.

## H

**Hard-reject floor**
The lowest governance bar. Any candidate that fails `repair_success ≥ 0.30` or `failure_rate ≤ 0.25` is rejected before any other check.

**Heuristic adapter**
A synthetic smoke-test adapter. Marked `promotable=False` so it can never become an incumbent.

## I

**Incumbent**
The current best model, selected by highest `overall_weighted_score` among promotable candidates in the scoreboard. Only a real `promote` decision can change the incumbent.

**Incumbent guard**
The governance rule that archive-only and reject decisions never clear incumbent flags. Only a real promotion does.

## L

**Language absorption**
The runtime layer that extracts terminology, capability signals, and continuity signals from each conversation turn. Implemented in `runtime/language_absorption.py`.

**Language module**
The living truth spine. Stores terms with provenance, trust ranks, and contradiction flags. Its canonical repo is [arc-language-module](https://github.com/GareBear99/arc-language-module).

## N

**Non-promotable adapter**
An adapter that can never become an incumbent regardless of score. Current list: `heuristic`, `echo`.

## O

**OBIN v2**
The indexed Omnibinary ledger format. Layout: 4-byte magic `OBIN`, 4-byte version, 8-byte timestamp, then repeated `(event-id string, blob-len uint32, blob bytes)` records. Sidecar `.idx` JSON maps `event_id → byte_offset` for O(1) lookup.

**Omnibinary**
The binary mirror of source truth. Runtime-ledger substrate with indexed lookup, SHA-256 integrity, and append-safe writes. Its canonical repo is [omnibinary-runtime](https://github.com/GareBear99/omnibinary-runtime).

## P

**Promotion receipt**
The JSON record written to `reports/promotion_decision.json` capturing every input and decision of a Gate v2 run.

**Provenance**
Metadata attached to every absorbed term: adapter, receipt_id, turn_id, conversation_id, timestamp. Required for restoring the exact source of any stored fact.

## R

**Receipt**
An addressable JSON record attached to any governed action. Every conversation turn, terminology change, and promotion decision produces one.

**Reflection loop**
A draft→critique→revise wrapper for any `ModelAdapter`. Produces three stages (draft, critique, revised) and emits the final answer. Implemented in `runtime/reflection_loop.py`.

**Regression ceiling**
The per-capability maximum allowed drop versus the incumbent. A candidate that exceeds any ceiling archives-only with explicit attribution.

## S

**Scoreboard**
The JSON file at `results/scoreboard.json` that records every candidate the gate has evaluated, with scores, decisions, and incumbent flags.

**SFT (Supervised Fine-Tuning)**
Training examples of the form `{prompt, target, capability}` used to shape model behavior.

## T

**Trust rank**
The confidence class of a terminology record. Ranked highest to lowest: `manual_correction` (100) > `correction` (100) > `definition` (70) > `canonical` (65) > `alias` (55) > `relationship` (50) > `observation` (30).

## W

**Weak-term filter**
The language absorption rule that rejects terms shorter than 3 characters or lacking at least one word character. Prevents fragment pollution of the language module.
