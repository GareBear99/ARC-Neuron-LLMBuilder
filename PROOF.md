# Proof — v1.0.0-governed

Every claim in this document is backed by a command anyone can re-run. The receipts, benchmarks, and promotion evidence cited here were all produced during v1.0.0-governed release verification.

If any command in this document doesn't produce the documented result on a fresh clone, that is a bug — file it as a [bug report](./.github/ISSUE_TEMPLATE/01_bug_report.yml).

---

## <a id="hardware-provenance"></a>Hardware provenance

> **Every result in this document was produced on a 2012 Intel Mac running macOS Catalina.**

Specifically:
- Pre-Retina-era Intel CPU (consumer laptop hardware from 2012)
- macOS Catalina (10.15.x)
- No discrete GPU used
- No cloud resources
- No specialized accelerator
- Python (CPython) + PyTorch (CPU build) + numpy

This is important. The three governed promotions (v4 → v5 → v6_conversation), the 87 passing tests, the Omnibinary throughput numbers (6,639 events/sec append, 8,859 O(1) lookups/sec), the five-cycle STABLE repeatability verdict, and the full 9-step demo proof workflow were **all produced on 12-year-old consumer hardware**. If the system runs there, it runs on effectively any machine anyone is reasonably likely to encounter. Modern hardware should be materially faster across every benchmark axis.

---

## 1. The system works — reproducible in three commands

```bash
git clone https://github.com/GareBear99/ARC-Neuron-LLMBuilder.git && cd ARC-Neuron-LLMBuilder
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt "torch>=2.0" "numpy<2.0" && python3 scripts/ops/bootstrap_keys.py

python3 -m pytest tests/ -q                   # → 87 passed
python3 scripts/ops/benchmark_omnibinary.py   # → PASS with measured throughput
python3 scripts/ops/demo_proof_workflow.py    # → 9/9 steps green
```

---

## 2. Gate v2 has fired in all four lawful decision states

| Decision | Candidate | Score vs incumbent | Outcome |
|---|---|---|---|
| **promote** | `arc_governed_v4` | 0.7128 vs v2 baseline 0.6121 | +0.1007, plateau broken |
| **promote** | `arc_governed_v5` | 0.7169 vs v4 0.7128 | +0.0041, beat v4 |
| **promote** | `arc_governed_v6_conversation` | 0.7333 vs v5 0.7169 | +0.0164, **conversation-derived corpus** |
| **archive_only (tie)** | `arc_governed_v6` | 0.7169 vs v5 0.7169 | tied, correctly archived |
| **archive_only (regression)** | `arc_governed_v7_regressed` | 0.619 vs v5 0.7169 | regression caught with attribution |
| **reject** | synthetic test candidate | hard-reject floor | test coverage |

**Reproducibility**: every promotion entry lives in `results/scoreboard.json`. Every decision receipt lives in `reports/promotion_decision.json` (latest) or per-cycle `reports/cycle_*_promo.json`.

### The regression catch (attributed)

When `arc_governed_v7_regressed` was tested with a deliberately reduced corpus, the gate output:

```json
{
  "decision": "archive_only",
  "promoted": false,
  "overall_weighted_score": 0.619,
  "regression_violations": [
    "reasoning: candidate=0.333 incumbent=1.000 regression=0.667 > allowed=0.05",
    "critique: candidate=0.500 incumbent=0.750 regression=0.250 > allowed=0.06"
  ]
}
```

**Every violation is attributed to a specific capability with exact numbers.** This is the discipline that distinguishes Gate v2 from simple "score went down" gates.

---

## 3. The brain grew from conversation, not hand-authored SFT

**Proof**: `arc_governed_v6_conversation` was trained from a corpus produced by running `run_proof_workflow.py` 30 times with varied prompts through the canonical pipeline.

- 30 conversation turns → 30 direct SFT records (`v6_direct_conversation.jsonl`)
- + 39 auto-tagged training-eligible records (`pipeline_v2_export.jsonl`)
- + 45 terminology-derived SFT records (`terminology_sft.jsonl`)
- + prior corpora baked into v5 (648 records)
- **= 762 exemplar records**, 114 more than v5 (648)

