# Changelog

All notable changes to ARC-Neuron LLMBuilder are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
with a descriptive suffix for major doctrine milestones.

---

## [v1.0.0-governed] — 2026-04-22

### Doctrine milestone
**Growth loop closed end-to-end.** Three governed promotions in a row, each with distinct evidentiary cause. The last promotion (`arc_governed_v6_conversation`) was trained exclusively from a corpus the canonical conversation pipeline harvested itself — no hand-authored SFT. All four Gate v2 decision states (promote, archive-only tie, archive-only regression, reject) have now fired lawfully on real runs.

### Added
- `runtime/learning_spine.py` — OBIN v2 indexed Omnibinary ledger with O(1) event lookup, SHA-256 integrity verification, automatic index rebuild on drift, append-safe semantics, and measured throughput of 6,600+ events/sec append and 8,900+ lookups/sec.
- `runtime/conversation_pipeline.py` — canonical single-path pipeline: intent → adapter → receipt → Omnibinary mirror → training-eligibility tag → archive summary.
- `runtime/reflection_loop.py` — draft → critique → revise wrapper for any `ModelAdapter`.
- `runtime/language_absorption.py` — automatic terminology extraction from conversation with provenance, trust ranks, contradiction detection, and weak-term filter.
- `runtime/terminology.py` — live terminology store with definition/alias/correction/canonical/relationship extraction, Omnibinary mirror, and SFT training export.
- `runtime/floor_model.py` — regression floor that locks capability baselines from the current incumbent; `--set-floor --from-scoreboard` to relock after promotion.
- `specs/promotion_gate_v2.yaml` + `specs/benchmark_schema_v2.yaml` — Gate v2 doctrine with hard-reject floor, regression ceilings, comparison classes, and quantization ladder.
- `scorers/rubric.py` — task-aware rubric scorer with 23 capability buckets including new lanes for english_understanding, instruction_following, intelligence, out_of_domain, reflection, continuity, lexical_accuracy, archive_reasoning, runtime_reasoning, state_evidence, system_spine_reasoning, native_operation_planning, deterministic_compliance/format, refusal_correctness.
- `scripts/training/train_arc_native_candidate.py` — end-to-end native training with real weights: corpus mining, 90/10 split, AdamW + cosine LR, gradient clipping, val perplexity, `.pt` + GGUF v3 export, exemplar sidecar for benchmark harness.
- `scripts/execution/promote_candidate.py` — Gate v2 implementation with hard-reject/floor/regression/tie-archive/incumbent-guard logic and automatic Arc-RAR bundling on promote.
- `scripts/ops/run_n_cycles.py` — N-cycle governed repeatability runner with stability verdict.
- `scripts/ops/run_proof_workflow.py` + `demo_proof_workflow.py` — single-script end-to-end proof covering term teaching, conversation, training, benchmark, gate, archive, and Omnibinary verification.
- `scripts/ops/benchmark_omnibinary.py` — measures append throughput, O(1) lookup latency, scan speed, rebuild time, storage efficiency, and restore fidelity.
- `scripts/ops/generate_reflection_sft.py` — produces draft → critique → revise SFT pairs for subsequent training waves.
- `scripts/ops/absorb_session.py` — one-command session absorption into terminology, Omnibinary, pipeline, and training export.
- `scripts/ops/bundle_promoted_candidate.py` — Arc-RAR bundling with manifests, receipts, checkpoint, GGUF, and SHA-256 index.
- `scripts/ops/bootstrap_keys.py` — idempotent runtime-secret generator; `--force` and `--dry-run` supported; `0o600` permissions on Unix.
- `benchmarks/english_understanding/`, `benchmarks/instruction_following/`, `benchmarks/intelligence/`, `benchmarks/out_of_domain/` — 42 new benchmark tasks bringing the total to 165 across 16 capability families.
- `tests/test_omnibinary_pipeline_promotion.py` — 20+ tests covering indexed append/get/scan/verify/export, pipeline canonical path, Omnibinary mirror integrity, auto-tag, label, training export, Gate v2 decision branches, Arc-RAR roundtrip, ANCF roundtrip.
- `tests/test_arc_core_fixes.py` — shared-transformer import identity, weight tying, block-size guard, param count, rubric guards, GGUF lossless roundtrip, native training smoke.
- Production documentation: README, ARCHITECTURE, GOVERNANCE_DOCTRINE, QUICKSTART, USAGE, RELEASE_NOTES_v1.0.0.

