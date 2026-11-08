# Dataset Acquisition Matrix for ARC-Neuron 3.0

External datasets are acquisition targets only. They are not bundled, not ingested into incumbent weights, and — by hard rule — **never enter the actual training data**. External datasets are evaluation/benchmark references only. The actual training uses **only our own data** (the "us" corpus — general knowledge about our stuff and system). Testing is offloaded to the continuous live running system, not mixed into training.

Every source must pass manifest, license, hash, quarantine, benchmark, and no-regression gates before it can influence promoted weights. Even then, an external dataset can only ever be a **benchmark/evaluation** input — never a training input.

| Dataset/source | Role | Entry lane | Status |
|---|---|---|---|
| FLAN Collection / FLAN-style instruction data | instruction following | v2 candidate | acquisition target only |
| OpenAssistant OASST1 | assistant dialogue | v2 candidate | acquisition target only |
| UltraChat / UltraChat 200k | multi-turn dialogue | v2 candidate | acquisition target only |
| MentalChat16K and counseling/support-language data | lexical simplicity, empathy, de-escalation; not therapy authority | v2 candidate, safety reviewed | acquisition target only |
| WikiLarge / text simplification | plain-language rewriting | v2 candidate | acquisition target only |
| GSM8K | reasoning benchmark/reference | v2 candidate/eval | **acquired 2026-11-06** — 500 records, MIT (permissive), quarantined + manifested, converted to `datasets/acquired/gsm8k/gsm8k.jsonl`, pending Gate v2. **Evaluation only — never training data.** |
| MBPP | code task solving | v2 candidate/eval | acquisition target only |
| HumanEval | code evaluation | eval only by default | acquisition target only |
| BigCode The Stack / Stack v2-style data | code reference data subject to license review | quarantine first | **held — license review** (card license `other`, not on the permissive allowlist); manifest only, no download, no records, no conversion. A human must review the license before it can enter any lane. |
| ARC-native operator corrections | self-curated truth corrections | curated local lane | highest trust |
| Memory / continuity tasks | doctrine and state consistency | benchmark lane | local benchmark |

## Rule

No dataset enters the incumbent directly. Every new data source must preserve provenance and must be able to be removed, replayed, or rolled back.

## Hard rule — no external dataset pollution in the actual training, ever

The actual training must **never** be polluted by external datasets. GSM8K, The Stack, and any other external dataset are **evaluation/benchmark references only** — they never enter the training data. The training uses **only our own data** (the "us" corpus — general knowledge about our stuff and system).

Why: because testing must not be mixed into training, testing is instead **offloaded to the continuous live running system** — the live system running continuously (Lucid / the ping server / the bots, in real operation) tests and validates itself. The evaluation path is: benchmark (Gate v2, 168 tasks) first, then live continuous testing in the running system. External datasets are never training inputs.

Current enforcement, verified 2026-11-07:

- The native trainer's SFT collector (`scripts/training/train_arc_native_candidate.py::collect_sft_corpus`) reads a fixed dir list that does **not** include `datasets/acquired/` — the GSM8K rows are not ingested.
- The raw-text collector (`collect_corpus`) does not read `.jsonl` or `.parquet`, so the GSM8K rows are not swept — but it **would** sweep the two `datasets/acquired/*/manifest.json` files if the corpus cap were raised (`.json` is a collected extension and `acquired` is not in the skip list). Under the default cap the walk fills before reaching them, so this is a **latent** vector, not an active one. Fix: add `acquired` to `_CORPUS_SKIP_PARTS` (training workstream, not done here). **DONE 2026-11-08** — `acquired` is now in `_CORPUS_SKIP_PARTS` in `scripts/training/train_arc_native_candidate.py` (dataset-section work; verified by `scripts/ops/catalogue_datasets.py --check-only`, which fails if the skip is removed).
- GSM8K placement is closed by this rule: the 500 rows are **not** copied into `datasets/distillation_sft/` and the trainer's dir list is **not** extended to include them. They stay evaluation-only.

## Landed Phase 1 internal targeted data

The repo now includes internal v2-candidate-only Phase 1 records generated from audit findings:

- `datasets/distillation_sft/phase1_instruction_following.jsonl` — 50 records
- `datasets/distillation_sft/phase1_continuity.jsonl` — 50 records
- `datasets/distillation_sft/phase1_reflection.jsonl` — 50 records

These are self-curated ARC records, not external datasets. They are staged for future candidate training only and do not change the current incumbent until a trained candidate passes benchmark and Gate v2.

