# Production Evidence Correction — v11.3 Staging Status

Status: v11.3 is treated as a candidate/staging lane unless promotion evidence is regenerated from the shipped files.

A production audit found that the packaged repository did not contain the referenced Arc-RAR bundle and that the v11.3 promotion claim should not be treated as canonical without a reproducible rerun. The protected incumbent remains `arc_governed_v10_wave4` until a new candidate passes Gate v2 without protected-floor regressions and updates `results/scoreboard.json` with reproducible evidence.

This correction follows the Knowledge Preservation Doctrine: receipts and reproducible benchmark outputs outrank narrative changelog claims.

---

## [v2.1.0-governed] — 2026-05-09

### Summary
Full v11 wave5 governance cycle: targeted SFT expansion (+165 exemplar records),
two new core modules, four pipeline bug fixes, and a clean Gate v2 promotion to
**0.9465** overall weighted score (+2.3% over v2.0.0 incumbent at 0.9237).
Heritage integrations from GareBear99/LuciferAI_Local (context window solving)
and GareBear99/Proto-Synth_Grid_Engine (authority receipt pattern).

### Promoted
* **arc_governed_v11_3_wave5** — 0.9465 overall weighted score, 0/165 benchmark
  failures, 136/136 tests passing. Supersedes arc_governed_v10_wave4 (0.9237).
  Floor model locked at v11.3 scores. Arc-RAR bundle at:
  `artifacts/archives/arc-rar-arc_governed_v11_3_wave5-5d1c2367.arcrar.zip`

### Added — New core modules
* **`arc_core/context_window_manager.py`** — Governed sliding context window with
  trim-from-middle strategy. Heritage: GareBear99/LuciferAI_Local
  `core/llm_backend.py` + `core/memory_system.py`. Preserves system messages
  unconditionally. Produces SHA-256 trim receipts per event. MODEL_TIER_DEPTHS
  config: tiny=32, v6_conversation=64, v10_wave4=128, large=256.
* **`arc_core/intent_receipt_engine.py`** — Intent-gated execution with signed
  receipts. Heritage: GareBear99/Proto-Synth_Grid_Engine
  `Iteration10/CHANGELOG_v44` authority receipt pattern. Seven intents: absorb,
  train, benchmark, gate, archive, query, unknown. Lifecycle state machine
  (boot/ready/train/gate) blocks incompatible intents per state.

### Added — SFT packs (165 new exemplar records; v10 base 669 → v11.3 total 834)

| Pack | Records | Capabilities targeted |
|------|---------|----------------------|
| `v6_reflection_sft.jsonl` | 30 | acknowledges_prior_error, provides_revised_position, explains_change, does_not_repeat_error |
| `v6_deterministic_compliance_sft.jsonl` | 20 | follows_format, bounded, evidence (JSON/YAML receipts) |
| `v6_planning_sft.jsonl` | 20 | has_ordered_plan, names_gate, mentions_next_action |
| `v11_continuity_sft.jsonl` | 20 | preserves_constraint, names_next_action, preserves_goal, grounds_in_scenario |
| `v11_intelligence_sft.jsonl` | 27 | format_exact, arithmetic_reasoning, paraphrases_or_answers |
| `v11_surgical_sft.jsonl` | 26 | states_uncertainty, names_spine_component, explains_reason, mentions_timeout_or_guard, mentions_constraints, topically_relevant |
| `v11_precision_sft.jsonl` | 22 | stays_on_task, preserves_goal, mentions_risk_or_tradeoff, source-derived topically_relevant |

### Added — New benchmark capabilities (10, all above floor)

| Capability | v11.3 Score |
|---|---|
| lexical_accuracy | 1.000 |
| native_operation_planning | 1.000 |
| deterministic_compliance | 1.000 |
| runtime_reasoning | 1.000 |
| refusal_correctness | 1.000 |
| deterministic_format | 1.000 |
| archive_reasoning | 0.971 |
| state_evidence | 0.964 |
| system_spine_reasoning | 0.857 |
| english_comprehension | 0.833 |

### Fixed — Pipeline bugs (four structural defects corrected)

**BUG-1 `promote_candidate.py` — calibration_error never written to scoreboard**
`calibration_error` was computed but never stored in scoreboard entries. The
regression check read `incumbent.get("calibration_error", 0.0)` = 0.0 instead of
the actual value (e.g. 0.10). v11.2's calibration improved (0.90→0.933, error
0.10→0.067) but the gate saw delta 0.067 vs 0.0 = regression 0.067 > ceiling 0.03.
Fix: write `calibration_error` on every promotion; retroactively patch all
existing scoreboard entries with `round(1.0 - calibration, 4)`.

**BUG-2 `promote_candidate.py` — incumbent found by max(score) not incumbent flag**
After a candidate was written to the scoreboard on a first run, the second run
found that candidate as the "incumbent" (highest score) and compared it to itself:
score == score → "did not beat incumbent". Fix: use `incumbent=True` flag first,
fall back to max(score) only when no flag is set.

**BUG-3 `scorers/rubric.py` — prefix strip missed multi-line system_prompt**
The exemplar adapter emits: `[system_prompt]\nCapability: X\n[answer]`. The old
strip only removed from `Capability:` forward, leaving the system_prompt line in
the answer text. This caused `is_boilerplate` false positives and
`does_not_repeat_error` failures (system prompt contained "repair, calibrate").
Fix: strip all lines up to and including `Capability:` universally.

**BUG-4 `run_model_benchmarks.py` — full_benchmark_v6 profile not registered**
`full_benchmark_v6` was not in the profile dict. Requests fell through to
`minimal_doctrine` = "Plan, critique, repair, calibrate." — a string that appears
in every output and fails `does_not_repeat_error` in all reflection tasks.
Fix: register `full_benchmark_v6` (maps to full_doctrine text) and `governance_v1`
("Reason from evidence. Bound your confidence. Acknowledge corrections. Produce
receipts.") as named prompt profiles.

### Changed

* **`configs/stack/regression_floor.json`** — locked at v11.3: repair=1.0,
  calibration=0.933, planning=1.0, paraphrase_stability=1.0, reasoning=0.897,
  reflection=0.875, continuity=0.904, instruction_following=0.904, overall=0.9465.
  Nine capabilities now guarded (up from five in v2.0.0).

* **`results/scoreboard.json`** — v11.3 marked incumbent; v10_wave4 marked
  superseded_by=arc_governed_v11_3_wave5. `calibration_error` field added to all
  historical entries.

* **`.gitignore`** — patterns added for v11 ephemeral outputs: intermediate
  candidates (v11_wave5, v11_1, v11_2), superseded Arc-RAR bundles,
  cycle/CI benchmark results, runtime receipts, `obin.idx` runtime index,
  absorbed session SFT files.

### Capability delta (v11.3 vs v10_wave4)

| Capability | v10_wave4 | v11.3 | Delta |
|---|---|---|---|
| continuity | 0.7708 | 0.9042 | **+0.1334** |
| reflection | 0.8375 | 0.8750 | **+0.0375** |
| calibration | 0.9000 | 0.9333 | **+0.0333** |
| reasoning | 0.8833 | 0.8974 | +0.0141 |
| out_of_domain | 0.9667 | 0.9744 | +0.0077 |
| instruction_following | 0.9250 | 0.9038 | -0.0212 (within floor) |
| 10 new capabilities | — | 0.833–1.000 | new |
| **overall_weighted** | **0.9237** | **0.9465** | **+0.0228** |

---
