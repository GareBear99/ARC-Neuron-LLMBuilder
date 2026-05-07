# Usage

Full reference for every major command in ARC-Neuron LLMBuilder. See [QUICKSTART.md](./QUICKSTART.md) for a guided tour.

---

## Setup commands

### `scripts/ops/bootstrap_keys.py`
Generate runtime secrets. Idempotent. Never overwrites without `--force`.

```bash
python3 scripts/ops/bootstrap_keys.py [--force] [--dry-run]
```

- `--force` — rotate keys (invalidates signed receipts).
- `--dry-run` — show what would be written without writing.

---

## Validation commands

### `scripts/validate_repo.py`
Verify required files, directory structure, and manifest integrity.

```bash
python3 scripts/validate_repo.py
```

### `tests/`
Full 115-test suite (115 passing, 1 skipped).

```bash
python3 -m pytest tests/ -q
python3 -m pytest tests/test_omnibinary_pipeline_promotion.py -v   # subset
```

### `scripts/ops/benchmark_omnibinary.py`
Measure Omnibinary ledger throughput and fidelity.

```bash
python3 scripts/ops/benchmark_omnibinary.py
```

Outputs append throughput, O(1) lookup p50/p99, full scan time, index rebuild time, storage per event, and fidelity pass/fail.

---

## Training commands

### `scripts/training/train_arc_native_candidate.py`
Train a native ARC transformer end-to-end. Produces `.pt`, `.gguf`, and exemplar sidecar.

```bash
python3 scripts/training/train_arc_native_candidate.py \
  --candidate <name> \
  --tier {tiny|small|base} \
  --steps 300 \
  --batch-size 4 \
  --lr 2e-3 \
  --seed 1337 \
  --max-corpus-bytes 600000 \
  --eval-batches 20
```

Tier presets:
- `tiny` — vocab=256, block=64, 2L, 4H, 64d (~0.05M params)
- `small` — vocab=256, block=128, 3L, 4H, 64d (~0.18M params)
- `base` — vocab=256, block=256, 4L, 8H, 128d (larger — needs GPU for reasonable speed)

### `scripts/training/train_lora_candidate.py`
Routes to native training when `--base-model` is an ARC-native name; falls back to scaffold for external bases.

```bash
python3 scripts/training/train_lora_candidate.py --candidate my_cand --base-model arc_neuron_small
```

### `scripts/training/prepare_distillation_corpus.py`
Assemble a unified SFT corpus from all distillation sources.

```bash
python3 scripts/training/prepare_distillation_corpus.py
```

---

## Benchmark commands

### `scripts/execution/run_model_benchmarks.py`
Run the 142-task suite against a candidate's exemplar artifact (14 capabilities × ~10 tasks each).

```bash
python3 scripts/execution/run_model_benchmarks.py \
  --adapter exemplar \
  --artifact exports/candidates/<name>/exemplar_train/exemplar_model.json \
  --output results/<name>_outputs.jsonl
```

### `scripts/execution/score_benchmark_outputs.py`
Score benchmark outputs with the task-aware rubric.

```bash
python3 scripts/execution/score_benchmark_outputs.py \
  --input results/<name>_outputs.jsonl \
  --output results/<name>_scored.json
```

Output includes per-capability summary, overall weighted score, failure count, and the scorer version used.

---

## Promotion commands

### `scripts/execution/promote_candidate.py`
Apply Gate v2 to a scored candidate. Writes a promotion receipt and (on promote/archive_only) an Arc-RAR bundle.

```bash
python3 scripts/execution/promote_candidate.py \
  --scored results/<name>_scored.json \
  --model-name <name> \
  --candidate <name> \
  [--scoreboard results/scoreboard.json] \
  [--report reports/promotion_decision.json] \
  [--skip-bundle] \
  [--floor-path configs/stack/regression_floor.json]
```

