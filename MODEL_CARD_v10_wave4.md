# Model Card — `arc_governed_v10_wave4`

Current incumbent as of v2.0.0-audited (2026-05-04).

## Summary

| Field | Value |
|---|---|
| Model name | `arc_governed_v10_wave4` |
| Version | v2.0.0-audited |
| Architecture | Exemplar retrieval (TF-IDF cosine similarity over 669 Q&A records) |
| Promoted from | arc_governed_v9_wave3 |
| Training records | 669 exemplar records |
| Inference method | Cap-first TF-IDF retrieval — no neural forward pass |
| Context window | Prompt vocabulary (no fixed limit) |
| License | MIT |
| Promotion date | 2026-05-04 |

## What this model actually is

This model is an exemplar retrieval system, not a trained neural network. When given a prompt, it computes TF-IDF-weighted cosine similarity against 669 stored question-answer pairs, retrieves the top-3 most similar records for the requested capability, and returns the stored answer. This is transparent by design — you can inspect every retrieval decision.

The `arc_core/transformer.py` contains a trainable GPT-2-style neural network that replaces this retrieval layer once trained. See [docs/HOW_TO_GROW.md](./docs/HOW_TO_GROW.md) for the training path.

## Benchmark scores

All scores verified by independent audit on 2026-05-04. Reproducible via:
```bash
python3 scripts/ops/run_benchmark.py --artifact exports/candidates/arc_governed_v10_wave4/exemplar_train/exemplar_model.json
```

| Capability | Score | Tasks |
|-----------|-------|-------|
| calibration | 0.9000 | 10 |
| compression | 0.9167 | 10 |
| continuity | 0.7708 | 10 |
| critique | **1.0000** | 10 |
| english_understanding | 0.9000 | 10 |
| instruction_following | 0.9250 | 10 |
| intelligence | 0.8472 | 12 |
| out_of_domain | 0.9667 | 10 |
| paraphrase_stability | **1.0000** | 10 |
| planning | **1.0000** | 10 |
| quantization_retention | **1.0000** | 10 |
| reasoning | 0.8833 | 10 |
| reflection | 0.8375 | 10 |
| repair | **1.0000** | 10 |
| **OVERALL** | **0.9237** | **142** |

## Promotion chain

```
v6_conversation (0.6836†) → v7_wave1 (0.8537) → v8_wave2 (0.8883) → v9_wave3 (0.8911) → v10_wave4 (0.9237)
```

†True post-audit baseline. Pre-audit claimed 0.7333; inflated by synthetic benchmark tasks. See [docs/BENCHMARK_PROOF.md](./docs/BENCHMARK_PROOF.md).

## Gate v2 record

All four promotions passed Gate v2:
- ✅ Overall score strictly exceeds incumbent
- ✅ No capability below `incumbent × 0.95` floor
- ✅ No single capability regressed more than 0.15

Full receipts in `exports/candidates/arc_governed_v10_wave4/promotion_receipt.json`.

## Training data

669 exemplar records across 14 capability families:

| Wave | Records | Capabilities |
|------|---------|-------------|
| Legacy (v1–v6) | 373 | generic, reasoning, calibration, repair, planning, critique, etc. |
| Wave 1 | +100 | reasoning, reflection, continuity, instruction_following, intelligence |
| Wave 1 extras | +81 | calibration, repair, planning, compression, paraphrase_stability, out_of_domain, english_understanding, quantization_retention |
| Wave 2 | +32 | compression (targeted), intelligence (arc-domain), continuity |
| Wave 3 | +33 | english_comprehension, english_understanding (targeted), reflection (targeted) |
| Wave 4 | +19 | english_understanding, intelligence, reflection |
| **Total** | **669** | **14 capabilities** |

## Known limitations

| Limitation | Detail |
|-----------|--------|
| Retrieval ceiling | Cannot generalise beyond stored exemplars. Novel prompts with no vocabulary match get the highest-IDF global match, which may be wrong. |
| Continuity (0.77) | Session-context preservation requires genuine memory of prior turns. Retrieval cannot do this across diverse prompt sequences. |
| Reflection (0.84) | Self-correction on novel claims requires reasoning, not pattern-matching. |
| Reasoning (0.88) | Multi-step inference on genuinely novel scenarios is beyond retrieval. |
| No neural inference | The transformer layer (`arc_core/transformer.py`) is not trained. Training it would break these ceilings. |

## Intended use

- Reference incumbent for candidate comparison and Gate v2 evaluation
- Demonstration that the governed promotion lifecycle (train → benchmark → gate → archive) works correctly
- Training corpus baseline for the native transformer
- Integration point for any domain that needs auditable, receipt-backed AI update cycles

## Ethical considerations

- This model runs entirely locally. No data leaves your machine.
- All decisions are logged in the Omnibinary archive with SHA-256 receipts.
- The model does not perform safety classification and should not be used as a safety gate without additional capability evaluation.
- The governance layer (Gate v2) enforces capability non-regression but not alignment.

## Citation

```bibtex
@software{arc_neuron_v10,
  author = {GareBear99},
  title  = {ARC-Neuron LLMBuilder — arc_governed_v10_wave4},
  year   = {2026},
  url    = {https://github.com/GareBear99/ARC-Neuron-LLMBuilder},
  note   = {v2.0.0-audited; overall benchmark score 0.9237 on 142 tasks}
}
```