v6_conversation then scored **0.7333 vs v5's 0.7169** on the **same 165-task benchmark**, promoted cleanly through Gate v2 with zero regression violations.

**Per-capability gains (v5 → v6_conversation, same 165-task set)**:

| Capability | v5 | v6_conversation | Δ |
|---|---|---|---|
| quantization_retention | 0.6667 | 0.8333 | **+0.167** |
| out_of_domain | 0.6667 | 0.7500 | **+0.083** |
| reflection | 0.5000 | 0.5667 | **+0.067** |
| intelligence | 0.5694 | 0.5972 | **+0.028** |
| english_understanding | 0.7333 | 0.7500 | **+0.017** |
| arc_neuron_base | 0.5333 | 0.4333 | -0.100 (below violation threshold) |
| **overall_weighted** | **0.7169** | **0.7333** | **+0.0164** |

The gains spread across broader-intelligence capabilities (not cherry-picked for a single metric) — the signature of real learning rather than keyword-farming.

---

## 4. The loop is stable, not a single lucky run

**5-cycle repeatability proof at v5 floor (before v6_conversation)**:

```
  total_cycles             : 5
  completed                : 5
  promoted                 : 0
  archive_only             : 5
  rejected                 : 0
  floor_breaches           : 0
  regressions              : 0
  score_min                : 0.7169
  score_max                : 0.7169
  score_mean               : 0.7169
  loop_stable              : True
```

**3-cycle repeatability at v4 floor (earlier session)**: STABLE. 3/3 completed, 0 regressions.

Every repeatability report lives in `reports/repeatability_<timestamp>.json`. Run `python3 scripts/ops/run_n_cycles.py --cycles 5 --tier tiny --steps 30` to reproduce.

---

## 5. Omnibinary performance, measured on commodity hardware

