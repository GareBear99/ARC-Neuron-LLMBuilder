# How to Grow the ARC-Neuron System

This document explains the growth path from the current exemplar-retrieval
architecture to a fully trained neural model — and what each stage unlocks.

---

## The Current Architecture

ARC-Neuron currently uses an **exemplar adapter**: TF-IDF weighted cosine similarity
over a corpus of 669 stored Q&A pairs. When you ask a question, it finds the
stored example whose vocabulary most closely matches yours, and returns that
stored answer.

This is the correct starting point. It:
- Works on any hardware, instantly
- Is fully auditable (you can see exactly what it retrieved and why)
- Demonstrates that the governance loop (Gate v2, receipts, benchmarks) works correctly
- Establishes a training corpus that a real neural model can learn from

The retrieval adapter has a ceiling. Four capabilities are currently below 0.90
(continuity, reflection, reasoning, intelligence) specifically because they require
genuine generalisation — understanding a novel situation rather than matching a stored one.
The transformer layer is how you break through that ceiling.

---

## Growth Stage 1 — Richer Exemplars (No Code Changes)

**Effort:** Low  
**Impact:** +5 to +15 points on targeted capabilities  
**Time:** Hours

The simplest growth lever is adding better training examples to
`datasets/distillation_sft/`. The training pipeline picks them up automatically.

### What makes a good exemplar

```jsonl
{
  "capability": "reasoning",
  "prompt": "A proposed change removes the rate-limiting middleware. The constraint is that no endpoint may serve more than 100 requests per second per user. Is this acceptable?",
  "target": "Not acceptable. Removing rate-limiting middleware directly violates the 100 req/s per user constraint. The change must be rejected unless an equivalent enforcement mechanism is proven to exist elsewhere in the stack."
}
```

**Good exemplar checklist:**
- [ ] The prompt is a real question someone would actually ask
- [ ] The target is a complete, grammatically correct answer with at least one sentence
- [ ] The target is specific to the prompt (not generic governance boilerplate)
- [ ] The target uses natural language for the domain (not artificial keyword lists)
- [ ] The capability label matches what the task actually tests

### How many exemplars per capability

| Current records | Current score | Recommendation |
|----------------|---------------|----------------|
| < 5 | < 0.70 | Add 15–20 targeted exemplars |
| 5–20 | 0.70–0.85 | Add 10 targeted exemplars for failing task types |
| > 20 | > 0.85 | Adding more may regress via retrieval contamination — train the transformer instead |

### Retrieval contamination warning

If adding exemplars makes scores go down on OTHER capabilities, you have
retrieval contamination: your new exemplars share vocabulary with prompts
in other capabilities. The fix is either:
1. Use more distinctive vocabulary in your exemplar prompts, or
2. Move to Stage 2 (transformer training) which doesn't have this problem

---

## Growth Stage 2 — Train the Transformer

**Effort:** Medium  
**Impact:** Breaks the retrieval ceiling; enables genuine generalisation  
**Time:** 30–60 minutes on modern laptop CPU (Tiny); 2–4 hours (Small)

The `arc_core/transformer.py` contains a complete GPT-2-style causal language model.
It is not trained yet — it exists as a trainable architecture waiting for a corpus.

```bash
# Train the Tiny model (0.05M params) on the current corpus
python3 scripts/training/train_arc_native_candidate.py \
  --model-size tiny \
  --candidate arc_native_tiny_v1

# Train the Small model (0.18M params) — better capability, needs more time
python3 scripts/training/train_arc_native_candidate.py \
  --model-size small \
  --candidate arc_native_small_v1
```

### What the transformer unlocks

