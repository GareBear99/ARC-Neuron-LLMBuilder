# Architecture

ARC-Neuron LLMBuilder is organized around four frozen roles that never swap responsibilities. Understanding these roles is the fastest path to using the system correctly.

## The four roles

### 1. Language Module — living truth spine
**Package**: `runtime/terminology.py`, `runtime/language_absorption.py`

Stores the canonical meaning of every term the system has learned. Every term carries:
- **Provenance** — adapter, receipt_id, turn_id, conversation_id, timestamp
- **Trust rank** — `manual_correction` (100) > `correction` (100) > `definition` (70) > `canonical` (65) > `alias` (55) > `relationship` (50) > `observation` (30)
- **Contradiction flags** — when a higher-trust record already exists with a different value
- **Weak-term filter** — fragments shorter than 3 chars or lacking word characters are rejected

The language module grows immediately from every conversation that passes through the canonical pipeline.

### 2. Runtime — continuity shell
**Package**: `runtime/conversation_pipeline.py`, `runtime/reflection_loop.py`, `runtime/model_factory.py`, `adapters/`

The persistent operator shell. Every user interaction goes through the canonical `ConversationPipeline.run_conversation()`:

```
user prompt
  → adapter.generate()
  → ConversationRecord (with SHA-256 hashes of prompt + response)
  → auto-tag training eligibility via scorers.rubric.score_record
  → mirror to OmnibinaryStore as event_type=conversation_turn
  → append to session history
  → return record to caller
```

No side channels. No parallel state. One path.

`ReflectionLoop` wraps any `ModelAdapter` with a draft → critique → revise sequence. The wrapped adapter keeps its `promotable` flag, so reflection can be added or removed without changing governance.

`LanguageAbsorptionLayer` is the bridge: it drives a `ConversationPipeline` turn and then absorbs terminology, capability signals, and continuity signals from the resulting record.

### 3. Cognition Core — build-and-benchmark lab
**Package**: `arc_core/`, `arc_tiny/`, `arc_neuron_small/`, `arc_neuron_tokenizer/`, `scorers/`, `scripts/training/`, `scripts/execution/`

The research lane. This is where:
- Candidates are **trained** via `scripts/training/train_arc_native_candidate.py` (byte-level, AdamW, cosine LR, 90/10 split, real PyTorch).
- GGUF v3 artifacts are written via `arc_tiny/gguf_io.py`.
- The benchmark harness runs candidates against the 142-task suite (rebuilt in v2.0.0-audited).
- The rubric scorer produces per-capability scores.
- `scripts/execution/promote_candidate.py` applies Gate v2 to decide promote, archive_only, or reject.

The single canonical transformer lives in `arc_core/transformer.py`. Tiny and Small are thin presets over it — there is no copy-paste between tiers, so any bug fixed in the base is fixed for the whole family.

### 4. Archive — restorable lineage
**Package**: `runtime/learning_spine.py`, `scripts/ops/bundle_promoted_candidate.py`

Three binary formats:

- **OBIN v2** — indexed Omnibinary ledger. Magic bytes, version header, timestamped UTC header, length-prefixed event records. Sidecar `.idx` JSON maps `event_id → byte_offset` for O(1) lookup. Integrity verified by SHA-256. Append-safe; index auto-rebuilds from scan if corrupt or missing.

- **ANCF v1** — ARC Neuron Canonical Format. Wraps a GGUF file with embedded JSON metadata. Magic bytes, version, meta-len, gguf-len, meta bytes, gguf bytes. SHA-256 on both payloads.

- **Arc-RAR bundle** — ZIP archive of a promoted candidate: manifests (training, exemplar, promotion, floor), receipts, checkpoint, GGUF, exemplar JSON, SHA-256 index. Readable in isolation via `read_arc_rar_manifest()`.

## How they compose

```
  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
  │ Language     │     │  Runtime     │     │  Cognition   │
  │ Module       │◄────┤  Pipeline    │────►│  Core        │
  │              │     │              │     │              │
  │ terms +      │     │ canonical    │     │ transformer  │
  │ provenance   │     │ conversation │     │ training     │
  │ + trust      │     │ + reflection │     │ benchmarks   │
  │ + contrad.   │     │ + absorption │     │ gate v2      │
  └──────┬───────┘     └──────┬───────┘     └──────┬───────┘
         │                    │                    │
         │                    ▼                    │
         │            ┌──────────────┐             │
         └───────────►│  Archive     │◄────────────┘
                      │              │
                      │ Omnibinary   │
                      │ (OBIN v2)    │
                      │ ANCF         │
                      │ Arc-RAR      │
                      │ bundles      │
                      └──────────────┘
```

**Rules**:
- Memory and truth stay outside the model. The language module is the authority, not the weights.
- The model learns in controlled promotion waves, not live during conversation.
- Every transition produces a receipt. No state change happens without a trace.
- The archive is addressable by SHA-256. Any prior state is restorable.

## Package-level map

