# ARC-Neuron LLMBuilder MCP Drop-In Package

This package is meant to be dragged into the root of `ARC-Neuron-LLMBuilder`.

It adds:

- MCP docs
- MCP manifest
- governed policy files
- receipt and promotion schemas
- starter client scaffolds
- starter server scaffolds
- tests for policy, receipts, dataset tools, eval tools, and business draft safety

## Install / Drop-In

Copy these folders into the repo root:

```text
docs/
mcp/
tests/
```

Then run:

```bash
python -m pytest tests/test_mcp_policy_gate.py tests/test_mcp_receipts.py tests/test_mcp_dataset_tools.py tests/test_mcp_eval_tools.py tests/test_mcp_business_tools.py
```

## Commit

```bash
git add docs/MCP_*.md mcp tests/test_mcp_*.py README_MCP_DROPIN.md
git commit -m "Add governed MCP integration scaffold"
git push origin main
```

## README Section

Add this to your main README:

```md
## Governed MCP Tool Layer

ARC-Neuron LLMBuilder is being extended with a governed MCP tool layer for dataset ingestion, repository inspection, evaluation, model artifact handling, memory receipts, business workflow drafts, and release packaging.

The goal is not uncontrolled agent behavior.

The goal is reliable AI operations with:

- deny-by-default tool permissions
- sandbox-first execution
- patch-before-overwrite repo changes
- receipts for every important action
- benchmark-gated model promotion
- rollback-safe model evolution
- source-grounded business outputs
- human approval for risky actions

The intended control flow is:

```text
LLM suggests
→ ARC validates
→ MCP executes
→ ARC receipts
→ evaluator scores
→ promotion gate decides
```

This turns MCP into a controlled capability layer rather than a black-box automation surface.
```