Decision output:
```json
{
  "ok": true,
  "promoted": false,
  "decision": "archive_only",
  "report": "reports/promotion_decision.json",
  "overall_weighted_score": 0.9237,  // v10_wave4 incumbent
  "arc_rar_bundle": null,
  "regression_violations": []
}
```

### `scripts/execution/run_full_candidate_gate.py`
Run the full candidate gate cycle: benchmark, score, promote.

```bash
python3 scripts/execution/run_full_candidate_gate.py
```

### `runtime/floor_model.py`
Manage the regression floor.

```bash
python3 runtime/floor_model.py --status
python3 runtime/floor_model.py --set-floor --from-scoreboard --note "after v6 promote"
python3 runtime/floor_model.py --set-floor --from-scored results/<name>_scored.json
```

---

## Archive and ledger commands

### `scripts/ops/bundle_promoted_candidate.py`
Build an Arc-RAR bundle for a candidate.

```bash
python3 scripts/ops/bundle_promoted_candidate.py --candidate <name>
```

### Omnibinary inspection

```bash
# Verify integrity
python3 -c "from pathlib import Path; import sys, json; sys.path.insert(0,'.'); \
  from runtime.learning_spine import OmnibinaryStore; \
  print(json.dumps(OmnibinaryStore(Path('artifacts/omnibinary/arc_conversations.obin')).verify(), indent=2))"

# Make target
make verify-store
```

### Arc-RAR inspection

```bash
python3 -c "from pathlib import Path; import sys, json; sys.path.insert(0,'.'); \
  from runtime.learning_spine import read_arc_rar_manifest; \
  print(json.dumps(read_arc_rar_manifest(Path('artifacts/archives/arc-rar-arc_governed_v6_conversation-2acf171e.arcrar.zip')), indent=2))"
```

---

## Conversation commands

### `scripts/execution/run_direct_candidate.py`
Run a single prompt through a candidate.

```bash
python3 scripts/execution/run_direct_candidate.py \
  --adapter exemplar \
  --artifact exports/candidates/<name>/exemplar_train/exemplar_model.json \
  --prompt "your question here"
```

Supported adapters: `exemplar`, `heuristic`, `echo`, `command`, `llama_cpp_http`, `openai_compatible`.

### `scripts/ops/absorb_session.py`
One-command session absorption.

```bash
python3 scripts/ops/absorb_session.py \
  --text "Long conversation text ..." \
  --session-id my_session_1
```

Extracts terminology, mirrors to Omnibinary, runs the canonical pipeline, and exports training candidates.

### `runtime/terminology.py`
CLI for the terminology store.

```bash
# Manually correct a term (highest trust)
python3 runtime/terminology.py --correct "my_term" "canonical definition"

# Look up a term
python3 runtime/terminology.py --lookup "my_term"

# Absorb from arbitrary text
python3 runtime/terminology.py --absorb "The text contains definitions to extract..."

# Show store statistics
python3 runtime/terminology.py --stats

# Export approved terms as SFT training pairs
python3 runtime/terminology.py --dump
```

---

## Proof and repeatability commands

### `scripts/ops/demo_proof_workflow.py`
9-step end-to-end demonstration of the whole loop.

```bash
python3 scripts/ops/demo_proof_workflow.py
```

### `scripts/ops/run_proof_workflow.py`
Single golden-path script covering term teaching, conversation, export, training, benchmark, gate, archive.

```bash
python3 scripts/ops/run_proof_workflow.py \
  --term "my_term" \
  --definition "..." \
  --prompt "..." \
  [--skip-training]       # skip train/bench/gate for fast pipeline-only proof
  [--candidate custom_name]
  [--steps 100]
  [--json-report path/to/report.json]
```

### `scripts/ops/run_n_cycles.py`
N-cycle repeatability runner with stability verdict.

```bash
python3 scripts/ops/run_n_cycles.py \
  --cycles 3 \
  --tier tiny \
  --steps 30 \
  --batch 4
```