```
arc_core/
    transformer.py        # Single canonical CausalTransformerLM + TransformerConfig
arc_tiny/
    model.py              # TinyConfig preset (~0.05M params)
    gguf_io.py            # GGUF v3 reader/writer (stdlib + numpy only)
arc_neuron_small/
    model.py              # SmallConfig preset (~0.18M params)
arc_neuron_tokenizer/
    builder.py            # Hybrid byte + wordpiece tokenizer builder
adapters/
    base.py               # ModelAdapter ABC + ModelResponse
    exemplar_adapter.py   # Cosine-retrieval adapter over training records
    heuristic_adapter.py  # Synthetic smoke-test adapter (promotable=False)
    echo_adapter.py       # Echo adapter for testing
    command_adapter.py    # Local binary adapter (llama-cli, llamafile)
    llama_cpp_http_adapter.py   # OpenAI-compatible HTTP adapter
    openai_compatible_adapter.py  # Generic OpenAI-compatible HTTP adapter
runtime/
    conversation_pipeline.py   # Canonical single-path pipeline
    reflection_loop.py         # Draft → critique → revise wrapper
    language_absorption.py     # Conversation → terminology/signals bridge
    terminology.py             # Live terminology store with Omnibinary mirror
    learning_spine.py          # OmnibinaryStore + ANCF + Arc-RAR helpers
    floor_model.py             # Regression floor (never-below baseline)
    model_factory.py           # Adapter name normalization + construction
    task_loader.py             # Benchmark task validation and loading
scorers/
    rubric.py                  # Task-aware capability scorer (23 buckets)
scripts/
    training/
        train_arc_native_candidate.py   # Real weight training + GGUF export
        train_lora_candidate.py         # LoRA routing (native or scaffold)
        train_exemplar_candidate.py     # Exemplar-only training path
        train_preference_candidate.py   # Preference pair training (DPO-style)
        prepare_distillation_corpus.py  # Corpus assembly for training
    execution/
        run_model_benchmarks.py         # Benchmark harness
        score_benchmark_outputs.py      # Scoring with rubric
        promote_candidate.py            # Gate v2 implementation
        run_full_candidate_gate.py      # Full gate cycle runner
        run_direct_candidate.py         # One-shot direct prompt
    ops/
        bootstrap_keys.py               # Runtime secret generator
        bundle_promoted_candidate.py    # Arc-RAR bundle builder
        benchmark_omnibinary.py         # Omnibinary performance measurement
        run_n_cycles.py                 # N-cycle repeatability runner
        run_proof_workflow.py           # Single-script end-to-end proof
        demo_proof_workflow.py          # 9-step demo workflow
        generate_reflection_sft.py      # Reflection SFT pair generator
        absorb_session.py               # One-command session absorption
specs/
    promotion_gate_v2.yaml             # Gate doctrine
    benchmark_schema_v2.yaml           # Benchmark task schema
    cognition_contract_v1.yaml         # System contract
    cognition_doctrine_v1.md           # Operating doctrine
benchmarks/                            # 165 tasks across 16 benchmark files (rebuilt)
configs/                               # Base model candidates, training stages, runtime profiles
datasets/                              # Seed and distilled SFT corpora
reports/                               # Promotion receipts, repeatability reports, benchmark numbers
artifacts/                             # GGUF models, Arc-RAR bundles, Omnibinary ledger
exports/candidates/                    # Trained candidate artifacts
results/                               # Benchmark outputs, scored summaries, scoreboard
tests/                                 # 136-test suite
docs/                                  # Extended documentation
```

## Data flow — a single governed promotion

1. **Collect** — `scripts/training/train_arc_native_candidate.py` mines `datasets/distillation_sft/*.jsonl` and repo text into a byte corpus.
2. **Train** — AdamW + cosine LR + gradient clip. 90/10 train/val split. Val perplexity tracked.
3. **Export** — `.pt` checkpoint + GGUF v3 via `arc_tiny/gguf_io.py` + exemplar sidecar (`exemplar_model.json`) for the benchmark harness.
4. **Benchmark** — `scripts/execution/run_model_benchmarks.py` runs the 142-task suite through the `ExemplarAdapter` (TF-IDF retrieval), captures per-task outputs as JSONL.
5. **Score** — `scripts/execution/score_benchmark_outputs.py` applies the rubric to produce per-capability summaries and overall weighted score.
6. **Gate** — `scripts/execution/promote_candidate.py` applies Gate v2 (hard-reject → floor model → regression ceilings → beat-incumbent) and emits a promotion receipt.
7. **Bundle** — on promote or archive_only, `scripts/ops/bundle_promoted_candidate.py` packages the candidate into a SHA-256-indexed Arc-RAR archive.
8. **Mirror** — the promotion receipt is appended to the Omnibinary ledger for O(1) lookup.
9. **Lock** — after a real promote, `runtime/floor_model.py --set-floor --from-scoreboard` updates the regression floor to the new incumbent's scores.

Every step is independently replayable. Every artifact has a SHA-256 that ties back to the source truth.

## Adapter boundary

The adapter boundary is the integration point for stronger models. Any class that implements `adapters.base.ModelAdapter` can:
- Participate in the canonical conversation pipeline.
- Be wrapped with `ReflectionLoop`.
- Drive the benchmark harness.
- Be gated by Gate v2.
- Be bundled via Arc-RAR.

Built-in adapters:
- `exemplar` — cosine retrieval over training records (default for governed native lane)
- `heuristic` — synthetic smoke test, never promotable
- `echo` — echo-back adapter for testing
- `command` — local binary (llama-cli, llamafile) via subprocess with timeout + state-trace
- `llama_cpp_http` — OpenAI-compatible HTTP client for local llama.cpp server
- `openai_compatible` — generic OpenAI-compatible HTTP client with optional Bearer key

To plug in a stronger base model, start an OpenAI-compatible server (llama.cpp, vLLM, TGI, etc.) and set:

```bash
export COGNITION_RUNTIME_ADAPTER=llama_cpp_http
export COGNITION_BASE_URL=http://127.0.0.1:8080
export COGNITION_MODEL_NAME=my-model
```

All governance machinery operates unchanged against the new brain.

## Philosophy

The shell is deliberately stronger than the brain. A weak shell with a strong model is fragile — any governance gap becomes an incident. A strong shell with a weaker model can keep improving without losing coherence. The ARC-Neuron family is small because the contribution is the governance; the adapter boundary is the pluggability contract for when you want a larger brain.
