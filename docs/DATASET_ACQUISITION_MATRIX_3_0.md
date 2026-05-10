# Dataset Acquisition Matrix — ARC-Neuron 3.0

This file records the external dataset/source candidates discussed for the 3.0 roadmap.

None of these external sources are claimed as already bundled, ingested, trained into the incumbent, or promoted into the live model lane. They are acquisition/evaluation targets only.

## Required intake path

Every external dataset must pass this path before it can affect a candidate:

1. source URL recorded;
2. license and allowed-use reviewed;
3. dataset manifest created;
4. raw hash recorded;
5. quarantine/raw storage used first;
6. transformed copy receives its own hash;
7. candidate-v2 lane only;
8. benchmark comparison against incumbent floors;
9. promotion only after no protected regression.

## Candidate sources

| Source | Link | Intended role | Status |
|---|---|---|---|
| FLAN Collection | https://github.com/google-research/FLAN | instruction tuning and task formatting | roadmap candidate |
| OpenAssistant OASST1 | https://huggingface.co/datasets/OpenAssistant/oasst1 | assistant dialogue and interaction | roadmap candidate |
| UltraChat / UltraChat 200k | https://huggingface.co/datasets/HuggingFaceH4/ultrachat_200k | multi-turn chat and instruction data | roadmap candidate |
| MentalChat16K | https://huggingface.co/papers/2503.13509 | support-language, empathy, lexical simplicity research lane only | roadmap candidate |
| WikiLarge / simplification references | https://huggingface.co/datasets/liweili/c4_200m/tree/main | plain-language rewriting and simplification references | roadmap candidate |
| GSM8K | https://huggingface.co/datasets/openai/gsm8k | math reasoning references | roadmap candidate |
| MBPP | https://huggingface.co/datasets/google-research-datasets/mbpp | Python/code task generation and repair | roadmap candidate |
| HumanEval | https://github.com/openai/human-eval | code generation evaluation | roadmap candidate |
| BigCode The Stack / The Stack v2 | https://huggingface.co/bigcode | code corpus reference with strict license review | roadmap candidate |
| ARC-native operator corrections | local repo artifacts | highest-trust self-curated correction/receipt lane | active/self-curated |
| Memory continuity tasks | local repo benchmarks/configs | repeated-question, doctrine-retention, provenance tests | repo-owned eval lane |

## Boundary

Mental-health/counseling-style data is not a medical claim and is not a therapy product lane. It is only a candidate support-language lane for clarity, de-escalation, empathy, and plain-English response behavior.
