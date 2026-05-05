# Roadmap

Concrete milestones for future releases of ARC-Neuron LLMBuilder. Items are ordered by impact and by how much they preserve the governance doctrine.

## Current release: v1.0.0-governed (2026-04-22)

**Status**: Shipped.

- Three governed promotions on record (v4, v5, v6_conversation) at v1.0.0
- **Four post-audit governed promotions on record (v7, v8, v9, v10) at v2.0.0** — overall score 0.6836→0.9237
- All four Gate v2 decision states fired lawfully
- Conversation-harvested corpus proven to grow the brain
- Omnibinary ledger measured: 6,600 ev/s append, 8,900 lookups/sec O(1)
- Arc-RAR bundles restorable end-to-end
- 115/116 tests passing (v2.0.0), 9/9 demo proof workflow green

---

## v1.1.0 — Expanded Native Lane

**Target**: widen the native ARC-Neuron lane without relying on external backends.

### Planned
- **ARC-Neuron Base tier** — 4 layers, 256 block, 128 embd (~1M params). GPU-accelerated training script with CUDA + MPS detection.
- **Real tokenizer beyond byte-level** — SentencePiece or BPE built from the accumulated corpus via `arc_neuron_tokenizer/builder.py`. Native models pick it up via `TransformerConfig.vocab_size`.
- **Distillation wave v2** — programmatic conversation-harvest driver that runs `run_proof_workflow.py` N times with varied prompts and auto-builds training packs.
- **Benchmark breadth expansion** — new lanes for safety_refusal, numerical_reasoning, structured_json, tool_calling (+50 tasks).
- **Scorer v3** — per-capability weighting in `overall_weighted_score` rather than equal weights.
- **CLI frontend** — `arc` command dispatching to all operator scripts (`arc train`, `arc promote`, `arc gate`, `arc explain`).

### Acceptance
- v7_native promoted through Gate v2 with cleanly higher overall score than v6_conversation using only the new tokenizer and ARC-Neuron Base tier.
- Distillation wave v2 produces 100+ SFT pairs in one run.
- CLI is documented in USAGE.md as the canonical surface.

---

## v1.2.0 — External Backend Integration

**Target**: prove the governance machinery holds against a frontier-grade external model.

### Planned
- **Reference integration docs** for Qwen3-32B-Instruct, Llama-4, DeepSeek-Coder via `llama_cpp_http`.
- **External-model benchmark preset** — 142-task suite pre-run against a canonical open-weights model as a reference ceiling.
- **Per-adapter scoreboard namespacing** — prevent external-model scores from displacing native-model incumbents accidentally (keep separate tracks under one scoreboard).
- **Command adapter timeout tuning** — expose first-output / idle / overall timeouts as `--timeout-*` flags to `promote_candidate.py`.
- **Reflection loop v2** — skip the critique stage when confidence is already bounded; detect overclaim patterns more precisely.

### Acceptance
- Gate v2 promotes a fine-tuned Qwen3-7B candidate through the identical pipeline.
- Reference benchmark numbers for Qwen3-32B published in `reports/external_reference/`.

---

## v1.3.0 — Multi-Repo Integration

**Target**: tighten the cross-repo contracts across the seven ARC repos.

### Planned
- **OmniBinary ↔ LLMBuilder federation** — a daemon in the OmniBinary repo that subscribes to this repo's Omnibinary ledger and mirrors into the canonical binary-runtime event graph.
- **ARC-Core event attestation** — every promotion receipt co-signed with an ARC-Core signing key from the bootstrap flow.
- **Arc-RAR → Cleanroom replay** — a one-command restore from any Arc-RAR bundle into a Cleanroom-runtime-governed execution slot.
- **Language Module canonicalization** — sync the LLMBuilder terminology store with the Language Module's governed truth surface, replacing the current local-only JSON store.

### Acceptance
- Cross-repo integration test: one conversation turn produces a receipt that is co-signed by ARC-Core, mirrored into OmniBinary, preserved in Arc-RAR, and restorable into Cleanroom.

---

## v2.0.0 — Production Governance

**Target**: institutional-grade readiness for enterprise adoption.

### Planned
- **Formal governance spec** — a versioned specification document (beyond the current Markdown doctrine) with machine-checkable invariants.
- **Sandboxed execution** — Gate v2 runs inside an isolated environment with enforced resource limits.
- **Audit trail export** — one-command export of every receipt, bundle, and decision for a date range into a tamper-evident format.
- **Per-organization scoreboards** — multi-tenant scoreboards with role-based access to promotion decisions.
- **Compliance tooling** — optional integration hooks for SOC 2 / ISO 27001 auditing workflows.

### Acceptance
- External audit validates the ten governance invariants.
- One external organization runs the governed loop in production under their own compliance framework.

---

## Ongoing

These are not tied to a specific release:

- **Documentation quality** — FAQ, GLOSSARY, EXAMPLES, MODEL_CARDs kept current as the system evolves.
- **Benchmark quality** — task diversity increases, rubric sophistication grows, paraphrase-pressure coverage expands.
- **Performance** — Omnibinary throughput, Arc-RAR pack time, benchmark runtime.
- **Cross-repo hygiene** — each of the seven ARC repos stays role-pure.

## How to influence the roadmap

- File a ✨ Feature request issue targeting the right version.
- Open a pull request that preserves all ten governance invariants.
- Sponsor the work: [github.com/sponsors/GareBear99](https://github.com/sponsors/GareBear99).
- Discuss architectural direction in [GitHub Discussions](https://github.com/GareBear99/ARC-Neuron-LLMBuilder/discussions).

## What won't be on the roadmap

- **Alignment or safety filtering.** The gate is a capability + regression gate. Safety is an orthogonal concern best handled by the operator's policy layer.
- **Hosted cloud service.** This is a local-first project. Hosted offerings are out of scope.
- **Closed-source components.** MIT all the way down.
- **Role inversion.** The seven-repo contract is permanent. New capabilities go into their correct home repo, not into whichever one is most convenient.
