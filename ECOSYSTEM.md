# The ARC Ecosystem

ARC-Neuron LLMBuilder is **one of seven repositories** in the ARC governed-AI ecosystem. Each repo owns a single frozen role. Together they form a local-first AI operating system with full lineage, receipts, and rollback.

This document explains what each repository actually does, in depth — not just its one-line tagline.

---

## Quick index

| # | Repo | Role in one line |
|---|---|---|
| 1 | [ARC-Core](#1-arc-core) | Event / receipt / authority spine — the source-of-truth event graph |
| 2 | [arc-lucifer-cleanroom-runtime](#2-arc-lucifer-cleanroom-runtime) | Deterministic local operator kernel — bounded execution with replay |
| 3 | [arc-cognition-core](#3-arc-cognition-core) | Model-growth lab — build, benchmark, shape, promote cognition candidates |
| 4 | [arc-language-module](#4-arc-language-module) | Canonical lexical truth — governed multilingual language backend |
| 5 | [omnibinary-runtime](#5-omnibinary-runtime) | Binary mirror / runtime ledger — native-first binary intake and execution fabric |
| 6 | [Arc-RAR](#6-arc-rar) | Archive / rollback bundles — CLI-first archive manager with native-app control |
| 7 | [ARC-Neuron-LLMBuilder](#7-arc-neuron-llmbuilder) | Governed build loop — canonical pipeline, Gate v2, reflection, absorption |

---

## 1. ARC-Core

**Repo:** https://github.com/GareBear99/ARC-Core
**Role:** Event / receipt / authority spine

### What it does

ARC-Core is the canonical event-and-receipt engine for the entire ecosystem. Every other repo that needs to prove *something happened* routes that fact through ARC-Core. It is the authoritative source of truth for:

- **Event graph** — every state change across the system, from conversation turns to promotion decisions to archive restores, is modeled as an event with a unique ID and a SHA-256 hash.
- **Receipts** — tamper-evident records of what action was taken, when, by which component, and what the before/after state was.
- **Authority gating** — who can propose, approve, execute, and attest to changes. ARC-Core decides which agents, services, or users are allowed to produce a given class of event.
- **Proposal/evidence discipline** — before an action takes effect, it is proposed as an event with supporting evidence; the evidence lives alongside the proposal in the graph.
- **Case and watchlist structures** — the signal-intelligence layer that lets operators organize events into investigations and tracked concerns.

### Why it exists

Most AI systems either trust everything or log everything. Neither works at scale. ARC-Core is the middle path: every meaningful state change is **a first-class event with a proposal, evidence, an authority, a receipt, and a hash**. That makes it possible to reconstruct, audit, and replay any decision the system has ever made.

### Concrete capabilities

- Role-based dependency injection at every sensitive endpoint
- Risk scoring (confidence × severity × log-capped event count × edge count, with watchlist boost)
- Geospatial / blueprint / calibration / track / incident event types
- Proposal → evidence → receipt flow with full SHA-256 lineage
- Audit report generation

### How it integrates with LLMBuilder

Every promotion receipt written by `scripts/execution/promote_candidate.py` is an ARC-Core-style event: it carries a decision, the inputs, the authority (Gate v2), the evidence (scored outputs), and a SHA-256 identity. Future integrations will co-sign these receipts with an ARC-Core signing key so that any third party can verify that a given promotion really happened in your lab.

---

## 2. arc-lucifer-cleanroom-runtime

**Repo:** https://github.com/GareBear99/arc-lucifer-cleanroom-runtime
**Role:** Deterministic local operator kernel

### What it does

Cleanroom Runtime is the **deterministic execution shell** the rest of the system eventually runs inside. Where ARC-Core answers "did it happen?", Cleanroom answers "did it happen the same way every time, and can we roll it back?" It provides:

- **Event-sourced kernel** — a `KernelEngine` with an append-only log. The system's state is derived by replaying events, never by mutating in place.
- **Policy evaluation** — every proposed operation is evaluated against declared policies before it runs. Violations produce rejections, not partial states.
- **Branch planning** — speculative forks of the event log let the system explore alternative actions without committing them.
- **Receipt recording** — every operation that executes leaves a receipt in the log.
- **`state_at(event_id)`** — point-in-time replay. You can reconstruct the system's state as of any past event ID.
- **SQLite backup + JSONL import/export** — durable local storage with portable exchange format.
- **Directive continuity** — long-running operator goals that survive restarts, context compaction, and adapter swaps.

### Why it exists

LLMs are stochastic. The systems around them should not be. Cleanroom Runtime is the deterministic substrate that lets you take a stochastic component (a model) and wrap it in a shell where every decision is reproducible. If something went wrong, `state_at(event_id)` shows you exactly what the world looked like; replaying from that point runs the same sequence of operations and produces the same receipts.

### Concrete capabilities

- Append-only event log with ordered, typed events
- Policy engine that can reject operations before they execute
- Branch/merge of speculative state
- Bounded continuity across sessions and restarts
- Bluetooth, robotics, perception, and memory bridges (optional, each a distinct module)
- Resilience primitives: continuation manager, fallback selector, retry budget, failure classifier
- Code editing with patch planner, symbol index, line map, verifier
- Self-improve subsystem: adversarial testing, benchmarks, candidates, sandbox, training

### How it integrates with LLMBuilder

LLMBuilder's canonical conversation pipeline produces `ConversationRecord` receipts with SHA-256 hashes; Cleanroom's long-term direction is to host that pipeline inside its deterministic kernel so the entire train → benchmark → gate → bundle loop becomes **branchable and replayable**. Today the integration is doctrinal (both follow the same receipt discipline); the full federation is a v1.3.0 milestone.

---

## 3. arc-cognition-core

**Repo:** https://github.com/GareBear99/arc-cognition-core
**Role:** Model-growth lab

### What it does

Cognition Core is the **build-and-benchmark lab** for cognition candidates. It is the upstream of LLMBuilder in spirit — where LLMBuilder focuses on the canonical conversation pipeline and Gate v2 for native small models, Cognition Core focuses more broadly on:

- **Candidate cognition shaping** — SFT, preference shaping, reflection-style post-training, persona shaping.
- **GGUF-oriented evaluation doctrine** — designed around local GGUF artifacts as the deployable unit.
- **Promotion gate lineage** — the v1 gate that LLMBuilder's Gate v2 evolved from, with the same discipline of hard-reject floor + regression detection + incumbent protection.
- **Benchmark scaffolding** — the task-schema discipline (id, capability, domain, difficulty, prompt, reference, scoring, tags) that LLMBuilder inherits.
- **MCP-style tool descriptors** — cognition candidates can declare tool surfaces they expect their runtime to provide.
- **Run manifests and experiment tracking** — every training run produces a manifest linking corpus, hyperparameters, artifact paths, and benchmark results.
- **Release bundle generation** — packaging candidate models for distribution.

### Why it exists

Cognition Core is where the **cognition doctrine** lives — the rules that define what "a cognition candidate" even means. It predates the narrower LLMBuilder release and carries the broader vision: anything that can plug into the ecosystem as a reasoning surface (model, tool, agent) is evaluated and promoted here.

### Concrete capabilities

- Candidate cognition build flow (SFT, preference, merge, export)
- Doctrine, contract, promotion gate v1, dataset policy, benchmark schema
- Execution-first adapter/runtime/scoring/promotion flow
- MCP-style tool descriptors + screenshot-attachment integration path
- Production hardening: CI, tests, validation, release bundle generation
- GGUF backend path, run manifests, experiment tracking

### How it integrates with LLMBuilder

LLMBuilder is the governance-first specialization of Cognition Core's doctrine. Gate v2, the floor model, the reflection loop, and the canonical conversation pipeline in LLMBuilder are all **operational extensions** of concepts first expressed in Cognition Core. Future releases will re-sync: Cognition Core will adopt Gate v2 formally, and LLMBuilder will expose its MCP-style tool descriptors for downstream cognition candidates.

---

## 4. arc-language-module

**Repo:** https://github.com/GareBear99/arc-language-module
**Role:** Canonical lexical truth

### What it does

The Language Module is the **governed multilingual language backend**. It is the authoritative store for what a word means, how it is spelled, what it maps to in other languages, and where each of those facts came from. Concretely:

- **Governed ingestion** — new language data enters through provenance-aware flows, not bulk blind merges. Every lemma, variant, concept, pronunciation, and transliteration carries a source, a confidence, and a trust rank.
- **Readiness / gap states** — the module knows what it *doesn't* know. A term that is partially attested returns as "readiness: partial" with a gap description rather than a silent guess.
- **Self-fill orchestration** — when the module detects gaps, it can propose self-fill operations with explicit approval gates (the "approved self-fill bootstrap" flow).
- **Arbitration** — when two sources disagree on the same term, the module flags the contradiction and records both records with their respective trust ranks.
- **Release pipelines** — language data ships in governed, replayable snapshots with integrity checks. Any released snapshot can be rolled back.
- **Retention / compaction** — old language state is compactable without losing audit lineage.
- **Speech and translation provider abstraction** — optional external providers (ASR, TTS, MT) plug in through a governed boundary; the module is not itself a TTS or MT engine, it is the truth layer they consult.
- **Onboarding** — a structured flow for adding a new language to the module.

### Why it exists

Most language software treats words as strings. The Language Module treats words as **first-class governed records with provenance**. That is necessary when you want an AI system to have stable, auditable, rollback-safe language behavior — if an agent says "omnibinary means X", the module is the authority on whether that is actually canonical.

### Concrete capabilities

- FastAPI-style service with routers: acquisition, core, knowledge, runtime
- 40+ internal services: aliases, arbitration, concepts, coverage, detection, etymology, evidence_export, governance, importers, lineage, linguistic_analysis, manifests, onboarding, orchestration, package_lifecycle, phonology, policy, pronunciation, provider actions/registry, relationships, release_integrity, runtime_receipts, search, seed_ingest, self_fill (+ arbitration/release/replay/retention/sources), source_policy, speech_provider, stats, system_status, translate_explain, translation_* , transliteration, variants
- Release integrity with replayable snapshots
- SQLite-backed storage with retention policies
- Evidence export and governance workflow endpoints
- 25+ tracked test versions (v22 → v36)

### How it integrates with LLMBuilder

LLMBuilder's in-repo `runtime/terminology.py` is a **lightweight local mirror** of the Language Module's discipline. It does definition/alias/correction extraction, provenance tracking, trust ranks, and contradiction flags — but it stores locally in JSON because the full Language Module is a separately-deployable service. The v1.3.0 roadmap item "Language Module canonicalization" will replace the local JSON store with live Language Module integration, so that terminology learned inside LLMBuilder flows directly into the governed multilingual truth surface.

---

## 5. omnibinary-runtime

**Repo:** https://github.com/GareBear99/omnibinary-runtime
**Role:** Binary mirror / runtime ledger

### What it does

OmniBinary is the **native-first binary intake, classification, and execution-fabric** layer. Where the other repos deal in JSON events and text receipts, OmniBinary deals in the binary substrate underneath. It is designed to:

- **Intake native binaries** — executables, libraries, GGUF model weights, ANCF artifacts, compiled code — into a classified, signed, deterministic store.
- **Classify and decode** — identify what each binary is, what its execution characteristics are, and produce a deterministic decoding of its relevant parts.
- **Provide a runtime ledger** — an indexed, SHA-256-verifiable mirror of every binary state change so that "what binary ran when" is always answerable.
- **Federated execution lanes** — separate lanes for managed, native, and dynamic-binary-translation (DBT) execution, each with its own policy and receipts.
- **Receipts-first observability** — every binary operation produces a receipt before it produces a result.
- **Cache integrity before speed** — block-cache and translation-cache policies that prioritize correctness over raw throughput.
- **Personality contracts** — distinct execution profiles (e.g. Linux-native personality) with explicit capability declarations.

### Why it exists

The same doctrine that applies to text events (every action has a receipt, every receipt is addressable, every prior state is restorable) needs to apply to binaries. Otherwise the moment a model artifact is converted, quantized, or repackaged, its lineage drops out of the governed system. OmniBinary's job is to keep binaries inside the receipt economy.

### Concrete capabilities (Rust crates)

- `obi-cache` — block-level content-addressable cache
- `obi-cli` — operator command-line surface
- `obi-config` — runtime configuration
- `obi-core` — core execution fabric
- `obi-intake` — binary intake and classification
- `obi-ir` — intermediate representation
- `obi-jit-cranelift` — JIT via Cranelift
- `obi-jit-llvm` — JIT via LLVM
- `obi-lane-dbt` — dynamic binary translation lane
- `obi-lane-managed` — managed execution lane
- `obi-lane-native` — native execution lane
- `obi-loader` — binary loader
- `obi-personality-linux` — Linux execution personality
- `obi-policy` — policy engine
- `obi-receipts` — runtime receipt format
- Extensive design docs: ADRs, cache contracts, decoder contracts, lane matrix, truth ledger, sandbox contract, personality contract

### How it integrates with LLMBuilder

The OBIN v2 format in LLMBuilder's `runtime/learning_spine.py` is the **simplified event-log substrate** that maps onto OmniBinary's runtime-ledger direction. LLMBuilder's Omnibinary is specialized for conversation turn events and promotion receipts in JSON form; full OmniBinary handles arbitrary binary artifacts with JIT lanes. The v1.3.0 federation roadmap connects the two: LLMBuilder's `.obin` files become subscribable by OmniBinary so GGUF exports and Arc-RAR bundles appear natively in the binary-side event graph.

---

## 6. Arc-RAR

**Repo:** https://github.com/GareBear99/Arc-RAR
**Role:** Archive / rollback bundles

### What it does

Arc-RAR is the **CLI-first archive manager with a native-app control surface**. It is the system-wide archive and rollback substrate. Every promoted cognition candidate, every governed state snapshot, every release artifact across the ecosystem is eligible to live inside an Arc-RAR bundle. Concretely:

- **Archive bundles** — portable, self-describing, manifest-indexed archives. Unlike a plain ZIP, an Arc-RAR bundle has a structured manifest readable in isolation and a SHA-256 index covering every file it contains.
- **CLI-first operation** — every archive operation is scriptable via the Arc-RAR CLI. No GUI is required; a GUI exists for operator convenience but is a thin wrapper over the CLI.
- **Native-app control** — platform-native desktop apps (Linux GTK, macOS, Windows WinUI) for managing archives when a GUI is preferred.
- **Governed extraction** — extraction is evidence-producing. Extracting a bundle leaves a receipt describing what was extracted, where, and for whom.
- **Automation** — an `arc-rar-automation` crate that wraps the CLI for CI/CD and operator-script integration.
- **FFI** — foreign-function-interface crate for embedding Arc-RAR inside other processes.
- **IPC** — inter-process-communication crate for talking to a long-running archive daemon.
- **Rollback semantics** — any archived state is addressable by SHA-256; restoring a prior version is a first-class operation, not a special-case recovery.

### Why it exists

Most archive managers (ZIP, tar, 7z, winrar) are "put files in a file." They don't know what's inside. Arc-RAR is built around the idea that an archive is a **governed artifact with a manifest, a lineage, and a restore contract**. You should be able to ask an archive "what candidate model are you?", "what promotion receipt do you contain?", "what's the SHA-256 of your GGUF?", and "can I restore only the exemplar artifact without the full weights?" — and get answers without extracting anything.

### Concrete capabilities (Rust crates + apps)

- `arc-rar-automation` — CLI wrapper for automation/CI
- `arc-rar-cli` — primary operator command-line
- `arc-rar-common` — shared types and constants
- `arc-rar-core` — archive format implementation
- `arc-rar-ffi` — FFI surface for embedding
- `arc-rar-ipc` — IPC for daemon mode
- Desktop apps: Linux GTK (`arc-rar-gtk`), macOS (ArcRAR), Windows WinUI (`ArcRAR.WinUI`)
- Design docs covering autowrap/intent validation, CLI spec, FFI bridge, GUI-daemon bridge, IPC spec, symlinks and shell integration
- Cross-platform packaging: Linux, macOS, Windows

### How it integrates with LLMBuilder

Every promoted LLMBuilder candidate is packaged via `scripts/ops/bundle_promoted_candidate.py` into an `arc-rar-<candidate>-<hash>.arcrar.zip` file that is **structurally compatible** with Arc-RAR — same manifest format, same SHA-256 index, same restore semantics. Today LLMBuilder produces bundles that Arc-RAR *could* read (the Python bundle builder reproduces the format by design); the v1.3.0 milestone wires the actual Arc-RAR tooling to directly index, list, and restore LLMBuilder bundles from anywhere on disk.

---

## 7. ARC-Neuron-LLMBuilder

**Repo:** https://github.com/GareBear99/ARC-Neuron-LLMBuilder *(you are here)*
**Role:** Governed build loop

### What it does

LLMBuilder is where the whole ecosystem's doctrine becomes **operational for a live governed model-growth loop**. Every other repo contributes primitives; LLMBuilder assembles them into a working build → benchmark → gate → archive → verify cycle with **seven governed promotions on record** (three at v1.0.0, four post-audit at v2.0.0). Concretely:

- **Canonical conversation pipeline** — `runtime/conversation_pipeline.py`. Every user interaction passes through one path that produces a SHA-256-addressable `ConversationRecord`, mirrors it into the Omnibinary ledger, auto-tags training eligibility, and returns the record.
- **Gate v2 promotion** — `scripts/execution/promote_candidate.py`. Four-layer governance: hard-reject floor, floor model, regression ceilings, beat-the-incumbent. Four lawful decision states: promote, archive_only (tie), archive_only (regression), reject.
- **Floor model** — `runtime/floor_model.py`. Never-below baseline locked from the current incumbent with 10% safety margin. Updated after every real promote.
- **Reflection loop** — `runtime/reflection_loop.py`. Wraps any adapter with draft → critique → revise before emission.
- **Language absorption** — `runtime/language_absorption.py`. Automatic terminology extraction from conversation with provenance, trust ranks, and contradiction detection.
- **Terminology store** — `runtime/terminology.py`. Local governed store of learned terms with definition/alias/correction/canonical/relationship extraction.
- **OBIN v2 indexed ledger** — `runtime/learning_spine.py`. ~6,600 events/sec append, ~8,900 O(1) lookups/sec, SHA-256 verified, index auto-rebuilds on drift.
- **Arc-RAR bundle format (Python implementation)** — `scripts/ops/bundle_promoted_candidate.py`. Produces bundles structurally compatible with the Arc-RAR tooling.
- **Native training lane** — `scripts/training/train_arc_native_candidate.py`. Real PyTorch training, GGUF v3 export, exemplar sidecar for the benchmark harness.
- **142-task benchmark suite** across 14 capability families (rebuilt and verified in v2.0.0-audited).
- **115-test suite** covering the full loop (115 passing, 1 skipped).
- **Adapter boundary** — `adapters/base.py`. Plug in any model backend (exemplar, llama.cpp, vLLM, TGI, OpenAI-compatible) with zero governance changes.

### Why it exists

The other six repos each own a role. LLMBuilder owns the **assembly** — the place where "train a candidate → benchmark it → decide if it's better → archive the decision" is actually wired together and proven to work repeatedly. Seven governed promotions on record — v4 (0.7128), v5 (0.7169), v6 (0.6836†), **v7 (0.8537), v8 (0.8883), v9 (0.8911), v10 (0.9237)** — demonstrate the assembly is real. †True post-audit baseline; pre-audit was 0.7333 inflated by synthetic benchmarks.

### Concrete capabilities

Covered exhaustively in [README](./README.md), [ARCHITECTURE](./ARCHITECTURE.md), [GOVERNANCE_DOCTRINE](./GOVERNANCE_DOCTRINE.md), and [USAGE](./USAGE.md).

### How it integrates

LLMBuilder is the **integration surface** for the other six repos. It implements lightweight-but-compatible versions of each sibling's core format:

- ARC-Core-style receipts for every governed action
- Cleanroom-style event-sourcing discipline for the conversation pipeline
- Cognition-Core-style benchmark schema + promotion gate (evolved to v2)
- Language-Module-style provenance + trust ranks for absorbed terms
- OmniBinary-style indexed binary ledger (OBIN v2)
- Arc-RAR-style manifest-indexed restorable archives

As the ecosystem matures (v1.3.0 roadmap), each of these lightweight local implementations will federate out to the full sibling service: receipts flow to ARC-Core, events to OmniBinary, bundles to Arc-RAR, terms to Language Module, and the whole loop runs inside a Cleanroom kernel.

---

## How the seven compose

```
┌───────────────────────────────────────────────────────────────┐
│                                                                │
│              ARC-Core  (authority + receipts)                  │
│                         ▲                                      │
│                         │  signs / attests                     │
│                         │                                      │
│   Cleanroom Runtime ◄───┼───► Cognition Core                   │
│   (deterministic        │     (model doctrine)                 │
│    kernel)              │                                      │
│                         │                                      │
│                         ▼                                      │
│            ARC-Neuron-LLMBuilder                               │
│            (governed build loop)                               │
│                         │                                      │
│            ┌────────────┼────────────┐                         │
│            ▼            ▼            ▼                         │
│   Language Module  OmniBinary     Arc-RAR                      │
│   (lexical truth)  (binary        (archive /                   │
│                    mirror)         rollback)                   │
│                                                                │
└───────────────────────────────────────────────────────────────┘
```

**Reading left-to-right, top-to-bottom**:

1. ARC-Core is the root authority. Every receipt derives from its discipline.
2. Cleanroom Runtime and Cognition Core are the two operational wings. Cleanroom owns "how things run" (deterministic execution); Cognition Core owns "how cognition is built" (doctrine).
3. LLMBuilder is the integration lab that assembles all of these into a working governed loop.
4. Below LLMBuilder, the three substrate repos own the persistent state: Language Module (what words mean), OmniBinary (what binaries are), Arc-RAR (what archives contain).

## Frozen roles — why it matters

Every repo has **one job**. Nothing else in the stack may claim that job.

- ARC-Core owns authoritative event truth. Every receipt in the system derives from its discipline. Nothing else is allowed to be the ultimate source of event truth.
- Cleanroom Runtime owns deterministic execution. Bounded continuity, directives, replay, rollback — all operate through its kernel. Nothing else is allowed to be "the deterministic kernel."
- Cognition Core owns the model-growth doctrine. Training, benchmarking, promotion of cognition candidates live here. Nothing else is allowed to redefine "what is a cognition candidate."
- Language Module owns canonical truth for language itself. Terms, aliases, corrections, provenance. Nothing else is allowed to be the word-meaning authority.
- OmniBinary owns the binary mirror of source truth. Runtime-ledger semantics, decode, dispatch, execution fabric. Nothing else is allowed to be the canonical binary substrate.
- Arc-RAR owns restorable archive lineage. Every promoted candidate ends up in a manifest-indexed bundle here. Nothing else is allowed to be the archive-and-restore authority.
- ARC-Neuron LLMBuilder owns the governed local build loop. The canonical pipeline, Gate v2, and reflection all live here. Nothing else is allowed to be "the build-and-gate machine."

Roles never swap. If a new capability is needed, it goes in the repo whose role it belongs to — not wherever is most convenient.

## Sponsoring the work

All seven repositories share a single author and a single funding target:

- **GitHub Sponsors**: https://github.com/sponsors/GareBear99
- **Direct contribution**: open issues and PRs in whichever repo addresses your use case

Sponsorship funds time for:
- Hardening governance across all seven repos
- Benchmark-breadth expansion in LLMBuilder
- Integration between adjacent roles (OmniBinary ↔ LLMBuilder, ARC-Core ↔ Cleanroom, Language Module ↔ LLMBuilder)
- External-model adapter validation at larger tiers
- Production documentation for enterprise adoption

## One-line summary

**One author, one doctrine, seven frozen roles. Each repo owns its single responsibility. Together they form a governed local AI operating system with full lineage, receipts, and rollback.**
