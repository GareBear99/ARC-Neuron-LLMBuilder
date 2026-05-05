# Comparison

Where ARC-Neuron LLMBuilder sits relative to adjacent tools. This is not a takedown of any of these — each is best-in-class at its own job. The point is to show **which job**.

## One-line positioning

| Tool | Owns | Does not own |
|---|---|---|
| **MLflow** | experiment tracking + model registry | governance doctrine, promotion gate, archive bundles |
| **Weights & Biases** | experiment visibility + artifact lineage | promotion gate, rollback bundles, regression floor |
| **Langfuse** | LLM app observability + tracing | training, promotion, archive |
| **llama.cpp** | local GGUF inference | training, governance, archive |
| **vLLM / TGI** | high-throughput inference serving | governance, archive, promotion |
| **Hugging Face Hub** | model hosting + discovery | local governance, regression floor, receipts |
| **EULLM** | sovereign local AI platform | conversation-driven growth loop, regression-aware gate |
| **ARC-Neuron LLMBuilder** | **governed local build loop** | **frontier-scale inference (delegated to adapters)** |

## Detailed side-by-side

### vs. MLflow

| Dimension | MLflow | ARC-Neuron LLMBuilder |
|---|---|---|
| Experiment tracking | ✅ best-in-class | basic (reports/* receipts) |
| Model registry | ✅ rich tags, aliases, versions | scoreboard + Arc-RAR bundles |
| Promotion doctrine | via stages (None → Staging → Production) | **Gate v2**: hard-reject + floor + regression ceilings |
| Regression detection | via custom metrics | **built-in**: per-capability ceilings |
| Restorable archive | via artifact store | **Arc-RAR** with SHA-256 index |
| Local-first | ✅ | ✅ |
| Conversation pipeline | ❌ | ✅ canonical pipeline with receipts |
| Language module | ❌ | ✅ terminology with provenance + trust ranks |

**When to use MLflow**: experiment tracking at scale with polished UI.
**When to use ARC-Neuron LLMBuilder**: governed model lifecycle with attributed regression detection and restorable archives.

### vs. Weights & Biases

| Dimension | W&B | ARC-Neuron LLMBuilder |
|---|---|---|
| Artifact lineage | ✅ beautiful graphs | via Arc-RAR bundle chain + scoreboard |
| Run tracking | ✅ | basic |
| Collaboration | ✅ team features | single-operator focused |
| Gate enforcement | ❌ operator discipline | **machine-enforced Gate v2** |
| Local-first | hybrid | fully local |
| Receipts | implicit | explicit SHA-256 addressable |
| Rollback | via artifact downloads | first-class Arc-RAR restore |

**When to use W&B**: team experiment tracking with hosted dashboards.
**When to use ARC-Neuron LLMBuilder**: solo/small-team governed local model growth with rollback guarantees.

### vs. Langfuse

| Dimension | Langfuse | ARC-Neuron LLMBuilder |
|---|---|---|
| LLM app tracing | ✅ best-in-class | basic conversation records |
| Prompt versioning | ✅ | via prompt profiles |
| Eval datasets | ✅ | ✅ 142 tasks, 14 capabilities (rebuilt v2.0.0) |
| Judge-based scoring | ✅ | keyword rubric (cheap, fast) |
| Training lane | ❌ | ✅ native + external |
| Promotion gate | ❌ | ✅ Gate v2 |
| Archive / rollback | ❌ | ✅ Arc-RAR |

**When to use Langfuse**: observing production LLM apps in the wild.
**When to use ARC-Neuron LLMBuilder**: building and governing the model itself.

**Note**: these are complementary. Langfuse could feed conversation traces into this repo's canonical pipeline as training data.

### vs. llama.cpp / vLLM / TGI

| Dimension | llama.cpp | ARC-Neuron LLMBuilder |
|---|---|---|
| Inference performance | ✅ excellent | delegated (via `llama_cpp_http` adapter) |
| Quantization | ✅ | reads GGUF, doesn't quantize |
| Training | ❌ | ✅ native transformer |
| Benchmarks | minimal | 142 tasks, 14 capabilities (rebuilt, verified) |
| Governance | ❌ | ✅ Gate v2 |
| Archive | ❌ | ✅ Arc-RAR |

**When to use llama.cpp**: running a GGUF model locally.
**When to use ARC-Neuron LLMBuilder**: governing which GGUF model gets used and why.

**They compose perfectly**: `llama-server` hosts the model; `ARC-Neuron LLMBuilder` plugs in via `llama_cpp_http` adapter and governs its lifecycle.

### vs. Hugging Face Hub

| Dimension | HF Hub | ARC-Neuron LLMBuilder |
|---|---|---|
| Model hosting | ✅ best-in-class | local only |
| Discovery | ✅ | no discovery layer |
| Model cards | ✅ standard | ✅ per-incumbent model cards |
| Local governance | ❌ | ✅ Gate v2 |
| Restorable archives | via git revisions | ✅ Arc-RAR with SHA-256 |
| Regression detection | ❌ | ✅ per-capability ceilings |

**When to use HF Hub**: publishing or discovering models.
**When to use ARC-Neuron LLMBuilder**: governing the local lifecycle of a model you're iterating on.

### vs. sovereign local AI platforms (e.g., EULLM)

| Dimension | Sovereign platforms | ARC-Neuron LLMBuilder |
|---|---|---|
| Local execution | ✅ | ✅ |
| Sovereign stack | ✅ | ✅ (part of seven-repo ARC ecosystem) |
| Deployment platform | ✅ | build/gate lane, not deployment |
| Conversation-driven growth | ⚠ varies | ✅ proven end-to-end |
| Gate discipline | ⚠ varies | ✅ four-layer Gate v2 |
| Archive receipts | ⚠ varies | ✅ Arc-RAR |

**When to use a sovereign AI platform**: deploying a model to serve users.
**When to use ARC-Neuron LLMBuilder**: building the model that platform serves.

## Where ARC-Neuron LLMBuilder is uniquely strong

1. **Governed promotion loop with attributed regression detection.** Gate v2 produces a receipt explaining which capability regressed by how much, with reference to the incumbent. Very few open-source tools offer this out of the box.

2. **Conversation-driven growth proven end-to-end.** The v5 → v6_conversation promotion was trained from a corpus the canonical pipeline harvested itself. Not a demo — a governed promotion. Post-audit (v2.0.0): four more governed promotions raised the verified score to 0.9237.

3. **Indexed binary ledger with measured performance.** OBIN v2 is a small, fast, SHA-256-verified event log with O(1) lookup by event ID. Measured: 6,600+ ev/s append, 8,900+ lookups/sec.

4. **Restorable archive bundles with manifest-only readers.** Any prior incumbent can be inspected without extracting the whole ZIP. `read_arc_rar_manifest` reads the manifest from the bundle in isolation.

5. **Four lawful decision states.** `promote`, `archive_only (tie)`, `archive_only (regression)`, `reject` — all four have fired on real candidates with evidence preserved.

6. **Seven-repo ecosystem with frozen roles.** The governance discipline extends across ARC-Core, Cleanroom Runtime, Cognition Core, Language Module, OmniBinary, Arc-RAR, and LLMBuilder. Each repo owns one role.

## Where other tools are better than ARC-Neuron LLMBuilder

1. **Experiment tracking UI** — MLflow and W&B have production-quality web UIs. This repo has JSON files.
2. **Inference throughput** — llama.cpp, vLLM, and TGI are all far ahead. This repo delegates to them via adapters.
3. **Team collaboration** — W&B and HF Hub have proper multi-user flows. This repo is single-operator or small-team focused.
4. **Pre-trained catalog** — HF Hub has millions of models. This repo ships two tiny reference models and expects you to bring your own brain via the adapter boundary.
5. **Frontier-scale model quality** — Claude, GPT, Gemini, Llama are all leagues ahead in raw capability. This repo is not trying to be a frontier model; it's trying to govern one.

## The honest positioning

> ARC-Neuron LLMBuilder is a **governance layer over the model training and promotion lifecycle** — the thing between "I trained a model" and "I'm ready to ship it." It delegates raw inference and raw training compute to adapters. Its contribution is the discipline, the evidence, and the restorable lineage.

If you are building a frontier chatbot, use a frontier model.
If you are governing how a model gets built, compared, promoted, and rolled back in a local or sovereign environment — this is the missing layer.
