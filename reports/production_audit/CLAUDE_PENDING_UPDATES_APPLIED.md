# Claude pending updates applied

Applied the pending Claude audit/update notes to the uploaded ARC-Neuron-LLMBuilder package.

## Applied

- Restored `.env.direct-runtime.example`.
- Removed detectable placeholder stub rows from `datasets/distillation_sft/seed_records.jsonl`.
- Archived removed rows in `reports/production_audit/phase0_removed_stub_records.jsonl`.
- Added 150 targeted Phase 1 examples:
  - 50 instruction_following
  - 50 continuity
  - 50 reflection
- Added `docs/PHASE_0_1_TARGETED_DATA_RECOVERY.md`.
- Updated README and llms.txt to surface the update without claiming incumbent promotion.

## Counts

```json
{
  "removed_stub_records": 30,
  "phase1_added_records": {
    "instruction_following": 50,
    "continuity": 50,
    "reflection": 50
  }
}
```

## Boundary

These changes do not promote a new model. They prepare a future v2 candidate training run. The current reproducible incumbent remains `arc_governed_v10_wave4` until a future candidate is trained, benchmarked, and accepted through Gate v2.
