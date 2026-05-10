---
title: "ARC-Neuron LLMBuilder"
description: "Governed local AI cognition lab for building, benchmarking, and promoting GGUF-oriented model candidates with receipts, rollback, provenance, and regression-safe gates."
---

# ARC-Neuron LLMBuilder

> A governed local AI build-and-memory system that can train small brains, compare them, protect the better one, archive the worse one, and preserve the evidence of why.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Tests: 136 collected](https://img.shields.io/badge/tests-136%20collected-blue.svg)](./tests)
[![Gate: v2](https://img.shields.io/badge/governance-Gate%20v2-blue.svg)](./specs/promotion_gate_v2.yaml)
[![Release: v1.0.0-governed](https://img.shields.io/badge/release-v1.0.0--governed-blueviolet.svg)](./RELEASE_NOTES_v1.0.0.html)
[![Sponsor](https://img.shields.io/badge/Sponsor-GareBear99-ea4aaa?logo=githubsponsors&logoColor=white)](https://github.com/sponsors/GareBear99)

## Start here

- [README](./README.html) — what this is and why it exists
- [Quickstart](./QUICKSTART.html) — 10-minute tour
- [Examples](./EXAMPLES.html) — runnable recipes
- [FAQ](./FAQ.html) — 20+ searchable questions

## Architecture and doctrine

- [Architecture](./ARCHITECTURE.html) — the four frozen roles
- [Governance Doctrine](./GOVERNANCE_DOCTRINE.html) — how Gate v2 decides
- [Glossary](./GLOSSARY.html) — every ARC-specific term
- [Comparison](./COMPARISON.html) — vs MLflow, W&B, Langfuse, llama.cpp

## Reference

- [Usage](./USAGE.html) — complete command reference
- [Roadmap](./ROADMAP.html) — v1.1 → v2 milestones
- [Changelog](./CHANGELOG.html) — release history
- [v1.0.0-governed Release Notes](./RELEASE_NOTES_v1.0.0.html) — evidence dossier
- [Model Card — `arc_governed_v10_wave4`](./MODEL_CARD_v10_wave4.md) — **current incumbent** (v2.0.0-audited)
- [Model Card — `arc_governed_v6_conversation`](./MODEL_CARD_v6_conversation.html) — v1.0.0 incumbent (superseded)

## Ecosystem

- [ECOSYSTEM](./ECOSYSTEM.html) — the seven-repo ARC family

| Repo | Role |
|---|---|
| [ARC-Core](https://github.com/GareBear99/ARC-Core) | Event / receipt / authority spine |
| [arc-lucifer-cleanroom-runtime](https://github.com/GareBear99/arc-lucifer-cleanroom-runtime) | Deterministic local operator kernel |
| [arc-cognition-core](https://github.com/GareBear99/arc-cognition-core) | Model-growth lab |
| [arc-language-module](https://github.com/GareBear99/arc-language-module) | Canonical lexical truth |
| [omnibinary-runtime](https://github.com/GareBear99/omnibinary-runtime) | Binary mirror / runtime ledger |
| [Arc-RAR](https://github.com/GareBear99/Arc-RAR) | Archive / rollback bundles |
| **ARC-Neuron-LLMBuilder** *(you are here)* | Governed build loop |


## Public indexing

- [SEO Indexing Playbook](./docs/SEO_INDEXING_PLAYBOOK.html) — GitHub topics, release wording, GitHub Pages, and external indexing checklist
- [3.0 Roadmap Integration](./docs/ARC_NEURON_3_0_ROADMAP_INTEGRATION.html) — protected roadmap baseline
- [Memory Evaluation Protocol](./docs/MODEL_MEMORY_EVALUATION_PROTOCOL.html) — repeated-question continuity and doctrine-retention tests
- [Transitional License Roadmap](./docs/TRANSITIONAL_LICENSE_ROADMAP.html) — 1.0-to-3.0 licensing path

<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "SoftwareSourceCode",
  "name": "ARC-Neuron LLMBuilder",
  "description": "Governed local AI cognition lab for building, benchmarking, and promoting GGUF-oriented model candidates with receipts, rollback, provenance, and regression-safe gates.",
  "codeRepository": "https://github.com/GareBear99/ARC-Neuron-LLMBuilder",
  "programmingLanguage": ["Python"],
  "keywords": "local AI model builder, governed LLM builder, GGUF, AI provenance, model promotion gate, offline LLM builder, sovereign AI"
}
</script>

## Community

- [GitHub Discussions](https://github.com/GareBear99/ARC-Neuron-LLMBuilder/discussions) — ask questions, share runs
- [Issues](https://github.com/GareBear99/ARC-Neuron-LLMBuilder/issues) — bug reports, feature requests, gate behavior reports
- [Contributing](./CONTRIBUTING.html) — how to contribute
- [Security](./SECURITY.html) — responsible disclosure
- [Sponsor](https://github.com/sponsors/GareBear99) — support the work

## At a glance

| What | Value |
|---|---|
| Tests | 136 collected; CI runs fast subset plus core-fix subset |
| Incumbent | `arc_governed_v10_wave4` @ 0.9237 |
| Promotions on record | 9 (v1, v2, v4, v5, v6, v7, v8, v9, v10) — 4 post-audit |
| Benchmark suite | 165 tasks / 16 capability families |
| Omnibinary append | ~6,600 events/sec |
| Omnibinary O(1) lookup | ~8,900 lookups/sec |
| Archive bundles | 12 restorable |
| License | MIT |

---

**Source code:** [github.com/GareBear99/ARC-Neuron-LLMBuilder](https://github.com/GareBear99/ARC-Neuron-LLMBuilder)
**Author:** Gary Doman
**Ecosystem:** [ARC family — seven repos](./ECOSYSTEM.html)
