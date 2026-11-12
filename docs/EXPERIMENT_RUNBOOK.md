# Experiment Runbook

## Purpose
Every meaningful run should leave behind structured evidence.

## Required run sequence
1. Validate repo
2. Check backend health
3. Run model benchmarks
4. Score outputs
5. Attempt promotion
6. Run quantization-retention report
7. Record experiment metadata

## Minimum experiment metadata
- model_name
- adapter
- backend endpoint
- prompt_profile
- benchmark input file
- scored output file
- promotion decision
- quantization report path
- notes

## Rule
No checkpoint should be described as improved unless an experiment record exists.

## Stock Llama 3.2 1B baseline (plan §5 Phase 2)

Harness: `scripts/execution/run_stock_1b_baseline.py` — runs the STOCK
(un-fine-tuned) Llama 3.2 1B through the 168-task benchmark via the
`openai_compatible` adapter and scores it with `scorers/rubric.py`.
The incumbent's 0.9237 (v10) is exemplar retrieval (TF-IDF), NOT a neural
score — this run is the true neural baseline the fine-tune is judged
against. No baseline number exists yet: the full run is blocked on (1) the
ping key (64-hex secret, Cloudflare only — Gary provides it via the Secure
Vault flow, or runs the harness himself, or the local T4/llamafile route is
used) and (2) Cloudflare blocking the repo adapter's urllib User-Agent
(HTTP 403 / error 1010) from this VM — the adapter needs a browser
User-Agent, or the run happens from an unblocked host. Cost of the full
run: 168 SP + a few hundred neurons; run once. `--dry-run` validates the
setup for 0 SP (benchmark loads, GET / answers). Full docs are in the
harness docstring. Evaluation path: benchmark baseline → Gate v2 on the
fine-tune → live continuous A/B in the running system. Training rule: no
external dataset (GSM8K, The Stack, any other) is ever in the actual
training data — this harness is evaluation only.