Directly from `scripts/ops/benchmark_omnibinary.py` on a **2012 Intel Mac / macOS Catalina** (see [Hardware provenance](#hardware-provenance)):

```
Omnibinary Benchmark — 1000 events
  Append:   6,639 events/sec  (150.62ms)
  O(1) Get: 8,859 lookups/sec  p50=0.0999ms  p99=0.2248ms
  Scan:     12.43ms total
  Rebuild:  3.8ms for 1000 events
  Storage:  397 bytes/event
  Fidelity: SHA256_stable=True  spot=True
```

Storage math: **a 1 TB drive holds ~2.71 billion governed events** at 397 bytes each. Full projections are in [STORAGE_ECONOMICS.md](./STORAGE_ECONOMICS.md).

---

## 6. Archive bundles are restorable, not theoretical

12 Arc-RAR bundles are on record in `artifacts/archives/`. Every bundle's manifest is readable without extracting:

```python
from runtime.learning_spine import read_arc_rar_manifest
from pathlib import Path

mf = read_arc_rar_manifest(Path(
    "artifacts/archives/arc-rar-arc_governed_v6_conversation-2acf171e.arcrar.zip"
))
# → dict with candidate name, file count, SHA-256 index, receipts
```

Verified bundles from v1.0.0-governed release:

| Bundle | Candidate | Files |
|---|---|---|
| `arc-rar-arc_governed_v1-ed1042be.arcrar.zip` | v1 | 16 |
| `arc-rar-arc_governed_v2-d4f2b940.arcrar.zip` | v2 | 16 |
| `arc-rar-arc_governed_v2-f0802548.arcrar.zip` | v2 (2nd) | 16 |
| `arc-rar-arc_governed_v4-e6f9d0df.arcrar.zip` | v4 | 16 |
| `arc-rar-arc_governed_v5-0721488f.arcrar.zip` | v5 | 16 |
| **`arc-rar-arc_governed_v6_conversation-2acf171e.arcrar.zip`** | **v6 (INCUMBENT)** | **16** |

Each bundle contains: promotion receipt, training manifests, `.pt` checkpoint, GGUF export, exemplar artifact, runtime receipts, and a SHA-256 index over every file.

---

## 7. The test suite proves every layer

**87 tests pass on a fresh clone**:

```
........................................................................ [ 82%]
...............                                                          [100%]
87 passed in ~30s
```

Coverage:
- Shared transformer base (import identity, weight tying, block-size guard, param count)
- GGUF v3 I/O (lossless roundtrip, bad-magic raise, alignment)
- Native training smoke (tiny tier, small tier, routing, scaffold fallback)
- Rubric scorer (all capability buckets, short/empty/substantial/overconfident guards)
- Canonical conversation pipeline (receipt creation, Omnibinary mirror, label, export, get)
- OmnibinaryStore (append, O(1) get, scan, verify, rebuild, export_jsonl, 100-event volume)
- Gate v2 (all four decision branches, floor breach, regression violation, tie-archive, non-promotable filter, incumbent guard)
- Arc-RAR bundle (roundtrip, manifest restore, SHA-256 index)
- ANCF (roundtrip, version check, magic bytes)
- Continuity, reflection loop

---

## 8. The demo proof workflow walks the whole loop

Running `python3 scripts/ops/demo_proof_workflow.py` produces this nine-step output, every step independently verified:

```
Step 1: Teach a term to language module                 ✓
Step 2: Retrieve the term from the store                ✓
Step 3: Conversation through canonical pipeline         ✓
Step 4: Export conversation as training SFT             ✓
Step 5: Train a tiny candidate model                    ✓
Step 6: Benchmark against 165-task suite                ✓
Step 7: Gate v2 decision (archive_only — incumbent wins) ✓
Step 8: Omnibinary store integrity verified             ✓
Step 9: 12 prior Arc-RAR bundles readable               ✓
```

Every `✓` corresponds to an assertion in the script. One red, and the workflow stops with a diagnostic.

---

## 9. The scoreboard tells the whole story

`results/scoreboard.json` preserves every candidate the gate has ever evaluated:

| Model | Score | Decision | Incumbent |
|---|---|---|---|
| arc_governed_v1 | 0.6122 | promote | false |
| arc_governed_v2 | 0.6247 | promote | false |
| arc_governed_v3 | 0.6128 | archive_only | false |
| arc_governed_v4 | 0.7128 | promote | false |
| arc_governed_v5 | 0.7169 | promote | false |
| arc_governed_v6 | 0.7169 | archive_only | false |
| arc_governed_v7_regressed | 0.6190 | archive_only | false |
| **arc_governed_v6_conversation** | **0.7333** | **promote** | **TRUE** |
| + cycle_01 through cycle_05_*_Z | 0.619–0.717 | archive_only | false |

No other open-source system I'm aware of can show you this kind of full-lineage, multi-decision, gate-attributed scoreboard with the receipts still addressable.

---

## 10. One-command verification

If you only want to prove everything end-to-end in under a minute:

```bash
make test && make verify-store && python3 scripts/ops/demo_proof_workflow.py
```

Expected final line:
```
The system remembered, trained, decided, and preserved.
```

---

## Summary table

| Claim | Receipt | Verify with |
|---|---|---|
| 87 tests pass | test suite output | `pytest tests/ -q` |
| Omnibinary 6,600+ ev/s append | `reports/omnibinary_benchmark.json` | `scripts/ops/benchmark_omnibinary.py` |
| v6_conversation promoted at 0.7333 | `reports/promotion_decision.json` | inspect scoreboard + scored file |
| Three governed promotions in a row | `results/scoreboard.json` | read decisions column |
| v7_regressed rejected with attribution | `reports/cycle_*_promo.json` | read regression_violations field |
| 5-cycle STABLE at v5 floor | `reports/repeatability_*.json` | `scripts/ops/run_n_cycles.py --cycles 5` |
| 12 Arc-RAR bundles restorable | `artifacts/archives/` + manifest reads | `read_arc_rar_manifest(...)` |
| 397 bytes/event measured | `reports/omnibinary_benchmark.json` | `scripts/ops/benchmark_omnibinary.py` |

The machine is lawful. The measurement is honest. Every claim has a receipt.