Output includes: completed count, promoted count, archive-only count, rejected count, floor breaches, regressions, score range, and `loop_stable: true|false`.

### `scripts/ops/generate_reflection_sft.py`
Generate draft → critique → revise SFT pairs from the incumbent for the next training wave.

```bash
python3 scripts/ops/generate_reflection_sft.py
```

---

## Makefile targets

```bash
make validate          # scripts/validate_repo.py
make test              # pytest tests/ -q
make counts            # count datasets and benchmarks
make candidate-gate    # run_full_candidate_gate.py
make backend-check     # check_local_backend.py
make bundle            # generate_release_bundle.py
make model-card        # generate_model_card.py
make readiness         # generate_readiness_report.py
make smoke-local       # smoke_local_candidate.py
make native-tiny       # train arc_native_tiny
make native-small      # train arc_native_small
make full-loop         # train → benchmark → score → gate → bundle → verify
make pipeline          # one conversation through canonical pipeline
make bootstrap-keys    # generate runtime keys
make bundle-candidate CANDIDATE=<name>
make verify-store      # Omnibinary verify
make prepare-corpus    # distillation corpus prep
make training-readiness # training readiness gate
make distillation-counts
```

---

## Plugging in a stronger model backend

### Local llama.cpp server

```bash
# Start the server
llama-server -m /path/to/model.gguf --port 8080 -c 8192

# Point the runtime at it
export COGNITION_RUNTIME_ADAPTER=llama_cpp_http
export COGNITION_BASE_URL=http://127.0.0.1:8080
export COGNITION_MODEL_NAME=my-model
```

Every governance command now operates against the local server with zero code changes.

### Direct binary (llama-cli, llamafile)

```bash
scripts/operator/register_gguf_runtime.sh \
  --gguf /absolute/path/to/model.gguf \
  --binary /absolute/path/to/llama-cli

# Or for a self-contained llamafile:
scripts/operator/register_gguf_runtime.sh \
  --llamafile /absolute/path/to/model.llamafile
```

### OpenAI-compatible HTTP (vLLM, TGI, etc.)

```bash
export COGNITION_RUNTIME_ADAPTER=openai_compatible
export COGNITION_BASE_URL=http://your-server/v1/chat/completions
export COGNITION_MODEL_NAME=your-model
export COGNITION_API_KEY=your-key-if-needed
```

---

## Environment variables

Copy `.env.direct-runtime.example` to `.env.direct-runtime` and fill in:

```bash
COGNITION_RUNTIME_ADAPTER=exemplar
COGNITION_EXEMPLAR_ARTIFACT=exports/candidates/arc_governed_v10_wave4/exemplar_train/exemplar_model.json
COGNITION_TIMEOUT_SECONDS=120
COGNITION_FIRST_OUTPUT_TIMEOUT_SECONDS=30
COGNITION_IDLE_TIMEOUT_SECONDS=20
COGNITION_MAX_OUTPUT_BYTES=262144
ARC_CONVERSATION_STORE=artifacts/omnibinary/arc_conversations.obin
```

---

## Debugging

### Check scoreboard

```bash
python3 -c "import json; d=json.load(open('results/scoreboard.json')); \
  [print(f'{m[\"model\"]:40s} score={m[\"overall_weighted_score\"]:.4f} decision={m.get(\"decision\",\"?\"):13s} incumbent={m.get(\"incumbent\")}') for m in d['models']]"
```

### Inspect floor model

```bash
python3 runtime/floor_model.py --status
```

### Verify a specific Arc-RAR bundle

```bash
python3 -c "import zipfile, json; z=zipfile.ZipFile('artifacts/archives/<file>.arcrar.zip'); \
  print(json.dumps(json.loads(z.read('manifest.json')), indent=2))"
```

### Count benchmarks

```bash
find benchmarks -name '*.jsonl' | xargs wc -l | tail -1
```
