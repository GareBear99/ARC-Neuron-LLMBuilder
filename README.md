# ARC-Neuron LLMBuilder

**ARC-Neuron LLMBuilder is a governed local AI model-building and memory-preservation lab for training, benchmarking, promoting, and archiving small language-model candidates with receipts, rollback, provenance, and regression-safe gates.**

It is designed for builders who care about **offline AI**, **local LLM training**, **GGUF-oriented model development**, **dataset lineage**, **model promotion gates**, **AI memory continuity**, **reproducible evaluation**, and **knowledge preservation**.

> **Core doctrine:** ARC-Neuron should never merely become smarter. It should know how it became smarter, preserve the path, and keep rollback evidence.

---

## What this is

ARC-Neuron LLMBuilder is the model-growth and evaluation layer of the ARC ecosystem. It focuses on one hard problem:

**How do you grow a local AI system without destroying the truth, evidence, lineage, and benchmark context that produced each improvement?**

This repository provides a governed workflow for:

- building ARC-Neuron model candidates
- tracking candidate lineage and evidence
- running local benchmark suites
- scoring model outputs against protected floors
- promoting only candidates that pass regression gates
- preserving receipts, manifests, scoreboards, and rollback paths
- preparing future GGUF / ANCF-style model artifacts
- separating experimental v2/v3 candidates from the current reproducible incumbent

It is not just a chatbot repo. It is a **local-first AI cognition workshop** for controlled model growth.

---

## Why it matters

Most AI experiments overwrite their own history. ARC-Neuron is built the opposite way.

Instead of chasing one-off benchmark wins, the system is designed around:

- **provenance-first training** — every dataset, candidate, score, and promotion needs a traceable path
- **regression-safe promotion** — new weights must not silently weaken protected capabilities
- **candidate isolation** — experimental v2/v3 weights do not pollute incumbent measurements
- **memory continuity** — repeated questions and doctrine checks should stabilize instead of drift
- **local-first execution** — development is designed to work without cloud dependency
- **rollback-aware releases** — model history stays recoverable, reviewable, and auditable

This is the roadmap foundation for the protected **ARC-Neuron 3.0 full base-model integration release**.

---

## Current production status

The current package is honest about what is proven and what is still candidate-stage.

| Area | Status |
|---|---|
| Current reproducible incumbent | `arc_governed_v10_wave4` |
| Incumbent score | `0.9237` |
| v11.3 / wave5 | candidate / staging only |
| Tests | 136-test suite tracked in repo evidence |
| Benchmark inventory | 17 benchmark files / 168 tasks in production package reports |
| Dataset inventory | 6 dataset files / 120 records in production package reports |
| Promotion model | Gate v2 / protected-floor comparison |
| 3.0 roadmap | documented, candidate-isolated, license-aware |

**Important:** v11.3 / wave5 materials are intentionally treated as staging until promotion evidence is regenerated from shipped files, Gate v2 passes without protected-floor regression, and the scoreboard/archive bundle are updated.

---

## Core capabilities

### Governed model candidate building

ARC-Neuron supports a candidate-based model workflow where new training waves are built, benchmarked, scored, and either promoted or rejected.

Key ideas:

- candidate models are not automatically trusted
- benchmark scores are attached to evidence files
- old floors must be protected
- candidate promotions require receipts
- release claims must match reproducible artifacts

### Regression-safe promotion gates

The promotion system is designed to prevent this failure mode:

```text
new data improves one capability
but silently damages planning, continuity, refusal, or ARC doctrine retention
```

Instead, candidates are compared against protected floors before promotion.

Relevant files:

- [`specs/promotion_gate_v2.yaml`](./specs/promotion_gate_v2.yaml)
- [`results/scoreboard.json`](./results/scoreboard.json)
- [`docs/BENCHMARK_PROOF.md`](./docs/BENCHMARK_PROOF.md)

### v2 candidate isolation

New weights and new dataset classes belong in a separate candidate lane before they can affect the incumbent.

This protects the current scoring baseline from being polluted by experimental data.

Relevant files:

- [`docs/V2_CANDIDATE_ISOLATION_POLICY.md`](./docs/V2_CANDIDATE_ISOLATION_POLICY.md)
- [`configs/candidates/v2_class_policy.yaml`](./configs/candidates/v2_class_policy.yaml)

### Knowledge preservation doctrine

ARC-Neuron treats model growth as an evidence chain, not a black box.

The doctrine is simple:

```text
No training event may destroy, overwrite, hide, or falsely simplify the provenance chain that produced a model behavior.
```

Relevant file:

- [`docs/KNOWLEDGE_PRESERVATION_DOCTRINE.md`](./docs/KNOWLEDGE_PRESERVATION_DOCTRINE.md)

