# ARC-Neuron LLMBuilder — Step-by-Step Guide

Everything you need to go from zero to a running governed AI system,
verified on a 2012 Intel Mac with no GPU.

---

## Prerequisites

```bash
python3 --version   # 3.10 or higher required
git --version       # any recent version
```

No GPU. No cloud account. No Docker required (optional).

---

## Step 1 — Clone and install

```bash
git clone https://github.com/GareBear99/ARC-Neuron-LLMBuilder.git
cd ARC-Neuron-LLMBuilder
pip install -r requirements.txt
```

---

## Step 2 — Verify the repo is clean

```bash
python3 scripts/validate_repo.py
```

Expected output:
```json
{
  "ok": true,
  "errors": []
}
```

If you see errors, check that all files from the latest release are present.

---

## Step 3 — Run the test suite

```bash
python3 -m pytest tests/ -v
```

Expected: **115 passed, 1 skipped**  
The skip is `torch` (not required for basic operation). All 136 tests run CPU-only.

---

## Step 4 — Run the proof workflow

This is the single-command end-to-end demonstration. It trains a candidate,
scores it, archives it, and produces a receipt — all in one shot.

```bash
python3 scripts/ops/demo_proof_workflow.py
```

Expected output (values will differ by run):
```json
{
  "ok": true,
  "term_stored": "proof_cycle",
  "obin_events": 4,
  "candidate": "demo_20260504T041611Z",
  "score": 0.0,
  "decision": "unknown",
  "bundles": 12
}
```

`score: 0.0` is expected for a demo candidate — it has no training data.
The proof is that the pipeline ran end-to-end and produced a receipt.

---

## Step 5 — Benchmark the current incumbent

```bash
python3 << 'PYEOF'
import sys, json, os
sys.path.insert(0, '.')
from scorers.rubric import score_record
from adapters.exemplar_adapter import ExemplarAdapter

model = ExemplarAdapter(
    artifact='exports/candidates/arc_governed_v10_wave4/exemplar_train/exemplar_model.json'
)

all_scores = []
print(f"{'Capability':<30} {'Score':>7}  Bar")
print("-" * 60)
for cap_dir in sorted(os.listdir('benchmarks')):
    path = f'benchmarks/{cap_dir}/seed_tasks.jsonl'
    if not os.path.exists(path):
        continue
    tasks = [json.loads(l) for l in open(path) if l.strip()]
    scores = []
    for t in tasks:
        cap = t.get('capability', cap_dir)
        resp = model.generate(t['prompt'], context={'capability': cap})
        scores.append(score_record(resp.text, t)['normalized_score'])
    avg = round(sum(scores) / len(scores), 4)
    all_scores.extend(scores)
    bar = '█' * int(avg * 20) + '░' * (20 - int(avg * 20))
    print(f"  {cap_dir:<28} {avg:>7.4f}  {bar}")

overall = round(sum(all_scores) / len(all_scores), 4)
print(f"\n  {'OVERALL':<28} {overall:>7.4f}")
PYEOF
```

Expected overall: **~0.9237**

---

## Step 6 — Benchmark the archive layer

```bash
python3 scripts/ops/benchmark_omnibinary.py
```

Expected results:
- Append throughput: ~4,000–5,000 events/sec
- Lookup latency: ~300–400 µs
- Restore fidelity: **1.000** (exact bit-for-bit recovery)

---

## Step 7 — Train your first candidate

This uses the current training corpus to build a new exemplar candidate:

```bash
python3 scripts/training/train_exemplar_candidate.py --candidate my_first_candidate
```

The artifact lands at:
```
exports/candidates/my_first_candidate/exemplar_train/exemplar_model.json
```

---

## Step 8 — Score your candidate against the incumbent

