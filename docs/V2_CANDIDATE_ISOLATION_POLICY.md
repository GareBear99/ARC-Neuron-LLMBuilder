# v2 Candidate Isolation Policy

New weights, external datasets, support-language corpora, and experimental merges must enter a v2 candidate class before they can affect incumbent scoring.

## Protected lanes

- `floor_model`: never overwritten.
- `incumbent_model`: current promoted model only.
- `candidate_v1`: same data class as incumbent.
- `candidate_v2`: new dataset class, new support-language data, new external-source training.
- `quarantine`: untrusted, license-unclear, PII-risk, or scraped sources.

## Promotion rule

A v2 candidate must beat the incumbent and preserve protected floors. Improvement in empathy, lexical simplicity, or style does not justify regressions in planning, paraphrase stability, repair, continuity, refusal correctness, provenance reasoning, or ARC doctrine.
