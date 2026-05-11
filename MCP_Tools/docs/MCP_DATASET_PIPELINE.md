# ARC-Neuron MCP Dataset Pipeline

The MCP dataset pipeline turns incoming material into validated, normalized, deduplicated, source-tracked training and evaluation candidates.

## Pipeline

```text
dataset.scan
→ dataset.validate_jsonl
→ dataset.normalize
→ dataset.deduplicate
→ dataset.quality_score
→ dataset.license_check
→ dataset.pii_scan
→ dataset.split_train_eval
→ memory.write_receipt
```

## Dataset Entry Requirements

A dataset should not enter training without:

- source path
- source/license note
- hash
- timestamp
- validation result
- normalization receipt
- PII/license status
- train/eval split proof

## Output Targets

- normalized sandbox JSONL
- deduped sandbox JSONL
- quality report
- training split
- evaluation split
- receipt chain