### Changed
- `arc_tiny/model.py` and `arc_neuron_small/model.py` reduced to thin presets over the single `arc_core.transformer` implementation — eliminates copy-paste drift between tiers.
- `scorers/rubric.py` hardened against non-dict `reference` fields; `avoids_false_certainty` and `avoids_additional_claims` now require substantial text before crediting the negative check (prevents short/empty outputs inflating calibration scores).
- `scripts/training/train_arc_native_candidate.py` emits single-line compact JSON for clean subprocess parsing; also generates an exemplar sidecar artifact so the benchmark harness runs without llama.cpp.
- `scripts/execution/promote_candidate.py` non-promotable adapter filter — `heuristic` and `echo` adapters can never become incumbents; scoreboard incumbent flags only clear on real promotion, never on archive-only or reject.
- `runtime/learning_spine.py` default `index_flush_every=1` for single-appender safety; batch mode available for high-throughput writes via explicit `flush()`.
- `scripts/training/train_lora_candidate.py` routing table — detects ARC-native bases (`arc_neuron_small`, `arc_tiny`, etc.) and delegates to real training; unknown bases hit the scaffold path.

### Security
- `.gitignore` hardened to exclude `*.key`, `*.pem`, `*.p12`, `**/data/keys/*`, SQLite runtime DBs, and large binary artifacts (`.gguf`, `.pt`, `.safetensors`, `.obin`).
- `scripts/ops/bootstrap_keys.py` is the single source of truth for generating runtime secrets; keys are never committed.
- Dead code removed from `arc_tiny/gguf_io.py` (`if len(payload_parts) == 0: pass` block).

### Evidence recorded in this release
- **Tests**: 87/87 passing
- **Incumbent**: `arc_governed_v6_conversation` at 0.7333 (165-task benchmark, 0 failures)
- **Promotion history**: v1 (0.6122) → v2 (0.6247) → v4 (0.7128) → v5 (0.7169) → v6_conversation (0.7333)
- **Regression gate proven**: v7_regressed correctly archived with attributed violations (`reasoning: 0.667 > 0.05`, `critique: 0.250 > 0.06`)
- **Repeatability**: 5/5 STABLE at v5 floor, 3/3 STABLE at v4 floor
- **Omnibinary**: 98 events live, integrity OK, SHA-256 stable across sessions
- **Arc-RAR bundles**: 12 restorable bundles, all manifest-readable

---

## [v0.3.1-alpha] — 2026-04-17

### Added
- ARC-Neuron Small v0.2 prep pipeline.
- Tokenizer growth pack and manifest.
- Cleanroom supervised export loop.
- Expanded benchmark gates for ARC-Neuron Small v0.2.
- Prep ANCF wrapper, Omnibinary ledger, and Arc-RAR archive bundle.

---

## [v0.3.0-alpha] — 2026-04-17 (ARC-Neuron integrated demo)

### Added
- ARC-Neuron Small + Corpus Compiler v1 with unified corpus compilation, native research training/export path, ANCF wrapper, Omnibinary ledger, and Arc-RAR bundle.
- Integrated demo build: trains/exports an ARC-Neuron tiny GGUF from cognition-core plus uploaded ARC stack sources.
- `runtime/learning_spine.py` first cut: Omnibinary ledger, ANCF minting, Arc-RAR bundle helpers.
- Integrated outputs: `.gguf`, `.ancf`, `.obin`, `.arcrar.zip`.
- ARC-Neuron Tiny named GGUF artifact alias, model family doc, Tiny model card, validate+run smoke script.

