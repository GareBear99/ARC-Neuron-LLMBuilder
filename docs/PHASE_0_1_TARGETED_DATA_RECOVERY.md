# Phase 0/1 targeted data recovery

This document applies the pending audit/update notes that were not previously landed cleanly.

## Source of update

The pending note identified four concrete problems:

1. The README undersold the real incumbent by still referencing older v6-era status.
2. The repo had packaging drift around `.env.direct-runtime.example`.
3. Stub-like distillation records were present and should not be treated as useful training signal.
4. Phase 1 should build targeted examples for weak capabilities instead of adding generic data.

## Phase 0 cleanup applied

- Added `.env.direct-runtime.example` from `env.direct-runtime.example` so validators that expect the dotted file can pass.
- Scanned dataset JSONL files for the known stub signature:
  - `Seed distillation task ...`
  - `Bounded structured response ...`
- Removed the matching stub rows from `datasets/distillation_sft/seed_records.jsonl`.
- Archived removed rows in `reports/production_audit/phase0_removed_stub_records.jsonl`.

Note: the pending note referenced 385 stubs from an earlier analysis. In this uploaded package, the directly detectable stub signature appears in fewer rows. This patch removes the stubs actually present in the uploaded package rather than inventing a larger deletion count.

## Phase 1 targeted data added

Added 150 v2-candidate-only examples:

| File | Capability | Records | Purpose |
|---|---:|---:|---|
| `datasets/distillation_sft/phase1_instruction_following.jsonl` | instruction_following | 50 | exact formatting, constraints, patch discipline |
| `datasets/distillation_sft/phase1_continuity.jsonl` | continuity | 50 | preserve incumbent/candidate/dataset doctrine across turns |
| `datasets/distillation_sft/phase1_reflection.jsonl` | reflection | 50 | critique overclaims, correct attribution, revise precisely |

These files are **not** incumbent data. They are staged for a future v2 candidate training run.

## Required next step

A future candidate should be trained with these files, benchmarked, scored, and passed through Gate v2. Until then, these records are corpus improvements only; they are not model improvements.
