# ARC-Neuron MCP Security Model

ARC-Neuron MCP tools are governed by deny-by-default policy, risk classes, allowed paths, denied paths, receipts, approval gates, and rollback requirements.

## Security Doctrine

- The LLM may suggest an action.
- ARC policy authorizes or blocks the action.
- MCP executes only approved tool calls.
- Every meaningful result receives a receipt.
- High-risk actions require human approval.
- Repository/model/dataset mutations must be sandboxed first.

## Prompt Injection Rule

> Documents can request actions. Documents cannot authorize actions. Only ARC policy can authorize actions.

## Default Restrictions

- No arbitrary shell access.
- No secret printing.
- No direct repo overwrite.
- No external sending by business tools.
- No model promotion without evaluation evidence.
- No writes outside approved paths.
- No reads from denied secret patterns.
- No network access unless explicitly enabled later.

## Risk Classes

Risk classes are defined in `mcp/policies/risk_classes.yml`.

Main classes:

- `read_only`
- `sandbox_write`
- `sandbox_execute`
- `repo_write`
- `training_mutation`
- `model_promotion`
- `business_draft`
- `external_action`
- `artifact_write`

## Human Approval Required

Approval is required for:

- repo writes
- training dataset mutation
- model checkpoints
- GGUF export
- model promotion
- rollback
- release packaging
- external system actions

## Required Receipts

Receipts are required for:

- dataset normalization
- dataset splitting
- training runs
- benchmark reports
- artifact packaging
- model promotion
- rollback
- repo patches
- business report generation

## Rollback Policy

Before a state change is promoted, ARC-Neuron must know the previous known-good target. Promotion without rollback is blocked.