| Capability | Exemplar adapter ceiling | After transformer training |
|-----------|------------------------|--------------------------|
| continuity | 0.77 (can't track prior turns) | Can be trained on multi-turn transcripts |
| reflection | 0.84 (can't reason about its own output) | Can learn to self-critique with RLHF-style data |
| reasoning | 0.88 (matches patterns, can't chain logic) | Can learn multi-step inference |
| out-of-distribution | 0.0 (fails completely) | Generalises from learned representations |

### Training data for the transformer

The same exemplars used for retrieval work for transformer training, but
the transformer also benefits from:

1. **Multi-turn conversations** — sequences of prompt/response pairs
2. **Negative examples** — wrong answers paired with corrections
3. **Raw text** — any domain text the model should understand

```python
# The training pipeline handles format conversion automatically
python3 scripts/training/prepare_distillation_corpus.py
```

---

## Growth Stage 3 — RLHF / Preference Tuning

**Effort:** High  
**Impact:** Teaches the model to prefer correct and calibrated answers  
**Time:** Varies by corpus size

Once the transformer produces coherent output, preference tuning teaches it
which of its own outputs are better. The system already has:

```bash
datasets/  ← supervised examples (preferred answers)
```

The next step is a preference dataset:

```jsonl
{
  "prompt": "Is a 400-request canary sample sufficient?",
  "chosen": "No. 400 requests is insufficient statistical power at sub-1% error rate delta...",
  "rejected": "Yes, that looks fine."
}
```

The `train_preference_candidate.py` script is already present and wired
to accept this format.

---

## Growth Stage 4 — Quantisation and Deployment

Once the transformer is trained, export it for efficient deployment:

```bash
python3 scripts/training/export_gguf_candidate.py \
  --candidate arc_native_small_v1 \
  --quantization q4_K_M
```

The quantisation_retention benchmark then validates that capability scores
are preserved within 10% after compression:

```bash
# Gate v2 will run the retention check automatically
python3 scripts/training/train_exemplar_candidate.py --candidate arc_gguf_v1
```

**Quantisation options and tradeoffs:**

| Scheme | Size reduction | Quality retention | Use case |
|--------|---------------|-------------------|---------|
| q8_0 | 2× | ~98% | Development, high-accuracy |
| q4_K_M | 4× | ~90% | Production, balanced |
| q4_0 | 4× | ~87% | Embedded, resource-constrained |
| q3_K_S | 5.5× | ~82% | Edge devices, IoT |

---

## Growth Stage 5 — Domain Specialisation

The governed pipeline makes specialisation safe:

1. Add domain-specific exemplars (medical, legal, embedded systems, etc.)
2. Train a domain candidate
3. Gate v2 ensures it doesn't regress on general capabilities
4. If it passes, it becomes the new incumbent for that domain

Each domain can have its own capability tower:

```
benchmarks/
├── medical_triage/        ← add domain-specific tasks here
├── legal_reasoning/
├── embedded_c/
└── robotics_planning/
```

The rubric is capability-agnostic — a new capability just needs a JSONL benchmark file
and a rubric entry in `scorers/rubric.py`.

---

## Monitoring and Observability

The Omnibinary archive stores every training event and every gate decision.
Query it at any time:

```python
from runtime.learning_spine import OmnibinaryStore

store = OmnibinaryStore('artifacts/omnibinary/arc_events.obin')
recent_events = store.scan(limit=10)
for event in recent_events:
    print(event['type'], event['timestamp'], event.get('score'))
```

The receipt chain gives you a complete audit log from v6 to v10, with
every delta, every floor check, and every SHA-256 hash. Nothing is hidden.

---

## The Ceiling of Each Stage

| Stage | Score ceiling | What breaks the ceiling |
|-------|--------------|------------------------|
| Exemplar retrieval | ~0.93 (current) | Retrieval cannot generalise |
| Tiny transformer (0.05M) | ~0.70–0.80 standalone | Too small for complex reasoning |
| Small transformer (0.18M) | ~0.75–0.85 standalone | Still small; benefits from fine-tuning |
| RLHF-tuned Small | ~0.85–0.92 | Calibration and self-correction improve |
| Trained on large corpus | Depends on data | Data quality becomes the limiting factor |

The governance loop works at every stage. Gate v2 doesn't care whether the
brain is a lookup table or a billion-parameter model — it checks scores,
floors, and receipts the same way.

