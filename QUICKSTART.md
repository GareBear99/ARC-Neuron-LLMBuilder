# Quickstart

A 10-minute tour of every major capability in ARC-Neuron LLMBuilder. Each section is independently runnable.

## 0. Install

```bash
git clone https://github.com/GareBear99/ARC-Neuron-LLMBuilder.git
cd ARC-Neuron-LLMBuilder

# Python 3.10+ required. 3.12 recommended.
python3.12 -m venv .venv
source .venv/bin/activate

# Core dependencies (always required)
pip install -r requirements.txt

# Training dependencies (only if you train native candidates)
pip install "torch>=2.0" "numpy<2.0"

# Generate runtime secrets (idempotent — safe to run multiple times)
python3 scripts/ops/bootstrap_keys.py
```

## 1. Verify the repo is healthy (30 seconds)

```bash
python3 -m pytest tests/ -q
```

**Expected**: `115 passed, 1 skipped in ~30s`. The skip is torch (optional). If other tests fail, investigate before proceeding.

## 2. Measure the Omnibinary ledger (15 seconds)

```bash
python3 scripts/ops/benchmark_omnibinary.py
```

**Expected**: 6,000+ events/sec append, 8,000+ O(1) lookups/sec, PASS on fidelity.

## 3. Run the 9-step end-to-end proof (2 minutes)

```bash
python3 scripts/ops/demo_proof_workflow.py
```

**What you'll see**:
1. Term taught to language module
2. Term retrieval proven
3. Conversation run through canonical pipeline (receipt + Omnibinary mirror)
4. Training data exported from the conversation
5. Candidate model trained (tiny tier, ~20 steps)
6. Candidate benchmarked + scored
7. Gate v2 decision (expected: archive_only — can't beat incumbent in 20 steps)
8. Omnibinary integrity verified
9. Prior Arc-RAR bundles confirmed restorable

**Expected**: 9/9 steps green.

## 4. Ask the incumbent a question (5 seconds)

```bash
python3 scripts/execution/run_direct_candidate.py \
  --adapter exemplar \
  --artifact exports/candidates/arc_governed_v10_wave4/exemplar_train/exemplar_model.json \
  --prompt "Critique a plan that ships without a rollback path."
```

You'll get a response assembled from the top-k cosine-retrieved training records. The system will explain its confidence bounds and list the supporting patterns it drew from.

## 5. Train your own candidate (3 minutes for small tier)

```bash
python3 scripts/training/train_arc_native_candidate.py \
  --candidate my_first_candidate \
  --tier small \
  --steps 300 \
  --batch-size 4
```

**What gets built**:
- `exports/candidates/my_first_candidate/lora_train/checkpoint/arc_native_my_first_candidate.pt`
- `exports/candidates/my_first_candidate/lora_train/checkpoint/arc_native_my_first_candidate.gguf`
- `exports/candidates/my_first_candidate/exemplar_train/exemplar_model.json`
- `reports/arc_native_train_my_first_candidate.json`

## 6. Benchmark your candidate (1 minute)

```bash
# Run the 142-task benchmark suite
python3 scripts/execution/run_model_benchmarks.py \
  --adapter exemplar \
  --artifact exports/candidates/my_first_candidate/exemplar_train/exemplar_model.json \
  --output results/my_first_candidate_outputs.jsonl

# Score the outputs with the task-aware rubric
python3 scripts/execution/score_benchmark_outputs.py \
  --input results/my_first_candidate_outputs.jsonl \
  --output results/my_first_candidate_scored.json
```

**Check the score**:
```bash
python3 -c "import json; d=json.load(open('results/my_first_candidate_scored.json')); print(f'overall: {d[\"overall_weighted_score\"]:.4f}  failures: {d[\"failure_count\"]}')"
```

## 7. Submit to Gate v2 (5 seconds)

```bash
python3 scripts/execution/promote_candidate.py \
  --scored results/my_first_candidate_scored.json \
  --model-name my_first_candidate \
  --candidate my_first_candidate
```

**Expected** (unless your candidate beats the v10_wave4 incumbent at 0.9237):
```json
{
  "ok": true,
  "promoted": false,
  "decision": "archive_only",
  ...
}
```

To check why, inspect `reports/promotion_decision.json`. You'll see the full receipt including the incumbent it challenged, any regression violations, and the decision reason.

## 8. Run a repeatability proof (5 minutes)

```bash
python3 scripts/ops/run_n_cycles.py --cycles 3 --tier tiny --steps 30
```

**Expected**: `Verdict: ✓ STABLE`. All 3 cycles complete with 0 floor breaches and 0 regressions.

## 9. Teach the system a new term and re-run (1 minute)

```bash
# Teach a term with manual correction (highest trust)
python3 runtime/terminology.py --correct "deterministic_gating" \
  "the property that gate decisions are reproducible from the same inputs and incumbent"

# See the term in the store
python3 runtime/terminology.py --lookup "deterministic_gating"

# Show stats
python3 runtime/terminology.py --stats
```

The term is now in the language module with provenance, mirrored to Omnibinary, and available for SFT export via `runtime/terminology.py --dump`.

## 10. Verify the Omnibinary store (5 seconds)

```bash
make verify-store
```

**Expected**:
```json
{
  "ok": true,
  "event_count": 98,
  "index_rebuilt": false,
  "sha256": "...",
  "path": "artifacts/omnibinary/arc_conversations.obin"
}
```

## The full governed loop in one command

After you've run the quickstart once, run the whole governed loop end-to-end:

```bash
make full-loop
```

This does: train → benchmark → score → gate → bundle → verify — with every step producing receipts and every artifact SHA-256 addressable.

## What to read next

- [README.md](./README.md) — overview and current state
- [ARCHITECTURE.md](./ARCHITECTURE.md) — the four roles and how they compose
- [GOVERNANCE_DOCTRINE.md](./GOVERNANCE_DOCTRINE.md) — how Gate v2 decides promotions
- [USAGE.md](./USAGE.md) — detailed reference for every command
- [RELEASE_NOTES_v1.0.0.md](./RELEASE_NOTES_v1.0.0.md) — current release evidence

## If something fails

1. **Tests fail**: check `torch` is installed with `numpy<2.0` pinned.
2. **Omnibinary benchmark fails**: check disk space in `artifacts/omnibinary/`.
3. **Training fails**: check Python version (3.10+) and that `torch.manual_seed` is importable.
4. **Benchmark can't find artifact**: confirm `exports/candidates/<name>/exemplar_train/exemplar_model.json` exists.
5. **Gate rejects every candidate**: check `configs/stack/regression_floor.json` — the floor may be locked higher than your candidate can clear. Use `python3 runtime/floor_model.py --status` to inspect.

File an issue with:
- The exact command you ran
- The error message
- Output of `python3 -m pytest tests/ -q` (first 20 lines is fine)
- Output of `python3 scripts/validate_repo.py`
