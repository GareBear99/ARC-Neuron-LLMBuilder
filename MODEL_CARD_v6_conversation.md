# Model Card — `arc_governed_v6_conversation`

> **Superseded.** This was the incumbent at v1.0.0-governed. The current incumbent is `arc_governed_v10_wave4`.
> Post-audit, the true v6 overall score is **0.6836** (not 0.7333 — inflated by synthetic benchmarks).
> See [MODEL_CARD_v10_wave4.md](./MODEL_CARD_v10_wave4.md) for the current model card.

Standard ML model card for the v1.0.0-governed incumbent (archived for provenance).

## Summary

| Field | Value |
|---|---|
| Model name | `arc_governed_v6_conversation` |
| Version | v1.0.0-governed |
| Architecture | Byte-level causal transformer (GPT-2-style pre-norm) |
| Tier | Small |
| Parameters | ~0.18M |
| Context window | 128 bytes |
| Tokenizer | Byte-level (vocab_size = 256) |
| Training framework | PyTorch |
| Training hardware | CPU (2 threads) |
| Export formats | PyTorch `.pt`, GGUF v3 `.gguf`, exemplar sidecar JSON |
| License | MIT |
| Training date | 2026-04-22 |

## Intended use

**Primary use case**: reference incumbent for the ARC-Neuron governed promotion lane. Demonstrates that the canonical conversation pipeline + Gate v2 + floor model can produce lawful, reproducible model growth from conversation-harvested training data.

**Secondary use case**: benchmark reference for candidate models trained by downstream users. Any new candidate must clear the regression floor locked from this model to be promoted.

**Out of scope**:
- Natural conversation at frontier LLM quality — this is a ~0.18M parameter model; use an external adapter (`llama_cpp_http`, `command`) for real conversational quality.
- Safety-sensitive deployments — the governance gate checks capability + regression, not alignment or safety.
- Any task that requires tokens broader than byte-level encoding — this model cannot leverage subword patterns.

## Training data

**Total records**: 762 exemplar records (114 more than the prior incumbent `arc_governed_v5` which had 648).

Sources:
- Base corpus: repo text from `datasets/*/*.jsonl` plus Python/Markdown/YAML files under 500 KB cap.
- SFT additions:
  - `v4_headroom_reasoning.jsonl` (17 records) — reasoning, critique, lexical accuracy, archive reasoning
  - `v5_extension_reasoning.jsonl` (8 records) — governance, promotion gate, lexical accuracy
  - **Conversation harvest** (30 records) — direct conversation output from the canonical pipeline driven by 30 varied prompts covering reasoning, critique, continuity, reflection, out_of_domain, instruction_following, system_spine, archive_reasoning, and lexical_accuracy
  - Pipeline SFT (39 records) — auto-tagged training-eligible records from the same conversations
  - Terminology SFT (45 records) — from the language module's approved terms
- Prior corpora: everything already baked into v5 (648 records).

**Corpus hash**: see `reports/arc_native_train_arc_governed_v6_conversation.json` for the SHA-256 of the training byte-stream.

**Provenance**: every conversation-harvested record carries receipt ID, turn ID, session ID, and UTC timestamp from the canonical pipeline run.

## Training configuration

| Hyperparameter | Value |
|---|---|
| Tier preset | small (3 layers, 4 heads, 64 embd, 128 block) |
| Steps | 300 |
| Batch size | 4 |
| Learning rate | 2e-3 |
| LR schedule | Cosine annealing to 0.1× |
| Optimizer | AdamW, weight_decay=0.01 |
| Gradient clipping | 1.0 |
| Seed | 2026 |
| Train/val split | 90/10 |
| Max corpus bytes | 600,000 |
| Eval batches | 20 |

**Training reproducibility**: deterministic given the same seed, corpus, and tier preset.

## Evaluation

**Benchmark**: 165-task suite across 16 capability families *(pre-audit rubric — synthetic benchmarks inflated scores)*.

**Overall weighted score**: `0.7333` pre-audit / **`0.6836` post-audit** (true score after fixing synthetic benchmarks and gameable rubric).

**Per-capability breakdown**:

| Capability | Score | Notes |
|---|---|---|
| reasoning | 1.0000 | at ceiling |
| planning | 1.0000 | at ceiling |
| compression | 1.0000 | at ceiling |
| paraphrase_stability | 0.8666 | |
| calibration | 0.8333 | |
| quantization_retention | 0.8333 | strong gain over v5 (0.667) |
| english_understanding | 0.7500 | |
| critique | 0.7500 | |
| out_of_domain | 0.7500 | strong gain over v5 (0.667) |
| repair | 0.6667 | |
| intelligence | 0.5972 | |
| instruction_following | 0.5833 | |
| continuity | 0.5833 | |
| reflection | 0.5667 | gain over v5 (0.500) |
| arc_neuron_small_v2 | 0.5185 | *(legacy benchmark — removed in v2.0.0 rebuild)* |
| arc_neuron_base | 0.4333 | regression from v5 (0.5333), below violation threshold *(legacy benchmark — removed in v2.0.0 rebuild)* |

