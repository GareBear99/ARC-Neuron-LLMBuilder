# ARC-Neuron LLMBuilder MCP Tools Specification

This document defines the next-step MCP tool integration layer for ARC-Neuron LLMBuilder.

The goal is to add a governed Model Context Protocol tool layer without turning the LLM into an uncontrolled agent. MCP tools extend ARC-Neuron’s ability to ingest data, inspect repositories, run evaluations, produce receipts, manage artifacts, and support business workflows while preserving ARC doctrine: lineage, rollback, validation, evidence, and promotion gates.

---

## Core Architecture Rule

The LLM does not directly control tools.

Correct flow:

```text
User request
→ ARC intent parser
→ policy/risk classifier
→ MCP tool planner
→ permission gate
→ sandbox executor
→ receipt writer
→ verifier/evaluator
→ promotion gate
→ final response or artifact
```

Incorrect flow:

```text
User request
→ LLM
→ arbitrary tool call
→ filesystem/model/business mutation
```

ARC-Neuron must treat MCP as a controlled execution layer, not raw agent freedom.

---

## Design Doctrine

1. Deny by default.
2. Read before write.
3. Patch before overwrite.
4. Sandbox before promotion.
5. Receipt everything.
6. Human approval for high-risk actions.
7. Evidence before memory.
8. Benchmarks before promotion.
9. Rollback must exist.
10. Documents can request actions, but documents cannot authorize actions. Only ARC policy can authorize actions.

---

## Tool Lanes

ARC-Neuron divides MCP tools into seven lanes:

1. Dataset tools
2. Repository tools
3. Evaluation tools
4. Model tools
5. Memory/archive tools
6. Business workflow tools
7. Artifact/release tools

---

## Dataset Tools

| Tool | Purpose | Risk Class |
|---|---|---|
| `dataset.scan` | Discover dataset files | read_only |
| `dataset.validate_jsonl` | Validate JSONL structure | read_only |
| `dataset.normalize` | Normalize records into ARC format | sandbox_write |
| `dataset.deduplicate` | Remove duplicate records | sandbox_write |
| `dataset.quality_score` | Score basic dataset quality | read_only |
| `dataset.license_check` | Record source/license status | read_only |
| `dataset.pii_scan` | Detect sensitive personal data | read_only |
| `dataset.split_train_eval` | Create train/eval splits | training_mutation |

Dataset tools must preserve source paths, hashes, validation results, and training/eval lineage.

---

## Repository Tools

| Tool | Purpose | Risk Class |
|---|---|---|
| `repo.read_tree` | Read repository structure | read_only |
| `repo.search` | Search repo text | read_only |
| `repo.read_file` | Read approved files | read_only |
| `repo.create_patch` | Create patch in sandbox | sandbox_write |
| `repo.apply_patch_sandbox` | Apply patch to sandbox copy | sandbox_write |
| `repo.run_tests` | Run approved tests with timeout | sandbox_execute |
| `repo.generate_diff_receipt` | Write diff/evidence receipt | sandbox_write |
| `repo.commit_prepare` | Prepare commit summary | repo_write |

No direct overwrite. Every write becomes a patch. Every patch receives a receipt. Every patch must pass validation before promotion.

---

## Evaluation Tools

| Tool | Purpose | Risk Class |
|---|---|---|
| `eval.run_benchmark` | Run benchmark suite | read_only |
| `eval.compare_candidates` | Compare candidate vs incumbent | read_only |
| `eval.score_regression` | Detect regressions | read_only |
| `eval.score_grounding` | Score source grounding | read_only |
| `eval.generate_report` | Create evaluation report | sandbox_write |

No model/tool/workflow promotion should occur without evaluation evidence.

---

## Model Tools

| Tool | Purpose | Risk Class |
|---|---|---|
| `model.train_smoke` | Run tiny smoke training | training_mutation |
| `model.train_candidate` | Run candidate training | training_mutation |
| `model.export_gguf` | Export candidate artifact | training_mutation |
| `model.write_manifest` | Write model manifest | sandbox_write |
| `model.promote_candidate` | Promote candidate to incumbent | model_promotion |
| `model.rollback` | Restore previous incumbent | model_promotion |

The newest model is never automatically better. Promotion requires proof.

---

## Memory / Archive Tools

| Tool | Purpose | Risk Class |
|---|---|---|
| `memory.write_receipt` | Write ARC receipt | sandbox_write |
| `memory.search_receipts` | Search receipts | read_only |
| `memory.link_artifact` | Link artifact to receipts | sandbox_write |
| `memory.export_audit_bundle` | Export audit bundle | artifact_write |

Receipts are the evidence spine.

---

## Business Workflow Tools

| Tool | Purpose | Risk Class |
|---|---|---|
| `business.ingest_docs` | Import business docs to sandbox collection | sandbox_write |
| `business.extract_sop` | Extract SOP steps from sources | read_only |
| `business.generate_ticket_response` | Generate source-backed draft | business_draft |
| `business.create_report` | Create sourced business report | sandbox_write |

Business tools generate drafts only. They do not send externally.

---

## Artifact / Release Tools

| Tool | Purpose | Risk Class |
|---|---|---|
| `artifact.package_model` | Package model artifacts | artifact_write |
| `artifact.verify_hashes` | Verify package hashes | read_only |
| `artifact.release_notes` | Generate release notes | sandbox_write |

---

## Definition of Done

MCP integration is done only when:

1. Tool registry exists.
2. Policy gate blocks unsafe calls.
3. Receipts are created for all tool actions.
4. Dataset tools can prepare clean training material.
5. Eval tools can compare candidate vs incumbent.
6. Memory tools preserve evidence.
7. Repo tools operate patch-first in sandbox.
8. Model tools cannot promote without evidence.
9. Business tools generate source-backed drafts only.
10. Artifact tools package outputs with hashes.
11. Tests prove each tool respects permissions.
12. README documents governed MCP support.
