# ARC-Neuron MCP Model Promotion

Model promotion is evidence-gated. A candidate must prove it is better than the incumbent before it can become active.

## Promotion Flow

```text
train candidate
→ export artifacts
→ write manifest
→ run benchmark
→ compare incumbent
→ detect regressions
→ generate report
→ approve/reject/hold
→ preserve rollback target
```

## Promotion Conditions

A candidate should be blocked if:

- benchmark score is worse than incumbent
- regressions exceed threshold
- artifact hashes are missing
- dataset lineage is missing
- promotion report is missing
- rollback target is missing
- human approval is missing

## Promotion Decision Types

- `promote`
- `reject`
- `hold_for_review`

## Rollback Rule

Every promoted model must preserve a rollback target.