**Comparison to baseline**:
- `arc_governed_v2` rescored: 0.6121 → v6_conversation: 0.7333 pre-audit / 0.6836 post-audit (**+11.9% relative**, true value)
- `arc_governed_v5`: 0.7169 → v6_conversation: 0.7333 pre-audit / 0.6836 post-audit

**Gate v2 decision receipt**: `reports/promotion_decision.json` at time of promotion — promoted with zero regression violations and zero floor violations.

## Safety and limitations

1. **Small model limitations.** At ~0.18M parameters on byte-level tokenization, the model cannot produce novel natural-language reasoning beyond what exemplar retrieval surfaces from its training corpus. Responses are effectively best-match retrievals with light paraphrasing.

2. **Exemplar retrieval, not generation.** Benchmark responses use the `ExemplarAdapter` which performs cosine retrieval over training records. The underlying transformer weights are real but their generative quality at this scale is limited.

3. **Doctrine-specific vocabulary.** The model has high fluency within the ARC governance doctrine (Gate v2, floor model, Arc-RAR, Omnibinary, receipts, lineage) and low fluency outside that domain. It is not a general-purpose assistant.

4. **No safety filtering.** Gate v2 is a capability + regression gate. This model has not been aligned for harmlessness, honesty, or helpfulness in the RLHF sense. Production deployments should add a safety layer at the adapter boundary.

5. **English-only.** No multilingual capability.

## Restoration

To restore this model after a future incumbent:

```python
from runtime.learning_spine import read_arc_rar_manifest
from pathlib import Path
import zipfile, shutil

bundle = Path("artifacts/archives/arc-rar-arc_governed_v6_conversation-2acf171e.arcrar.zip")
with zipfile.ZipFile(bundle) as z:
    z.extractall("restore/arc_governed_v6_conversation/")

# Inspect the manifest
mf = read_arc_rar_manifest(bundle)
print(f"files in bundle: {mf['file_count']}")

# Move the exemplar artifact back into exports/
shutil.copy(
    "restore/arc_governed_v6_conversation/exemplar_model.json",
    "exports/candidates/arc_governed_v6_conversation_restored/exemplar_train/exemplar_model.json",
)
```

The restored exemplar can be registered via the standard benchmark and gate path for verification that the restore is lossless.

## Artifacts

Location within repo (all gitignored except manifests and bundle):

| Path | Content |
|---|---|
| `exports/candidates/arc_governed_v6_conversation/lora_train/checkpoint/arc_native_arc_governed_v6_conversation.pt` | PyTorch checkpoint |
| `exports/candidates/arc_governed_v6_conversation/lora_train/checkpoint/arc_native_arc_governed_v6_conversation.gguf` | GGUF v3 export |
| `exports/candidates/arc_governed_v6_conversation/exemplar_train/exemplar_model.json` | Retrieval exemplar artifact (762 records) |
| `reports/arc_native_train_arc_governed_v6_conversation.json` | Training report |
| `results/arc_governed_v6_conversation_scored.json` | Benchmark scored outputs |
| `artifacts/archives/arc-rar-arc_governed_v6_conversation-2acf171e.arcrar.zip` | Arc-RAR restorable bundle |

## Lineage

```
arc_governed_v1  (0.6122) — first baseline
  └─ arc_governed_v2  (0.6247) — compression to 1.000
       └─ arc_governed_v3  (0.6128, archive_only) — corpus experiment
       └─ arc_governed_v4  (0.7128) — broke plateau via reasoning SFT
            └─ arc_governed_v5  (0.7169) — extension pack
                 └─ arc_governed_v6  (0.7169, archive_only) — tie-archive
                 └─ arc_governed_v7_regressed  (0.6190, archive_only) — regression caught
                 └─ arc_governed_v6_conversation  (0.6836 post-audit, promote, superseded) ← see MODEL_CARD_v10_wave4.md
```

## How to cite this specific model

```bibtex
@software{arc_governed_v6_conversation_2026,
  author  = {Doman, Gary},
  title   = {arc_governed_v6_conversation: Governed Incumbent for ARC-Neuron LLMBuilder v1.0.0},
  year    = 2026,
  version = {v1.0.0-governed},
  url     = {https://github.com/GareBear99/ARC-Neuron-LLMBuilder/releases/tag/v1.0.0-governed}
}
```
