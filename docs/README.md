# Extended Documentation

This directory holds **62 internal design docs** that predate or supplement the canonical root-level documentation. For the production-path docs, start at the repo root:

- [README](../README.md)
- [QUICKSTART](../QUICKSTART.md)
- [ARCHITECTURE](../ARCHITECTURE.md)
- [GOVERNANCE_DOCTRINE](../GOVERNANCE_DOCTRINE.md)
- [USAGE](../USAGE.md)
- [EXAMPLES](../EXAMPLES.md)
- [FAQ](../FAQ.md)
- [GLOSSARY](../GLOSSARY.md)
- [PROOF](../PROOF.md)
- [STORAGE_ECONOMICS](../STORAGE_ECONOMICS.md)
- [ROADMAP](../ROADMAP.md)
- [COMPARISON](../COMPARISON.md)
- [ECOSYSTEM](../ECOSYSTEM.md)
- [RELEASE_NOTES_v1.0.0](../RELEASE_NOTES_v1.0.0.md)
- [MODEL_CARD_v6_conversation](../MODEL_CARD_v6_conversation.md)

This folder contains the **historical and topical design record** — acceptance gates, phase reports, model family progression, release checkpoints, and prep/promotion docs. They are preserved for provenance and technical depth, not as the primary entry point for new users.

---

## Index by topic

### ARC-Neuron model family — prep, promotion, training path

- [ARC_NEURON_MODEL_FAMILY.md](./ARC_NEURON_MODEL_FAMILY.md) — model family overview
- [ARC_NEURON_TINY_MODEL_CARD.md](./ARC_NEURON_TINY_MODEL_CARD.md) — Tiny tier card
- [ARC_NEURON_SMALL_AND_CORPUS_COMPILER.md](./ARC_NEURON_SMALL_AND_CORPUS_COMPILER.md) — Small tier + corpus compiler
- [ARC_NEURON_SMALL_V0_2_PREP.md](./ARC_NEURON_SMALL_V0_2_PREP.md) — Small v0.2 prep
- [ARC_NEURON_BASE_PREP.md](./ARC_NEURON_BASE_PREP.md) — Base tier prep
- [ARC_NEURON_BASE_PROMOTION.md](./ARC_NEURON_BASE_PROMOTION.md) — Base tier promotion
- [ARC_NEURON_INTEGRATED_STACK.md](./ARC_NEURON_INTEGRATED_STACK.md) — integrated stack build
- [ARC_TINY_GGUF_PATH.md](./ARC_TINY_GGUF_PATH.md) — Tiny GGUF path
- [NATIVE_GGUF_BOOTSTRAP_FROM_UPLOADED_STACK.md](./NATIVE_GGUF_BOOTSTRAP_FROM_UPLOADED_STACK.md) — native GGUF bootstrap
- [TRAINING_STACK_AND_GGUF_PATH.md](./TRAINING_STACK_AND_GGUF_PATH.md) — training stack + GGUF
- [CANDIDATE_SHAPING_PHASES.md](./CANDIDATE_SHAPING_PHASES.md) — candidate shaping phases
- [FIRST_REAL_CANDIDATE_RUN.md](./FIRST_REAL_CANDIDATE_RUN.md) — first real candidate run
- [MODEL_LADDER.md](./MODEL_LADDER.md) — tiered model ladder
- [MODEL_RUNTIME_BOUNDARY_SPEC.md](./MODEL_RUNTIME_BOUNDARY_SPEC.md) — model/runtime boundary spec

### Runtime, execution, and GGUF/llamafile

- [GGUF_BACKEND_WIRING.md](./GGUF_BACKEND_WIRING.md) — GGUF backend wiring
- [LLAMAFILE_BINARY_RUNTIME_2026-04-14.md](./LLAMAFILE_BINARY_RUNTIME_2026-04-14.md) — llamafile binary runtime
- [FLAGSHIP_GGUF_SWITCHOVER_2026-04-14.md](./FLAGSHIP_GGUF_SWITCHOVER_2026-04-14.md) — flagship GGUF switchover
- [FLAGSHIP_RUNTIME_VALIDATION_2026-04-14.md](./FLAGSHIP_RUNTIME_VALIDATION_2026-04-14.md) — flagship runtime validation
- [PHASE3_EXTERNAL_RUNTIME_WIRING_2026-04-14.md](./PHASE3_EXTERNAL_RUNTIME_WIRING_2026-04-14.md) — external runtime wiring
- [PHASE4_FUNCTIONING_MODEL_2026-04-14.md](./PHASE4_FUNCTIONING_MODEL_2026-04-14.md) — phase 4 functioning model
- [PHASE6_LLAMAFILE_RUNTIME_2026-04-14.md](./PHASE6_LLAMAFILE_RUNTIME_2026-04-14.md) — phase 6 llamafile runtime
- [LOCAL_BACKEND_SETUP.md](./LOCAL_BACKEND_SETUP.md) — local backend setup
- [USER_END_RUNTIME_FLOW_2026-04-14.md](./USER_END_RUNTIME_FLOW_2026-04-14.md) — user-end runtime flow
- [BROWSER_UI_BOUNDARY_2026-04-14.md](./BROWSER_UI_BOUNDARY_2026-04-14.md) — browser UI boundary
- [FINAL_EXTERNAL_BOUNDARY_2026-04-14.md](./FINAL_EXTERNAL_BOUNDARY_2026-04-14.md) — final external boundary
- [PRODUCTION_GGUF_BUILD_CONTRACT_2026-04-14.md](./PRODUCTION_GGUF_BUILD_CONTRACT_2026-04-14.md) — production GGUF build contract
- [REAL_GGUF_PRODUCTION_PATH_2026-04-14.md](./REAL_GGUF_PRODUCTION_PATH_2026-04-14.md) — real GGUF production path
- [RUNTIME_RECEIPTS_AND_TIMEOUTS_2026-04-14.md](./RUNTIME_RECEIPTS_AND_TIMEOUTS_2026-04-14.md) — runtime receipts + timeouts
- [EXECUTION_FIRST_UPGRADE.md](./EXECUTION_FIRST_UPGRADE.md) — execution-first upgrade

