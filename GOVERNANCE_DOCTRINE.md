# Governance Doctrine

This document explains **why** the system refuses to promote most candidates and **how** it makes that decision. The governance doctrine is the load-bearing contribution of ARC-Neuron LLMBuilder. The model is only one artifact inside it.

## The core principle

> A candidate may only displace the incumbent if it demonstrably improves the system without regressing on any guarded capability, without breaking any hard-floor constraint, and without losing attribution for why it won.

Everything in this document is derived from that principle.

## The four governance layers

### Layer 1 — Hard-reject floor

The lowest bar. A candidate that fails this floor cannot even be considered, regardless of any other score.

```yaml
hard_reject:
  repair_success_floor:            0.30   # must meet
  failure_rate_ceiling:            0.25   # must not exceed
  quantization_retention_floor:    0.90   # must meet (when quantized)
```

Implementation: `scripts/execution/promote_candidate.py::_hard_reject_check`

Rationale: these are the minimum viable thresholds for the system to be usable at all. A model with 25%+ task failures or near-zero repair capability is not a candidate; it is a defect.

### Layer 2 — Floor model (never-below baseline)

The floor model locks capability baselines from the current incumbent with a 10% safety margin. Every future candidate must clear the floor on every guarded capability.

Guarded capabilities:
- `repair`
- `calibration`
- `planning`
- `compression`
- `paraphrase_stability`
- `overall_weighted_score`
- `failure_rate` (ceiling, not floor)

Implementation: `runtime/floor_model.py::FloorModel.check()`

After a real promotion, the floor is relocked from the new incumbent:

```bash
python3 runtime/floor_model.py --set-floor --from-scoreboard
```

Rationale: incumbents shift over time. The floor prevents slow drift into weirdness — a series of small archive-only candidates that each individually look fine but collectively erode core capability.

### Layer 3 — Regression ceilings

Per-capability maximum allowed drop versus the incumbent. A candidate may trade strength in one lane for strength in another, but no lane may collapse.

```yaml
regression_ceilings:
  repair_success:        0.04
  calibration_error:     0.03    # error, lower is better — ceiling on increase
  reasoning:             0.05
  planning:              0.05
  critique:              0.06
  compression:           0.06
  paraphrase_stability:  0.06
```

Implementation: `scripts/execution/promote_candidate.py::_regression_check`

When a candidate violates a ceiling, the gate records the attribution explicitly:

```
reasoning: candidate=0.333 incumbent=1.000 regression=0.667 > allowed=0.05
critique:  candidate=0.500 incumbent=0.750 regression=0.250 > allowed=0.06
```

This is exactly what fired for `arc_governed_v7_regressed` in the v1.0.0-governed release.

### Layer 4 — Beat the incumbent

After a candidate clears the hard-reject floor, the floor model, and every regression ceiling, it must still beat the current incumbent's **overall weighted score** and **not regress on failure_rate** before promoting.

Ties are archived, not promoted. Identical scores do not displace the incumbent — the rule is strictly "beat," not "match."

## The four decision states

Every Gate v2 run ends in exactly one of these:

### 1. Promote
All four layers cleared. The candidate becomes the new incumbent. A promotion receipt is written. An Arc-RAR bundle is built. The scoreboard is updated to mark the new incumbent; all prior incumbent flags are cleared.

### 2. Archive-only (tie or under-incumbent)
The candidate did not beat the incumbent but also did not violate any regression ceiling or floor. It is preserved in the scoreboard for future analysis. The incumbent is untouched.

### 3. Archive-only (regression violation)
The candidate clipped a regression ceiling. The violations are attributed by capability. It is preserved but cannot promote. The incumbent is untouched.

### 4. Reject
The candidate failed the hard-reject floor or the floor model. It is not added to the scoreboard. No bundle is built. This is a hard rejection — there is no recoverable state.

## The non-promotable adapter rule

Some adapters exist for testing or synthetic smoke checks, not real cognition:
- `heuristic` — keyword-based synthetic responses
- `echo` — echo-back

These adapters can never become incumbents, regardless of score. The filter runs before the incumbent lookup:

```python
_NON_PROMOTABLE = {"heuristic", "echo"}
promotable_models = [
    m for m in scoreboard["models"]
    if m["adapter"] not in _NON_PROMOTABLE
    and m.get("promotable", True) is not False
]
incumbent = max(promotable_models, key=lambda m: m["overall_weighted_score"], default=None)
```

Rationale: a synthetic adapter that happens to score well by keyword-stuffing must not become the baseline every real candidate has to beat.

## The incumbent-guard rule

Archive-only and reject decisions **never** clear incumbent flags. Only a real promotion does:

```python
if promoted:
    for model in deduped:
        model["incumbent"] = False   # clear all prior incumbents
entry["incumbent"] = promoted or (not promoted and not any(m["incumbent"] for m in deduped))
```