```bash
python3 << 'PYEOF'
import sys, json, os
sys.path.insert(0, '.')
from scorers.rubric import score_record
from adapters.exemplar_adapter import ExemplarAdapter

INCUMBENT = 'exports/candidates/arc_governed_v10_wave4/exemplar_train/exemplar_model.json'
CANDIDATE = 'exports/candidates/my_first_candidate/exemplar_train/exemplar_model.json'

inc = ExemplarAdapter(artifact=INCUMBENT)
cand = ExemplarAdapter(artifact=CANDIDATE)

all_inc, all_cand = [], []
for cap_dir in sorted(os.listdir('benchmarks')):
    path = f'benchmarks/{cap_dir}/seed_tasks.jsonl'
    if not os.path.exists(path):
        continue
    tasks = [json.loads(l) for l in open(path) if l.strip()]
    for t in tasks:
        cap = t.get('capability', cap_dir)
        all_inc.append(score_record(inc.generate(t['prompt'], context={'capability': cap}).text, t)['normalized_score'])
        all_cand.append(score_record(cand.generate(t['prompt'], context={'capability': cap}).text, t)['normalized_score'])

inc_overall  = round(sum(all_inc)  / len(all_inc),  4)
cand_overall = round(sum(all_cand) / len(all_cand), 4)
delta = cand_overall - inc_overall

print(f"Incumbent : {inc_overall:.4f}")
print(f"Candidate : {cand_overall:.4f}")
print(f"Delta     : {delta:+.4f}")
print(f"Decision  : {'PROMOTE' if delta > 0 else 'REJECT'}")
PYEOF
```

---

## Step 9 — Add your own training examples

Create a JSONL file in `datasets/distillation_sft/`:

```jsonl
{"capability": "reasoning", "prompt": "Is a 400-request canary sample sufficient to promote?", "target": "No. 400 requests is insufficient statistical power to distinguish a real improvement from noise at sub-1% error rate deltas. Accumulate at least 5000 requests before evaluating promotion."}
{"capability": "planning", "prompt": "Plan a safe canary rollout.", "target": "Step 1: route 1% of traffic to canary. Step 2: monitor error rate and latency for 24 hours. Step 3: if stable, expand to 10%. Step 4: run statistical significance check at 5000 requests. Step 5: promote if all checks pass."}
```

Then retrain:
```bash
python3 scripts/training/train_exemplar_candidate.py --candidate my_improved_candidate
```

Score and compare to incumbent as in Step 8.

---

## Step 10 — Promote a winning candidate

If your candidate beats the incumbent:

```bash
# Copy to the new incumbent slot
mkdir -p exports/candidates/arc_governed_v11_mine/exemplar_train
cp exports/candidates/my_improved_candidate/exemplar_train/exemplar_model.json \
   exports/candidates/arc_governed_v11_mine/exemplar_train/exemplar_model.json

# Update the scoreboard (optional but recommended)
# Add an entry to results/scoreboard.json with your scores
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ModuleNotFoundError: torch` | torch not installed | Install with `pip install torch` or skip — torch is optional for basic operation |
| Score is 0.0 on all tasks | No cap-matched exemplars | Add training examples for that capability |
| Score regressed after adding exemplars | Retrieval contamination | Ensure new exemplars use distinctive vocabulary for their capability |
| `validate_repo.py` errors | Missing required file | Check the error — usually a missing `.env.direct-runtime.example` |

---

## Directory Map

```
ARC-Neuron-LLMBuilder/
├── adapters/
│   └── exemplar_adapter.py      ← retrieval brain (TF-IDF)
├── arc_core/
│   └── transformer.py           ← PyTorch CausalLM (train this next)
├── benchmarks/
│   └── <capability>/
│       └── seed_tasks.jsonl     ← 10–12 tasks per capability
├── datasets/
│   └── distillation_sft/        ← training exemplars (add yours here)
├── exports/
│   └── candidates/
│       └── arc_governed_v10_wave4/  ← current incumbent
├── scorers/
│   └── rubric.py               ← capability scoring rubric
├── scripts/
│   ├── ops/
│   │   ├── demo_proof_workflow.py
│   │   └── benchmark_omnibinary.py
│   └── training/
│       └── train_exemplar_candidate.py
└── tests/
    └── *.py                    ← 136 tests
```
