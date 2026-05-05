# Frequently Asked Questions

Searchable index of the most common questions about ARC-Neuron LLMBuilder.

## Table of contents

- [What is this?](#what-is-this)
- [How is this different from MLflow / Weights & Biases / Langfuse?](#comparison)
- [Can this compete with ChatGPT or Claude?](#frontier)
- [Do I need a GPU?](#gpu)
- [Do I need to download a model?](#download-model)
- [What is "Gate v2"?](#gate-v2)
- [What is "Omnibinary"?](#omnibinary)
- [What is "Arc-RAR"?](#arc-rar)
- [What is the "floor model"?](#floor-model)
- [How do I plug in Qwen / Llama / DeepSeek?](#external-model)
- [Can the system learn from my conversations?](#learning)
- [Is my data local?](#local)
- [What is a "promotion receipt"?](#receipts)
- [Can I roll back a promoted model?](#rollback)
- [How do I contribute a new benchmark?](#contribute-benchmark)
- [How do I report a gate decision I think is wrong?](#gate-issue)
- [What are the seven ARC repos?](#ecosystem)
- [What's the license?](#license)
- [Can I use this commercially?](#commercial)
- [How do I cite this project?](#cite)

---

## <a id="what-is-this"></a>What is this?

ARC-Neuron LLMBuilder is a local-first, governed cognition lab. You train small language models, measure them, and promote the better ones through a regression-aware gate — with full receipts, restorable archives, and an indexed event ledger. The included ARC-Neuron Tiny and Small models prove the pipeline is real; the adapter boundary lets you plug in any stronger base model while preserving all governance.

**Keywords**: local AI, governed AI, LLM builder, promotion gate, model registry, regression floor, indexed ledger, conversation pipeline, reflection loop, terminology absorption, GGUF, llama.cpp wrapper, sovereign AI, private AI, on-prem AI.

## <a id="comparison"></a>How is this different from MLflow / Weights & Biases / Langfuse?

- **MLflow / W&B** — strong on experiment tracking and model registry. They log what you ran. They don't enforce a doctrine for when a candidate is safe to promote.
- **Langfuse** — strong on LLM app observability. It traces conversations. It doesn't train, gate, or archive models.
- **llama.cpp** — strong on local inference. It runs GGUF models efficiently. It doesn't govern the lifecycle around them.

ARC-Neuron LLMBuilder is a **governed build loop** — it owns what happens between "train a candidate" and "ship it to users." See [COMPARISON.md](./COMPARISON.md) for the full side-by-side.

## <a id="frontier"></a>Can this compete with ChatGPT or Claude?

No — not directly, and not with the included native models. The included ARC-Neuron Tiny (~0.05M params) and Small (~0.18M params) are proof-of-pipeline tiers. They are deliberately small because the contribution is the **governance**, not the raw brain.

To compete at usability with frontier assistants, plug a strong open-weights base model (e.g. Qwen3-32B, Llama-4, DeepSeek) into the `llama_cpp_http` or `command` adapter. The governance machinery operates unchanged. See [USAGE.md](./USAGE.md#plugging-in-a-stronger-model-backend).

## <a id="gpu"></a>Do I need a GPU?

No for the included tiers. The ARC-Neuron Tiny and Small models train on CPU in 2-5 minutes per candidate. For the `base` tier (larger params, 256-block context) a GPU is recommended. For any real external model via `llama.cpp` or `vLLM`, the usual inference-side GPU requirements apply.

## <a id="download-model"></a>Do I need to download a model?

No. The repo ships with `arc_governed_v10_wave4` as the current incumbent (overall score 0.9237). Clone, install, and run `scripts/ops/demo_proof_workflow.py` — everything works out of the box.

## <a id="gate-v2"></a>What is "Gate v2"?

The regression-aware promotion gate. It decides whether a new candidate can displace the current incumbent. Four layers: hard-reject floor, floor model (never-below baseline), per-capability regression ceilings, and beat-the-incumbent. Four outcomes: `promote`, `archive_only (tie)`, `archive_only (regression)`, `reject`. Full doctrine: [GOVERNANCE_DOCTRINE.md](./GOVERNANCE_DOCTRINE.md).

## <a id="omnibinary"></a>What is "Omnibinary"?

The indexed binary ledger that mirrors every event (conversation turn, terminology change, promotion decision) into an append-safe, SHA-256-verifiable format with O(1) lookup by event ID. Format is OBIN v2. Measured on commodity hardware: ~6,600 events/sec append, ~8,900 lookups/sec, p99 latency ~0.22ms. See [ARCHITECTURE.md](./ARCHITECTURE.md#4--archive--restorable-lineage).

## <a id="arc-rar"></a>What is "Arc-RAR"?

The restorable archive bundle format. Every promoted candidate gets packaged into a ZIP with manifests, receipts, checkpoint, GGUF, exemplar artifact, and a SHA-256 index. Any prior incumbent can be restored from its bundle at any time. Manifest is readable in isolation — no special tooling required.

## <a id="floor-model"></a>What is the "floor model"?

A never-below baseline locked from the current incumbent with a 10% safety margin. Every future candidate must clear the floor on every guarded capability (repair, calibration, planning, compression, paraphrase_stability, overall_weighted_score, failure_rate). Prevents slow drift into weirdness. Updated after every real promote via `runtime/floor_model.py --set-floor --from-scoreboard`.

## <a id="external-model"></a>How do I plug in Qwen / Llama / DeepSeek?

Start any OpenAI-compatible server (llama.cpp, vLLM, TGI):

```bash
llama-server -m /path/to/qwen3-32b-instruct-q5_k_m.gguf --port 8080 -c 8192

export COGNITION_RUNTIME_ADAPTER=llama_cpp_http
export COGNITION_BASE_URL=http://127.0.0.1:8080
export COGNITION_MODEL_NAME=qwen3-32b-instruct
```

Every governance command now operates against the external model with zero code changes. Full details: [USAGE.md](./USAGE.md#plugging-in-a-stronger-model-backend).

## <a id="learning"></a>Can the system learn from my conversations?

Yes. Two channels:

- **Live**: the language module absorbs terminology, capability signals, and continuity signals from every conversation turn that passes through the canonical pipeline. This happens immediately.
- **Periodic**: conversations that auto-tag as training-eligible are exported as SFT corpora. On the next training wave, those corpora feed the candidate. This is how v5 → v6_conversation closed the doctrine loop. Post-audit (v2.0.0), four additional cycles raised the verified score to 0.9237.

## <a id="local"></a>Is my data local?

Yes, by default. Nothing is sent to any external server unless you explicitly configure the `openai_compatible` adapter to point at a remote endpoint. Omnibinary, Arc-RAR, and terminology stores all live under `artifacts/` in the repo working directory.

## <a id="receipts"></a>What is a "promotion receipt"?

A JSON record written to `reports/promotion_decision.json` (latest) and `reports/cycle_*_promo.json` (per-cycle) that captures every input and decision of a Gate v2 run: the candidate entry, the incumbent it challenged, hard-reject status, floor violations, regression violations, the decision, the decision reason, and the Arc-RAR bundle path if one was built. Every receipt is SHA-256 addressable.

## <a id="rollback"></a>Can I roll back a promoted model?

Yes. Every promoted candidate is stored in `artifacts/archives/arc-rar-<candidate>-<hash>.arcrar.zip` with its full training artifacts, receipts, and manifests. Read the manifest in isolation:

```python
from runtime.learning_spine import read_arc_rar_manifest
from pathlib import Path
mf = read_arc_rar_manifest(Path("artifacts/archives/arc-rar-arc_governed_v5-0721488f.arcrar.zip"))
```

Copy the exemplar artifact from the bundle into `exports/candidates/<name>/` to restore.

## <a id="contribute-benchmark"></a>How do I contribute a new benchmark?

File a "📊 Benchmark contribution proposal" issue. Tasks must conform to `specs/benchmark_schema_v2.yaml`. Required fields: `id`, `capability`, `domain`, `difficulty`, `prompt`, `reference`, `scoring`, `tags`. See [EXAMPLES.md](./EXAMPLES.md) for example task shapes.

## <a id="gate-issue"></a>How do I report a gate decision I think is wrong?

File a "⚖️ Gate behavior report" issue. Attach `reports/promotion_decision.json`, the scored outputs summary, and the scoreboard state. These reports are treated as first-class evidence.

## <a id="ecosystem"></a>What are the seven ARC repos?

1. **[ARC-Core](https://github.com/GareBear99/ARC-Core)** — event/receipt/authority spine
2. **[arc-lucifer-cleanroom-runtime](https://github.com/GareBear99/arc-lucifer-cleanroom-runtime)** — deterministic operator kernel
3. **[arc-cognition-core](https://github.com/GareBear99/arc-cognition-core)** — model-growth lab
4. **[arc-language-module](https://github.com/GareBear99/arc-language-module)** — canonical lexical truth
5. **[omnibinary-runtime](https://github.com/GareBear99/omnibinary-runtime)** — binary mirror / runtime ledger
6. **[Arc-RAR](https://github.com/GareBear99/Arc-RAR)** — archive/rollback bundles
7. **ARC-Neuron-LLMBuilder** *(this repo)* — governed build loop

Full role contract: [ECOSYSTEM.md](./ECOSYSTEM.md).

## <a id="license"></a>What's the license?

MIT. See [LICENSE](./LICENSE).

## <a id="commercial"></a>Can I use this commercially?

Yes. MIT allows commercial use, modification, and redistribution. Attribution is required. The included ARC-Neuron Tiny and Small models are also MIT-licensed.

## <a id="cite"></a>How do I cite this project?

BibTeX in [CITATION.cff](./CITATION.cff):

```bibtex
@software{arc_neuron_llmbuilder_2026,
  author  = {Doman, Gary},
  title   = {ARC-Neuron LLMBuilder: A Governed Local AI Build-and-Memory System},
  year    = 2026,
  version = {v1.0.0-governed},
  url     = {https://github.com/GareBear99/ARC-Neuron-LLMBuilder}
}
```