Rationale: a streak of archive-only decisions (which is normal after a strong incumbent is locked) must not accidentally leave the scoreboard with no incumbent. The current best is preserved through any number of failed challenges.

## The receipt contract

Every gate decision produces a JSON receipt:

```json
{
  "ok": true,
  "candidate": { "...": "full entry including all scored capabilities" },
  "incumbent_before": { "...": "the incumbent this candidate challenged" },
  "promoted": true,
  "decision": "promote",
  "decision_reason": "Candidate improved weighted score with no disqualifying regressions.",
  "hard_rejected": false,
  "floor_violations": [],
  "regression_violations": [],
  "arc_rar_bundle": "artifacts/archives/arc-rar-...",
  "gate_version": 2
}
```

This receipt is written to `reports/promotion_decision.json` (latest) and per-cycle reports in `reports/cycle_*_promo.json`. Every receipt is addressable after the fact.

## The Arc-RAR bundle contract

On promote or archive-only (not on reject), the candidate is packaged into a SHA-256-indexed ZIP archive:

```
arc-rar-<candidate>-<hash>.arcrar.zip
├── manifest.json               — bundle-level metadata with SHA-256 index
├── promotion_report.json       — the decision receipt
├── candidate_entry.json        — the scoreboard entry
├── lora_train_manifest.json    — training stage manifest
├── exemplar_train_manifest.json — exemplar artifact manifest
├── arc_native_<cand>.pt        — PyTorch checkpoint
├── arc_native_<cand>.gguf      — GGUF v3 export
├── exemplar_model.json         — retrieval artifact
├── receipts/*.json             — runtime receipts
└── reports/*.json              — benchmark and training reports
```

Readable in isolation with `runtime.learning_spine.read_arc_rar_manifest(path)`. Any prior candidate can be restored from its bundle at any time.

## The Omnibinary mirror contract

Every gate decision and every conversation turn is mirrored into the Omnibinary ledger:

- `event_type = "conversation_turn"` — canonical pipeline turns
- `event_type = "terminology_event"` — language module term writes
- Promotion receipts are addressable by their own SHA-256

O(1) lookup by `event_id` via the sidecar `.idx` file. Integrity verified by SHA-256 on both the ledger file and per-event hashes. Append-safe — the index rebuilds automatically from the ledger on corruption.

## What the governance does NOT do

The doctrine is deliberately narrow. Things it does not try to decide:

- **Which training data to use.** That is the operator's choice.
- **Whether a model is ethically aligned.** Gate v2 is a capability + regression gate, not a safety gate.
- **Whether to trust an external model backend.** The adapter boundary delegates trust to whatever the operator configured.
- **Whether to ship.** A promoted candidate is the best available, not a certified production release.

The doctrine answers one question well: *is this candidate safe to displace the incumbent, and do we have evidence for why*.

## The governance invariants

These hold across every Gate v2 run:

1. No candidate below the hard-reject floor can promote.
2. No candidate below the floor model can promote.
3. No candidate with a regression-ceiling violation can promote.
4. No candidate with a lower-or-equal overall score can promote.
5. No non-promotable adapter can become an incumbent.
6. No archive-only or reject decision clears the current incumbent flag.
7. Every decision produces a machine-readable receipt.
8. Every promote or archive-only produces a restorable Arc-RAR bundle.
9. Every receipt and bundle is SHA-256 addressable.
10. The floor model locks from the current incumbent after every real promote.

Violations of any invariant are treated as bugs, not policy exceptions.

## Evidence

As of v1.0.0-governed, every decision state has fired on a real candidate:

| Decision | Example | Cause |
|---|---|---|
| promote | `arc_governed_v4` | +0.1007 vs v2 baseline, zero regressions |
| promote | `arc_governed_v5` | +0.0041 vs v4, zero regressions |
| promote | `arc_governed_v6_conversation` | +0.0164 vs v5, conversation-derived corpus |
| promote | `arc_governed_v7_wave1` | +0.1701 vs v6 (post-audit), wave 1 exemplars |
| promote | `arc_governed_v8_wave2` | +0.0346 vs v7, wave 2 exemplars |
| promote | `arc_governed_v9_wave3` | +0.0028 vs v8, wave 3 exemplars |
| promote | `arc_governed_v10_wave4` | +0.0326 vs v9, wave 4 exemplars — **current incumbent** |
| archive_only (tie) | `arc_governed_v6` | Identical to v5 at 0.7169 |

> **Note:** The post-audit overall score for v6_conversation is 0.6836 (true baseline after fixing synthetic benchmarks and gameable rubric). Pre-audit claimed 0.7333.
| archive_only (regression) | `arc_governed_v7_regressed` | `reasoning` dropped 0.667, `critique` dropped 0.250 |
| reject | covered by test suite | hard-reject floor triggered on synthetic candidates |

See `RELEASE_NOTES_v1.0.0.md` for the full evidence dossier.

## The one-line doctrine

**Preserve the better brain. Reject the worse one. Leave evidence for why, in a form anyone can check later.**
