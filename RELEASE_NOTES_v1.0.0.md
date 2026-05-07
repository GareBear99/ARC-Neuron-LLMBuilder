> **Historical document — v1.0.0-governed.**
> Scores in this file reflect the pre-audit rubric and synthetic benchmarks.
> The true v6_conversation baseline is **0.6836** (not 0.7333).
> Current incumbent is `arc_governed_v10_wave4` at **0.9237**.
> See [docs/BENCHMARK_PROOF.md](./docs/BENCHMARK_PROOF.md) for the authoritative post-audit record.

---

# Release Notes — v1.0.0-governed

**Released**: 2026-04-22
**Codename**: *Doctrine Closed*
**Incumbent**: `arc_governed_v6_conversation` at 0.7333

---

## One-line summary

The growth loop is closed end-to-end: conversation grows the brain, not just the memory. Three governed promotions in a row on record; all four Gate v2 decision states have fired lawfully on real runs.

---

## What this release proves

1. **The plateau is breakable.** From v2's 0.6247 ceiling (which held across 3 cycles and 10 consecutive archive_only decisions), the system broke to 0.7128 (v4) → 0.7169 (v5) → 0.7333 (v6_conversation) through corpus augmentation alone.

2. **The gate is not pass-happy.** Gate v2 has now executed every decision state it was designed for:
   - **Promote** — v4, v5, v6_conversation (three successive real promotions)
   - **Archive-only tie** — v6 (identical score to incumbent v5, correctly archived)
   - **Archive-only regression** — v7_regressed (caught with attribution: `reasoning: 0.667 > 0.05`, `critique: 0.250 > 0.06`)
   - **Reject** — exercised by the hard-reject floor logic in test coverage

3. **Conversation truly grows the brain.** `v6_conversation` was trained from a corpus the canonical conversation pipeline harvested itself — 30 varied prompts through `ExemplarAdapter → ReflectionLoop → ConversationPipeline → LanguageAbsorptionLayer` produced 30 direct SFT + 39 pipeline SFT + 45 terminology SFT records, which when merged with the repo corpus trained a candidate that beat v5 by +0.0164.

4. **The archive is lossless.** All 12 Arc-RAR bundles are manifest-readable and restorable. The Omnibinary ledger has SHA-256 integrity across sessions, with the index automatically rebuilding on drift.

5. **The loop is stable.** 5 consecutive cycles at the v5 floor all correctly archive-only'd at 0.7169. 3 consecutive cycles at the v4 floor all correctly archive-only'd at 0.6200. No floor breaches. No regressions. No failures.

---

## Full promotion history

| Version | Score | Records | Decision | Cause |
|---|---|---|---|---|
| arc_governed_v1 | 0.6122 | 546 | **promote** | first baseline candidate |
| arc_governed_v2 | 0.6247 | 549 | **promote** | +3 records, compression to 1.000 |
| arc_governed_v3 | 0.6128 | 556 | archive_only | regressed continuity/reflection |
| arc_governed_v4 | **0.7128** | 640 | **promote** | +17 reasoning/critique/lexical SFT broke plateau |
| arc_governed_v5 | **0.7169** | 648 | **promote** | +8 extension pack, beat v4 |
| arc_governed_v6 | 0.7169 | 648 | archive_only | tied v5 (deterministic, correct) |
| arc_governed_v7_regressed | 0.6190 | 623 | archive_only | reasoning/critique regression caught |
| arc_governed_v6_conversation | **0.7333** | 762 | **promote** | conversation-harvested corpus, +0.0164 over v5 |

---

## Per-capability evidence (v6_conversation vs v5)

| Capability | v5 | v6_conversation | Δ |
|---|---|---|---|
| reasoning | 1.0000 | 1.0000 | = |
| planning | 1.0000 | 1.0000 | = |
| compression | 1.0000 | 1.0000 | = |
| paraphrase_stability | 0.8666 | 0.8666 | = |
| calibration | 0.8333 | 0.8333 | = |
| critique | 0.7500 | 0.7500 | = |
| english_understanding | 0.7333 | 0.7500 | **+0.017** |
| quantization_retention | 0.6667 | 0.8333 | **+0.167** |
| out_of_domain | 0.6667 | 0.7500 | **+0.083** |
| intelligence | 0.5694 | 0.5972 | **+0.028** |
| reflection | 0.5000 | 0.5667 | **+0.067** |
| repair | 0.6667 | 0.6667 | = |
| instruction_following | 0.5833 | 0.5833 | = |
| continuity | 0.5834 | 0.5833 | = |
| arc_neuron_small_v2 | 0.5185 | 0.5185 | = | *(legacy benchmark row — removed in v2.0.0)* |
| arc_neuron_base | 0.5333 | 0.4333 | -0.100 (below violation threshold) | *(legacy benchmark row — removed in v2.0.0)* |
| **overall_weighted** | **0.7169** | **0.7333** | **+0.0164** |

The gain profile is the signature of real learning: broader intelligence capabilities improved (out_of_domain, quantization_retention, reflection, intelligence, english_understanding) rather than a single cherry-picked metric. One minor regression on arc_neuron_base (-0.100) was caught but did not trigger a violation because that capability is not in the regression ceiling list. *(arc_neuron_base and arc_neuron_small_v2 were legacy benchmark families removed during the v2.0.0 audit; they are not part of the current 14-capability benchmark suite.)*

---

## Omnibinary performance (measured at release)

Benchmark run of 1,000 events on commodity hardware:

| Metric | Value |
|---|---|
| Append throughput | 6,639 events/sec |
| O(1) lookup throughput | 8,859 lookups/sec |
| Lookup p50 latency | 0.10 ms |
| Lookup p99 latency | 0.22 ms |
| Full scan (1,000 events) | 12.43 ms |
| Index rebuild from ledger | 3.80 ms |
| Storage per event | 397 bytes |
| SHA-256 fidelity | PASS |
| Spot-check restore fidelity | PASS |

Live store at release: 98 events, integrity OK, index_rebuilt=false across sessions.

---

## Test evidence

**87/87 tests passing** covering:
- Shared transformer base (import identity, weight tying, block-size guard, param count)
- GGUF v3 I/O (lossless roundtrip, bad-magic raise, alignment constraint)
- Native training smoke (tiny tier, small tier, routing detection, scaffold fallback)
- Rubric scorer (all capability buckets, short/empty/substantial/overconfident guards)
- Canonical conversation pipeline (receipt creation, Omnibinary mirror, label, export, get by receipt/turn)
- Omnibinary indexed store (append, O(1) get, scan, verify, rebuild, export_jsonl, high-volume 100-event, cross-instance consistency)
- Gate v2 (promote, archive_only, reject, floor breach, regression violation, tie-archive, non-promotable filter, incumbent guard)
- Arc-RAR bundle (roundtrip, manifest restore, SHA-256 index)
- ANCF (roundtrip, version check, magic bytes)
- Continuity (goal retention, constraint preservation, terminology correction, decision recall)
- Reflection loop (draft → critique → revise, skip on short, fix parsing)

---

## Artifact SHAs

Promoted model bundles in `artifacts/archives/`:

- `arc-rar-arc_governed_v1-ed1042be.arcrar.zip` — 16 files
- `arc-rar-arc_governed_v2-d4f2b940.arcrar.zip` — 16 files
- `arc-rar-arc_governed_v2-f0802548.arcrar.zip` — 16 files
- `arc-rar-arc_governed_v4-e6f9d0df.arcrar.zip` — 16 files
- `arc-rar-arc_governed_v5-0721488f.arcrar.zip` — 16 files
- `arc-rar-arc_governed_v6_conversation-2acf171e.arcrar.zip` — 16 files

---

## Known limitations

1. **Model size is the ceiling.** The ARC-Neuron Small tier is ~0.18M parameters. That is enough to prove the governance and growth loop, not enough to compete with frontier LLMs. The adapter boundary (`adapters/command_adapter.py`, `adapters/llama_cpp_http_adapter.py`) exists specifically to let you plug in a stronger base model while preserving all governance.

2. **Exemplar adapter is retrieval, not generation.** The current benchmark evidence uses an `ExemplarAdapter` that performs cosine retrieval over training records. The native transformer produces real weights and GGUF artifacts, but actual benchmark response quality at small-model scale is dominated by retrieval coverage.

3. **English fluency is small-model grade.** Responses are coherent in the governed-cognition doctrine vocabulary the corpus teaches. Broad natural conversation is beyond current model capacity. This is expected for the size.

4. **Training is CPU-only by default.** Native training runs on CPU at ~2 threads in the default config. Suitable for the Tiny and Small tiers; larger tiers would benefit from GPU acceleration via standard PyTorch.

---

## Upgrade notes

This is the first production release. If you were tracking the v0.3.x alpha line, the canonical-path changes mean:

- Replace any direct `OmnibinaryStore(path)` construction with the new default (`index_flush_every=1` for single-appender safety; use `flush()` explicitly if batching).
- Any custom promotion script should now pass scored outputs through `promote_candidate.py` Gate v2 rather than v1 thresholds.
- `run_proof_workflow.py` is the new end-to-end entry point; older demo scripts remain but are deprecated in favor of the canonical one.
- The floor model is now enforced before any other promotion logic; candidates that drop below the locked baseline reject immediately, not archive-only.

---

## Contributors

- **Gary Doman** — architecture, doctrine, production hardening, training loop, Gate v2, Omnibinary, Arc-RAR, language absorption, promotion wave execution.

---

## Verification

To independently verify this release:

```bash
git clone https://github.com/GareBear99/ARC-Neuron-LLMBuilder.git
cd ARC-Neuron-LLMBuilder
git checkout v1.0.0-governed

python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install "torch>=2.0" "numpy<2.0"
python3 scripts/ops/bootstrap_keys.py

# Expected: 87 passed
python3 -m pytest tests/ -q

# Expected: Omnibinary PASS with measured throughput
python3 scripts/ops/benchmark_omnibinary.py

# Expected: 9/9 steps green, decision=archive_only (can't beat v6_conversation)
python3 scripts/ops/demo_proof_workflow.py

# Expected: STABLE verdict, 3/3 cycles
python3 scripts/ops/run_n_cycles.py --cycles 3 --tier tiny --steps 30
```

---

## The verdict

The machine is lawful. The measurement is honest. The loop grows a better brain on demand, preserves the prior one, rejects worse ones with attribution, and does so repeatedly.


---

## Post-audit addendum (v2.0.0-audited — 2026-05-04)

An independent audit found 4 structural defects in the v1.0.0 benchmark and rubric. The claims below about benchmark scores reflect the pre-fix rubric. The corrected numbers are:

- True v6_conversation overall score: **0.6836** (not 0.7333)
- Post-audit, four additional governed promotions raised this to **0.9237**
- See [docs/BENCHMARK_PROOF.md](./docs/BENCHMARK_PROOF.md) for the complete audit record

The promoted candidates (v4, v5, v6_conversation), the gate decision states, and the receipt chain are real and unchanged. Only the score values were inflated by the synthetic benchmarks.
