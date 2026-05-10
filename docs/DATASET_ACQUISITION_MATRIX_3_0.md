# Dataset Acquisition Matrix for ARC-Neuron 3.0

External datasets are acquisition targets only. They are not bundled, not ingested, and not promoted into incumbent weights until manifest, license, hash, quarantine, benchmark, and no-regression gates pass.

| Dataset/source | Role | Entry lane | Status |
|---|---|---|---|
| FLAN Collection / FLAN-style instruction data | instruction following | v2 candidate | acquisition target only |
| OpenAssistant OASST1 | assistant dialogue | v2 candidate | acquisition target only |
| UltraChat / UltraChat 200k | multi-turn dialogue | v2 candidate | acquisition target only |
| MentalChat16K and counseling/support-language data | lexical simplicity, empathy, de-escalation; not therapy authority | v2 candidate, safety reviewed | acquisition target only |
| WikiLarge / text simplification | plain-language rewriting | v2 candidate | acquisition target only |
| GSM8K | reasoning benchmark/reference | v2 candidate/eval | acquisition target only |
| MBPP | code task solving | v2 candidate/eval | acquisition target only |
| HumanEval | code evaluation | eval only by default | acquisition target only |
| BigCode The Stack / Stack v2-style data | code reference data subject to license review | quarantine first | acquisition target only |
| ARC-native operator corrections | self-curated truth corrections | curated local lane | highest trust |
| Memory / continuity tasks | doctrine and state consistency | benchmark lane | local benchmark |

## Rule

No dataset enters the incumbent directly. Every new data source must preserve provenance and must be able to be removed, replayed, or rolled back.

## Landed Phase 1 internal targeted data

The repo now includes internal v2-candidate-only Phase 1 records generated from audit findings:

- `datasets/distillation_sft/phase1_instruction_following.jsonl` — 50 records
- `datasets/distillation_sft/phase1_continuity.jsonl` — 50 records
- `datasets/distillation_sft/phase1_reflection.jsonl` — 50 records

These are self-curated ARC records, not external datasets. They are staged for future candidate training only and do not change the current incumbent until a trained candidate passes benchmark and Gate v2.