### Memory and continuity evaluation

The roadmap includes regression tests for repeated questions, doctrine memory, continuity, and answer stability.

Relevant files:

- [`docs/MODEL_MEMORY_EVALUATION_PROTOCOL.md`](./docs/MODEL_MEMORY_EVALUATION_PROTOCOL.md)
- [`configs/evaluation/memory_regression_suite.yaml`](./configs/evaluation/memory_regression_suite.yaml)
- [`benchmarks/v2_memory_continuity_tasks.jsonl`](./benchmarks/v2_memory_continuity_tasks.jsonl)

### Dataset roadmap for 3.0

The 3.0 dataset plan is governed, staged, and license-aware. External datasets are not blindly bundled. They must pass manifest, license, risk, and candidate-lane checks.

Roadmap dataset classes include:

- ARC-native doctrine, receipts, scoreboards, and operator corrections
- instruction-following datasets
- reasoning, planning, and critique/revision datasets
- lexical simplicity and support-language datasets
- code, tool-use, and repo-repair datasets
- refusal, licensing, safety, and provenance datasets
- memory-continuity regression data

Relevant files:

- [`docs/DATASET_ACQUISITION_MATRIX_3_0.md`](./docs/DATASET_ACQUISITION_MATRIX_3_0.md)
- [`configs/datasets/dataset_manifest_template.yaml`](./configs/datasets/dataset_manifest_template.yaml)
- [`docs/DARPA_NEXT_STEPS_TO_GEMMA_CLAUDE_STATE.md`](./docs/DARPA_NEXT_STEPS_TO_GEMMA_CLAUDE_STATE.md)

---

## ARC-Neuron 3.0 roadmap

ARC-Neuron 3.0 is the planned full roadmap integration release.

The 3.0 direction is:

```text
language truth grows
→ governed traces are captured
→ ARC Core validates and receipts
→ Omnibinary stores learning deltas
→ Arc-RAR snapshots and archives waves
→ Cognition Core compiles corpora and runs eval gates
→ ARC-Neuron retrains/promotes candidates
→ ANCF/GGUF-style artifacts are exported for local runtime
```

The goal is not merely to wrap an external model. The goal is to build a governed local model-growth system that preserves its own history.

Relevant files:

- [`docs/ARC_NEURON_3_0_ROADMAP_INTEGRATION.md`](./docs/ARC_NEURON_3_0_ROADMAP_INTEGRATION.md)
- [`docs/DARPA_NEXT_STEPS_TO_GEMMA_CLAUDE_STATE.md`](./docs/DARPA_NEXT_STEPS_TO_GEMMA_CLAUDE_STATE.md)
- [`docs/TRANSITIONAL_LICENSE_ROADMAP.md`](./docs/TRANSITIONAL_LICENSE_ROADMAP.md)
- [`LICENSE_TRANSITIONAL_NOTICE.md`](./LICENSE_TRANSITIONAL_NOTICE.md)

---

## Ecosystem links

ARC-Neuron LLMBuilder is part of the broader ARC / Lucipher local-first AI ecosystem.

