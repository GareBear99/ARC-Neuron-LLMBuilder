# ARC-Neuron MCP Business Workflows

Business workflows are draft-first, source-grounded, and approval-safe.

## Supported Workflow Targets

- internal SOP assistant
- customer support draft helper
- documentation assistant
- compliance note summarizer
- engineering triage helper
- research/report generator
- private business knowledge base builder

## Workflow Requirements

Every business workflow should include:

- source collection
- source trace
- confidence estimate
- draft output
- receipt path
- human review flag

## Forbidden Behavior

- no external sending
- no unsupported policy claims
- no secret exposure
- no business mutation without explicit approval

## Example Flow

```text
ingest business docs
→ extract SOP
→ generate draft
→ score grounding
→ write receipt
→ require human review
```
