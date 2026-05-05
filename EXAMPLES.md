# Examples

End-to-end recipes for common use cases. Every example is runnable after `make validate && make test`.

## Table of contents

- [1. First-time tour](#1-first-time-tour)
- [2. Ask the incumbent a question](#2-ask-the-incumbent-a-question)
- [3. Teach a new term and harvest it for training](#3-teach-a-new-term-and-harvest-it-for-training)
- [4. Train a new candidate and try to promote it](#4-train-a-new-candidate-and-try-to-promote-it)
- [5. Run a repeatability proof](#5-run-a-repeatability-proof)
- [6. Wrap an adapter with reflection](#6-wrap-an-adapter-with-reflection)
- [7. Inspect an Arc-RAR bundle](#7-inspect-an-arc-rar-bundle)
- [8. Verify the Omnibinary ledger](#8-verify-the-omnibinary-ledger)
- [9. Plug in a local llama.cpp server](#9-plug-in-a-local-llamacpp-server)
- [10. Author a benchmark task](#10-author-a-benchmark-task)

---

## 1. First-time tour

```bash
git clone https://github.com/GareBear99/ARC-Neuron-LLMBuilder.git
cd ARC-Neuron-LLMBuilder
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt "torch>=2.0" "numpy<2.0"
python3 scripts/ops/bootstrap_keys.py

python3 -m pytest tests/ -q                   # 115 passed, 1 skipped
python3 scripts/ops/demo_proof_workflow.py    # 9/9 green
```

## 2. Ask the incumbent a question

```bash
python3 scripts/execution/run_direct_candidate.py \
  --adapter exemplar \
  --artifact exports/candidates/arc_governed_v10_wave4/exemplar_train/exemplar_model.json \
  --prompt "Critique a plan that ships without a rollback path."
```

The response is cosine-retrieved from the 762 exemplar records baked into v6. Expect a 1-2 paragraph response that reasons about the governed-change contract and cites supporting patterns from the training records.

## 3. Teach a new term and harvest it for training

```bash
# Teach with manual-correction trust (highest rank)
python3 runtime/terminology.py --correct "speculative_decoding" \
  "a technique where a smaller draft model proposes tokens for a larger model to verify"

# Export approved terms as SFT training pairs
python3 runtime/terminology.py --dump
# Writes datasets/language_reasoning/terminology_sft.jsonl

# Inspect the term
python3 runtime/terminology.py --lookup "speculative_decoding"
```

Next time you train a candidate, this term is included in the corpus:

```bash
python3 scripts/training/train_arc_native_candidate.py \
  --candidate v7_with_speculative_decoding --tier small --steps 300
```

## 4. Train a new candidate and try to promote it

```python
# Python, inside the repo
import json, subprocess, sys
from pathlib import Path

CAND = "v7_example"
PY = sys.executable

# Step 1: train
subprocess.run([PY, "scripts/training/train_arc_native_candidate.py",
                "--candidate", CAND, "--tier", "small", "--steps", "300"], check=True)

# Step 2: benchmark
subprocess.run([PY, "scripts/execution/run_model_benchmarks.py",
                "--adapter", "exemplar",
                "--artifact", f"exports/candidates/{CAND}/exemplar_train/exemplar_model.json",
                "--output", f"results/{CAND}_outputs.jsonl"], check=True)

# Step 3: score
subprocess.run([PY, "scripts/execution/score_benchmark_outputs.py",
                "--input", f"results/{CAND}_outputs.jsonl",
                "--output", f"results/{CAND}_scored.json"], check=True)

scored = json.loads(Path(f"results/{CAND}_scored.json").read_text())
print(f"overall: {scored['overall_weighted_score']:.4f}")

# Step 4: gate
subprocess.run([PY, "scripts/execution/promote_candidate.py",
                "--scored", f"results/{CAND}_scored.json",
                "--model-name", CAND, "--candidate", CAND], check=True)

# Step 5: read the receipt
receipt = json.loads(Path("reports/promotion_decision.json").read_text())
print(f"decision: {receipt['decision']}")
print(f"reason:   {receipt['decision_reason']}")
```

Or with Make:

```bash
make full-loop
```

## 5. Run a repeatability proof

```bash
python3 scripts/ops/run_n_cycles.py --cycles 5 --tier tiny --steps 30
```

Expected output:
```
  total_cycles             : 5
  completed                : 5
  promoted                 : 0
  archive_only             : 5
  rejected                 : 0
  floor_breaches           : 0
  regressions              : 0
  loop_stable              : True
  Verdict: ✓ STABLE
```

A stable loop means the gate correctly rejects identical-twin candidates that cannot beat the current incumbent.

## 6. Wrap an adapter with reflection

```python
from adapters.exemplar_adapter import ExemplarAdapter
from runtime.reflection_loop import ReflectionLoop
from runtime.conversation_pipeline import ConversationPipeline
from pathlib import Path

base = ExemplarAdapter(
    artifact="exports/candidates/arc_governed_v10_wave4/exemplar_train/exemplar_model.json",
    top_k=3,
)
adapter = ReflectionLoop(base, skip_on_short=60)

pipeline = ConversationPipeline(adapter,
    store_path=Path("artifacts/omnibinary/arc_conversations.obin"),
    conversation_id="my_session",
)

record = pipeline.run_conversation(
    "Propose a minimum-scope repair for a failing regression test.",
    system_prompt="Plan, critique, repair, calibrate.",
)

print(record.response_text)
print("reflection stages:", record.meta.get("reflection"))
```

The response goes through draft → critique → revise before emission. All three stages are captured in `record.meta["reflection"]`.

## 7. Inspect an Arc-RAR bundle

```python
from runtime.learning_spine import read_arc_rar_manifest
from pathlib import Path

bundle = Path("artifacts/archives/arc-rar-arc_governed_v6_conversation-2acf171e.arcrar.zip")
mf = read_arc_rar_manifest(bundle)
print(f"candidate: {mf['candidate']}")
print(f"files:     {mf['file_count']}")
print(f"SHA-256 index entries: {len(mf.get('sha256_index', {}))}")
```

Or extract a specific file without unpacking:

```python
import zipfile
with zipfile.ZipFile(bundle) as z:
    receipt = z.read("promotion_report.json").decode()
    print(receipt)
```

## 8. Verify the Omnibinary ledger

```python
from runtime.learning_spine import OmnibinaryStore
from pathlib import Path
import json

store = OmnibinaryStore(Path("artifacts/omnibinary/arc_conversations.obin"))
v = store.verify()
print(json.dumps(v, indent=2))

# Retrieve a specific event by ID (O(1))
events = list(store.scan())
first = events[0]
re_fetched = store.get(first.event_id)
assert re_fetched.event_id == first.event_id
```

## 9. Plug in a local llama.cpp server

```bash
# Start llama.cpp server (assumes you have a GGUF downloaded)
llama-server -m /path/to/qwen3-32b-instruct-q5_k_m.gguf --port 8080 -c 8192

# Configure the runtime
export COGNITION_RUNTIME_ADAPTER=llama_cpp_http
export COGNITION_BASE_URL=http://127.0.0.1:8080
export COGNITION_MODEL_NAME=qwen3-32b-instruct

# Run a single prompt
python3 scripts/execution/run_direct_candidate.py \
  --adapter llama_cpp_http \
  --prompt "Summarize the governance doctrine in three sentences."

# Benchmark the external model through the same gate
python3 scripts/execution/run_model_benchmarks.py \
  --adapter llama_cpp_http \
  --output results/qwen3_32b_outputs.jsonl
python3 scripts/execution/score_benchmark_outputs.py \
  --input results/qwen3_32b_outputs.jsonl \
  --output results/qwen3_32b_scored.json
```

Every governance path operates identically. The only thing that changed is which adapter produces the text.

## 10. Author a benchmark task

```json
{
  "id": "my_reasoning_001",
  "capability": "reasoning",
  "domain": "governed_change",
  "difficulty": "medium",
  "prompt": "A proposal preserves interface A but removes receipt B. Evaluate the tradeoff.",
  "reference": {
    "rubric": "must separate fact from inference, name the conflict, and reject or conditionally bound"
  },
  "scoring": "rubric",
  "tags": ["reasoning", "governed_change"]
}
```

Save to `benchmarks/reasoning/custom_tasks.jsonl` (one JSON object per line). The next benchmark run picks it up automatically.

To validate the file before running:

```python
from runtime.task_loader import load_jsonl
from pathlib import Path
for t in load_jsonl(Path("benchmarks/reasoning/custom_tasks.jsonl")):
    print(t["id"], t["capability"])
```
