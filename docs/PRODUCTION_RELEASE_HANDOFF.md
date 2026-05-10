# ARC-Neuron LLMBuilder — Production Release Handoff

Date: 2026-05-09
Package class: professional production candidate / protected 3.0 roadmap baseline

## Release truth

This repository is clean enough to hand off as a professional production candidate for ARC-Neuron/LLMBuilder. The shipped state is intentionally conservative:

- `arc_governed_v10_wave4` remains the reproducible incumbent.
- v11.3 / wave5 remains in a candidate/staging lane until regenerated evidence passes Gate v2 from the shipped files.
- v2-class and 3.0-class weights must remain isolated from incumbent scoring until promoted by receipts.
- External GGUFs, teacher models, scraped corpora, and sensitive datasets are proposal/reference sources only until quarantine, license, safety, and provenance gates pass.

## Verified from package

| Check | Result |
|---|---:|
| `python -m compileall -q .` | PASS |
| `python scripts/validate_repo.py` | PASS |
| Test modules | 136 / 136 passed when run by module |
| Validator inventory | 109 JSONL, 45 YAML, 444 JSON checked |
| Dataset inventory | 6 dataset files / 120 records |
| Benchmark inventory | 17 benchmark files / 168 tasks |

## Production doctrine now included

- `docs/KNOWLEDGE_PRESERVATION_DOCTRINE.md`
- `docs/V2_CANDIDATE_ISOLATION_POLICY.md`
- `docs/ARC_NEURON_3_0_ROADMAP_INTEGRATION.md`
- `docs/DATASET_ACQUISITION_MATRIX_3_0.md`
- `configs/datasets/dataset_manifest_template.yaml`
- `configs/candidates/v2_class_policy.yaml`
- `LICENSE_TRANSITIONAL_NOTICE.md`

## Remaining hard gates before calling v11.3 promoted

1. Rebuild v11.3 from the shipped SFT packs.
2. Rerun full benchmark.
3. Confirm no protected-floor breach, especially planning and paraphrase stability.
4. Generate the real Arc-RAR archive bundle.
5. Update `results/scoreboard.json` only after Gate v2 accepts.
6. Keep rejected candidates archived with receipts rather than deleting them.

## 3.0 readiness rule

3.0 is not just a code release. It is a protected base-model release with connected datasets, manifests, lineage, receipts, rollback, license controls, and isolated candidate classes.

The governing rule is:

> ARC-Neuron should never merely become smarter. It should know how it became smarter, preserve the path, and keep rollback evidence.
