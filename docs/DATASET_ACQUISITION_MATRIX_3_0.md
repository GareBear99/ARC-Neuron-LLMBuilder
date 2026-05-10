# Dataset Acquisition Matrix for ARC-Neuron 3.0

Status: planning matrix. This document does not approve ingestion by itself.

## Ring 0 — ARC-native truth data

Purpose: identity, doctrine, provenance, system behavior.

Examples:

- ARC docs
- receipts
- promotion reports
- rejected candidate reports
- benchmark outputs
- operator corrections
- architecture notes
- license notices
- dataset manifests

Default lane: `candidate_v1` or `candidate_v3` depending on release stage.

Risk: low if internally authored and manifest-backed.

## Ring 1 — general instruction following

Purpose: chat behavior, task following, formatting, generalization.

Examples:

- public instruction-tuning collections
- multi-turn assistant dialogues
- task-oriented Q/A sets

Default lane: `candidate_v2`.

Risk: medium. Requires license and content filtering.

## Ring 2 — reasoning and planning

Purpose: decomposition, repair, code reasoning, multi-step planning.

Preferred format:

```text
intent -> constraints -> plan -> action -> evidence -> result
```

Default lane: `candidate_v2`.

Risk: medium. Avoid unverifiable hidden chain-of-thought dumps; prefer structured traces and receipts.

## Ring 3 — lexical simplicity and support-language data

Purpose: simpler wording, empathy, de-escalation, sensitive-topic clarity.

Examples:

- plain-language rewriting
- supportive dialogue
- anonymized counseling-style datasets
- emotional support examples

Default lane: `candidate_v2` only.

Risk: high. Treat mental-health data as language/style/reference data, not as therapy authority. Require PII review, safety review, and medical/sensitive-data flags.

## Ring 4 — technical domain knowledge

Purpose: make ARC useful as a builder.

Examples:

- Python examples
- C++/JUCE examples
- FastAPI examples
- SQLite examples
- GGUF/llama.cpp documentation
- build/release engineering docs

Default lane: `candidate_v2` or retrieval-only until licensing is clear.

Risk: medium. License classification required.

## Ring 5 — safety, refusal, license, and provenance behavior

Purpose: protect the product and prevent bad ingestion.

Examples:

- license classification examples
- dataset approval/rejection examples
- PII-handling examples
- unsafe-output refusal examples
- commercial redistribution edge cases

Default lane: `candidate_v2` then `candidate_v3` after approval.

Risk: medium. Must be reviewed because this directly shapes gatekeeping behavior.

## Recommended 3.0 training mixture

```text
35% ARC-native doctrine / receipts / repo tasks
20% general instruction following
15% code + tool-use + repo repair
10% reasoning / planning / critique-revise
10% lexical simplicity / support-language behavior
5% refusal / safety / license law
5% adversarial regression tests
```

## Manifest rule

No manifest, no training.