| Project | Role |
|---|---|
| [`ARC-Core`](https://github.com/GareBear99/ARC-Core) | authority, receipts, state, validation, and promotion control |
| [`ARC-Neuron-LLMBuilder`](https://github.com/GareBear99/ARC-Neuron-LLMBuilder) | local model candidate building, scoring, promotion, and memory evaluation |
| [`arc-lucifer-cleanroom-runtime`](https://github.com/GareBear99/arc-lucifer-cleanroom-runtime) | governed local runtime, replay, rollback, and supervised execution |
| [`arc-language-module`](https://github.com/GareBear99/arc-language-module) | canonical lexical truth spine and language growth layer |
| [`Arc-RAR`](https://github.com/GareBear99/Arc-RAR) | archival bundles, rollback packages, and reproducible restore paths |
| [`ARC-Turbo-OS`](https://github.com/GareBear99/ARC-Turbo-OS) | acceleration layer and operating-system direction for ARC workflows |

Together, these projects form a local-first AI architecture focused on **truth preservation**, **model governance**, **offline execution**, **replayable memory**, and **auditable intelligence growth**.

---

## Quick start

### 1. Clone

```bash
git clone https://github.com/GareBear99/ARC-Neuron-LLMBuilder.git
cd ARC-Neuron-LLMBuilder
```

### 2. Create environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Validate the repo

```bash
python scripts/validate_repo.py
```

### 4. Run production verification

```bash
python scripts/production_verify.py
```

Or:

```bash
make production-verify
```

### 5. Run SEO validation

```bash
python scripts/seo_validate.py
```

Or:

```bash
make seo-validate
```

---

## Public SEO description

**ARC-Neuron LLMBuilder is a governed local AI model-building lab for offline LLM training, GGUF-oriented model candidates, benchmark scoring, memory continuity, dataset provenance, rollback-safe promotion, and ARC ecosystem cognition research.**

Recommended GitHub description:

```text
Governed local AI cognition lab for building, benchmarking, and promoting GGUF-oriented model candidates with receipts, rollback, provenance, and regression-safe gates.
```

Recommended GitHub topics:

```text
local-ai, offline-ai, llm, gguf, ai-governance, model-evaluation, benchmark, provenance, ai-memory, rollback, dataset-lineage, model-training, python, arc-neuron, arc-core, omnibinary, arc-rar, reproducible-ai, local-llm, ai-safety
```

SEO keyword targets:

- local AI model builder
- offline LLM training
- GGUF model builder
- governed AI training
- AI memory system
- model promotion gate
- regression-safe model evaluation
- dataset provenance for AI
- rollback-safe AI
- ARC-Neuron
- ARC Core
- Omnibinary
- Arc-RAR
- local-first AI cognition
- open-source AI governance framework

---

## Repository map

```text
benchmarks/              benchmark tasks and evaluation suites
configs/                 candidate, dataset, evaluation, and licensing config
data/                    curated dataset records and critique inputs
docs/                    production docs, roadmap, SEO, memory, doctrine, proof
exports/                 candidate outputs and generated model artifacts
manifests/               file manifests and release evidence
reports/                 production audit and promotion reports
results/                 scoreboards, benchmark results, validation outputs
scripts/                 build, benchmark, scoring, validation, SEO, production tools
specs/                   promotion gates and governance specifications
tests/                   regression and unit tests
```

---

## Production evidence and reports

Important proof files:

- [`docs/PRODUCTION_RELEASE_HANDOFF.md`](./docs/PRODUCTION_RELEASE_HANDOFF.md)
- [`reports/production_audit/FINAL_COMPLETION_LOCK_2026-05-09.md`](./reports/production_audit/FINAL_COMPLETION_LOCK_2026-05-09.md)
- [`reports/production_audit/SEO_AND_MEMORY_COMPLETION_LOCK_2026-05-10.md`](./reports/production_audit/SEO_AND_MEMORY_COMPLETION_LOCK_2026-05-10.md)
- [`reports/production_audit/seo_validate_final_2026-05-10.json`](./reports/production_audit/seo_validate_final_2026-05-10.json)
- [`reports/production_audit/final_validate_repo_2026-05-10.json`](./reports/production_audit/final_validate_repo_2026-05-10.json)

---

## Licensing roadmap

The current licensing direction is staged:

- **1.0** keeps the license it shipped with.
- **There is no formal public 2.0 release.**
- **1.0–2.0-era work** is a development bridge.
- **3.0** is the planned protected full roadmap/base-model release.
- **3.0+** should use a more suitable license that prevents unrestricted resale, repackaging, or commercial misuse of the full product and model artifacts.

Relevant files:

- [`LICENSE`](./LICENSE)
- [`LICENSE_TRANSITIONAL_NOTICE.md`](./LICENSE_TRANSITIONAL_NOTICE.md)
- [`docs/TRANSITIONAL_LICENSE_ROADMAP.md`](./docs/TRANSITIONAL_LICENSE_ROADMAP.md)
- [`configs/licensing/three_point_zero_release_license_checklist.yaml`](./configs/licensing/three_point_zero_release_license_checklist.yaml)

---

## Project identity

Built by **Gary Doman / GareBear99** as part of the ARC, Lucipher, Omnibinary, Arc-RAR, Cleanroom Runtime, and local-first AI ecosystem.

GitHub:

- [`GareBear99`](https://github.com/GareBear99)
- [`ARC-Neuron-LLMBuilder`](https://github.com/GareBear99/ARC-Neuron-LLMBuilder)

---

## Star / sponsor / follow

If this project helps your research into local AI, model governance, offline LLM building, GGUF candidate workflows, reproducible AI, or evidence-preserving model growth:

- star the repo
- open an issue with benchmark or dataset suggestions
- follow the ARC ecosystem projects
- support development through GitHub Sponsors when available

[![Sponsor](https://img.shields.io/badge/Sponsor-GareBear99-ea4aaa?logo=githubsponsors&logoColor=white)](https://github.com/sponsors/GareBear99)

---

## Final note

ARC-Neuron LLMBuilder is not trying to fake a finished frontier model.

It is building the infrastructure required to grow one safely:

```text
candidate → benchmark → score → compare → gate → receipt → archive → promote or reject
```

The mission is simple:

**Build intelligence without destroying the evidence of how that intelligence came to be.**