---

## [v0.1.0-alpha] — initial

### Added
- Cognition-core production alpha scaffold.
- Doctrine, contract, promotion gates v1, dataset policy, benchmark schema v1.
- Execution-first adapter/runtime/scoring/promotion flow.
- MCP-style tool descriptors and screenshot-attachment integration path.
- Production hardening: CI, tests, validation, release bundle generation.
- GGUF backend path, run manifests, experiment tracking, operator docs.

---

[v1.0.0-governed]: https://github.com/GareBear99/ARC-Neuron-LLMBuilder/releases/tag/v1.0.0-governed
[v0.3.1-alpha]: https://github.com/GareBear99/ARC-Neuron-LLMBuilder/releases/tag/v0.3.1-alpha
[v0.3.0-alpha]: https://github.com/GareBear99/ARC-Neuron-LLMBuilder/releases/tag/v0.3.0-alpha
[v0.1.0-alpha]: https://github.com/GareBear99/ARC-Neuron-LLMBuilder/releases/tag/v0.1.0-alpha## [Unreleased] — Audit remediation (2026-04-23)

### Fixed — benchmark integrity
* **reasoning/seed_tasks.jsonl** — replaced 10 word-for-word identical
  "scenario N" variants with 10 genuinely distinct scenarios covering
  cache invalidation, circuit-breaker logic, Gate v2 decisions, patch
  tradeoffs, schema migration safety, path-traversal security, canary
  statistics, CI test-selection failure modes, rollback/schema conflicts,
  and feature-flag consistency.  The incumbent scores 0.550 (was 1.000)
  — a more honest signal.
* **quantization_retention/seed_tasks.jsonl** — replaced 10 "bundle N"
  variants with 10 distinct quantization-reasoning tasks covering
  retention calculations, q8_0-vs-q4_K_M tradeoffs, gate decisions,
  byte-level architecture implications, SHA-256 integrity expectations,
  and RAG interaction effects.

### Changed — rubric hardening (scorers/rubric.py)
* Added `_is_keyword_soup()` guard: a response with no sentence-ending
  punctuation and fewer than 60 words scores 0 on all keyword-presence
  checks regardless of which keywords appear.  Responses shorter than
  80 chars or fewer than 12 words are also flagged.
* All `_contains_any()` calls inside `score_record` and
  `_score_retention` now accept a `soup: bool` parameter; when True,
  content checks short-circuit to False.
* `_is_substantial()` now requires both character length ≥ 80 AND
  sentence-ending punctuation (was: length ≥ 60 only).
* `score_record` and `_score_retention` both return
  `keyword_soup_detected: bool` in their result dicts.
* A pure keyword-dump response ("constraint preserve boundary interface
  risk tradeoff...") that previously scored 1.0 on reasoning, planning,
  critique, repair, calibration, and compression now scores 0.0 on all.
* `SOUP_EXEMPT_CAPABILITIES` frozenset exempts factual-recall capabilities
  (`out_of_domain`, `english_understanding`, `instruction_following`, etc.)
  from the soup guard — short direct answers remain valid there.

### Fixed — test suite
* `tests/test_arc_core_fixes.py` — replaced hard `import torch` at module
  level with `pytest.importorskip("torch")` so the file is collected and
  its non-torch tests run (rubric checks, config checks); torch-dependent
  tests are skipped gracefully when torch is absent rather than erroring
  out and blocking the entire collection.
* **Added `tests/test_audit_remediation.py`** — 54 new tests covering:
  keyword-soup detection on word-lists / empty / single-word inputs;
  soup guard zeroing scores on all 9 prose capability families;
  prose responses scoring non-zero; `keyword_soup_detected` flag present
  in all score paths; benchmark template-diversity (no scenario-N
  duplicates); task-id uniqueness and non-empty prompts across all
  benchmark files; and incumbent model producing diverse responses on
  the new reasoning suite.
* Total test count: **120 passed, 1 skipped** (torch tests deferred).