### Datasets, benchmarks, and corpus

- [DATASET_STRATEGY.md](./DATASET_STRATEGY.md) — dataset strategy
- [DATASET_EXPANSION_PLAN.md](./DATASET_EXPANSION_PLAN.md) — dataset expansion plan
- [EXPERIMENT_RUNBOOK.md](./EXPERIMENT_RUNBOOK.md) — experiment runbook

### Integration and ecosystem

- [ANCF_CANONICAL_ARTIFACT.md](./ANCF_CANONICAL_ARTIFACT.md) — ANCF canonical artifact spec
- [ECOSYSTEM_INTEGRATION_MATRIX_2026-04-14.md](./ECOSYSTEM_INTEGRATION_MATRIX_2026-04-14.md) — ecosystem integration matrix
- [ECOSYSTEM_PACKAGE_AUDIT_2026-04-14.md](./ECOSYSTEM_PACKAGE_AUDIT_2026-04-14.md) — ecosystem package audit
- [OMNIBINARY_BIDIRECTIONAL_TRUTH_LATCH.md](./OMNIBINARY_BIDIRECTIONAL_TRUTH_LATCH.md) — Omnibinary bidirectional truth latch
- [OMNIBINARY_INTEGRATION_NEXT_STEPS.md](./OMNIBINARY_INTEGRATION_NEXT_STEPS.md) — Omnibinary integration next steps
- [STACK_INTERFACE_CONTRACTS.md](./STACK_INTERFACE_CONTRACTS.md) — stack interface contracts
- [INTEGRATIONS.md](./INTEGRATIONS.md) — integrations overview
- [MCP_TOOLING.md](./MCP_TOOLING.md) — MCP tooling
- [VISUAL_ATTACHMENT_WORKFLOW.md](./VISUAL_ATTACHMENT_WORKFLOW.md) — visual attachment workflow

### Program control and governance

- [MASTER_OPERATOR_CONTROL.md](./MASTER_OPERATOR_CONTROL.md) — master operator control
- [DARPA_PROGRAM_CONTROL.md](./DARPA_PROGRAM_CONTROL.md) — program control
- [DARPA_MASTER_AUDIT_2026-04-14.md](./DARPA_MASTER_AUDIT_2026-04-14.md) — master audit
- [ACCEPTANCE_GATES.md](./ACCEPTANCE_GATES.md) — acceptance gates
- [UPSTREAM_EVENT_RELEASE_FLOW_2026-04-14.md](./UPSTREAM_EVENT_RELEASE_FLOW_2026-04-14.md) — upstream event release flow

### Status, readiness, and release

- [ALPHA_DEFINITION.md](./ALPHA_DEFINITION.md) — alpha definition
- [ALPHA_COMPLETE_STATUS.md](./ALPHA_COMPLETE_STATUS.md) — alpha complete status
- [PRODUCTION_READINESS_MATRIX.md](./PRODUCTION_READINESS_MATRIX.md) — production readiness matrix
- [PRODUCTION_HARDENING_STATUS.md](./PRODUCTION_HARDENING_STATUS.md) — production hardening status
- [FUNCTIONING_MODEL_STATUS_2026-04-14.md](./FUNCTIONING_MODEL_STATUS_2026-04-14.md) — functioning model status
- [MERGED_FINAL_STATUS.md](./MERGED_FINAL_STATUS.md) — merged final status
- [CURRENT_STATE_AND_NEXT_ACTIONS_2026-04-14.md](./CURRENT_STATE_AND_NEXT_ACTIONS_2026-04-14.md) — current state + next actions
- [HONEST_STATUS_AND_NEXT_GATES.md](./HONEST_STATUS_AND_NEXT_GATES.md) — honest status + next gates
- [PHASE3_STATUS_2026-04-14.md](./PHASE3_STATUS_2026-04-14.md) — phase 3 status
- [FINAL_USER_CHECKLIST_2026-04-14.md](./FINAL_USER_CHECKLIST_2026-04-14.md) — final user checklist
- [FINAL_PRODUCTION_HANDOFF_2026-04-14.md](./FINAL_PRODUCTION_HANDOFF_2026-04-14.md) — final production handoff
- [NEXT_ESSENTIALS_PURPOSE_MAP.md](./NEXT_ESSENTIALS_PURPOSE_MAP.md) — next essentials purpose map
- [ROADMAP_NEXT_STEPS.md](./ROADMAP_NEXT_STEPS.md) — roadmap next steps

### SEO and repo discovery

- [GITHUB_LAUNCH_CHECKLIST.md](./GITHUB_LAUNCH_CHECKLIST.md) — GitHub launch checklist
- [GITHUB_SEO_AUDIT.md](./GITHUB_SEO_AUDIT.md) — SEO audit
- [REPO_PURPOSE_MATRIX.md](./REPO_PURPOSE_MATRIX.md) — repo purpose matrix

---

## Relationship to canonical docs

Anything in this folder should be considered **historical context** or **deep-dive supplement**. If the root-level docs and a file in here disagree, the root-level docs win.

If you find information here that should be promoted into the canonical root-level docs, please file a [documentation issue](../.github/ISSUE_TEMPLATE/05_docs.yml).
