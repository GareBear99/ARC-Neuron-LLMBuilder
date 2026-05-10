# ARC-Neuron v2.1.0-governed — Drop-in Package

**Incumbent:** arc_governed_v11_3_wave5 at **0.9465** (+2.3% vs v2.0.0)
**Tests:** 136/136 | **Benchmark:** 165/165, 0 failures | **New records:** +165 exemplars

---

## What is in this package

```
arc_v11_dropin/
├── arc_core/
│   ├── context_window_manager.py          NEW module — drop into arc_core/
│   └── intent_receipt_engine.py           NEW module — drop into arc_core/
├── datasets/distillation_sft/
│   ├── v6_reflection_sft.jsonl            30 records — reflection gap closure
│   ├── v6_deterministic_compliance_sft.jsonl  20 records
│   ├── v6_planning_sft.jsonl              20 records
│   ├── v11_continuity_sft.jsonl           20 records
│   ├── v11_intelligence_sft.jsonl         28 records
│   ├── v11_surgical_sft.jsonl             26 records
│   └── v11_precision_sft.jsonl            22 records
├── configs/stack/
│   └── regression_floor.json             REPLACE — new floor locked at v11.3
├── scripts/execution/
│   ├── run_model_benchmarks_PATCH.md      Apply 5-line change to register new profiles
│   └── promote_candidate_PATCH.md        Apply 2 fixes (incumbent flag + calibration_error)
├── scorers/
│   └── rubric_PATCH.md                   Apply prefix-strip fix
├── CHANGELOG_v2.1.0.md                   Prepend to CHANGELOG.md
└── gitignore_additions.txt               Append to .gitignore
```

---

## Apply in this order

### 1. New files — copy directly (no conflicts)

```bash
cp arc_core/context_window_manager.py   /your/repo/arc_core/
cp arc_core/intent_receipt_engine.py    /your/repo/arc_core/
cp datasets/distillation_sft/*.jsonl    /your/repo/datasets/distillation_sft/
cp configs/stack/regression_floor.json /your/repo/configs/stack/
```

### 2. Apply code patches — three files to edit

**a) `scripts/execution/run_model_benchmarks.py`**
Find the `system_prompt = {` dict (around line 59) and add two entries:
```python
"full_benchmark_v6": "Think in plans, critique weak points, repair conservatively, calibrate uncertainty.",
"governance_v1":     "Reason from evidence. Bound your confidence. Acknowledge corrections. Produce receipts.",
```
See `run_model_benchmarks_PATCH.md` for full before/after.

**b) `scripts/execution/promote_candidate.py`** — two fixes:

Fix 1 — change incumbent selection from max(score) to flag-first:
```python
# BEFORE:
incumbent = max(promotable_models, key=lambda m: m.get("overall_weighted_score", 0.0), default=None)

# AFTER:
_flagged = [m for m in promotable_models if m.get("incumbent", False)]
incumbent = (
    _flagged[0] if _flagged
    else max(promotable_models, key=lambda m: m.get("overall_weighted_score", 0.0), default=None)
)
```

Fix 2 — ensure `calibration_error` is written to scoreboard entries:
```python
"calibration_error": round(1.0 - summary.get("calibration", 1.0), 4),
```

Fix 3 — retroactively patch existing scoreboard entries (run once):
```python
for m in sb["models"]:
    if "calibration" in m and "calibration_error" not in m:
        m["calibration_error"] = round(1.0 - m["calibration"], 4)
```

See `promote_candidate_PATCH.md` for full context.

**c) `scorers/rubric.py`**
Find the prefix-strip block in `score_record()` (around line 128) and replace:
```python
# BEFORE:
if text.lower().startswith("capability:"):
    text = text.split("\n", 1)[-1].strip()

# AFTER:
lines = text.splitlines()
cap_idx = next(
    (i for i, l in enumerate(lines) if l.strip().lower().startswith("capability:")),
    None,
)
if cap_idx is not None:
    text = "\n".join(lines[cap_idx + 1:]).strip()
if not text:
    text = (output_text or "").strip()
```
See `rubric_PATCH.md` for full context.

### 3. Update .gitignore

```bash
cat gitignore_additions.txt >> /your/repo/.gitignore
```

### 4. Update CHANGELOG.md

Prepend contents of `CHANGELOG_v2.1.0.md` after the header section in your `CHANGELOG.md`.

### 5. Verify

```bash
cd /your/repo
python3 arc_core/context_window_manager.py    # should print: All self-tests passed.
python3 arc_core/intent_receipt_engine.py     # should print: All self-tests passed.
python3 -m pytest tests/ -q                   # should print: 136 passed
python3 scripts/validate_repo.py              # should print: "ok": true, "errors": []
```

---

## Commit message

```
feat: v2.1.0-governed — v11.3 wave5 promotion at 0.9465

- arc_core/context_window_manager.py (trim-from-middle, SHA-256 receipts)
- arc_core/intent_receipt_engine.py (7-intent lifecycle-gated receipts)
- +165 SFT exemplar records across 7 packs (v6 reflection/compliance/planning,
  v11 continuity/intelligence/surgical/precision)
- 4 pipeline bugs fixed: calibration_error default, incumbent flag selection,
  rubric prefix strip, full_benchmark_v6 profile registration
- Floor model updated: 9 capabilities guarded, overall floor 0.9465
- 10 new benchmark capabilities, all above floor

Closes v11 wave5 cycle. Incumbent: arc_governed_v11_3_wave5.
Prior incumbent: arc_governed_v10_wave4 (0.9237).
```

---

## Scoreboard lineage reference

| Model | Score | Decision |
|---|---|---|
| arc_governed_v1 | 0.6122 | promote |
| arc_governed_v2 | 0.6247 | promote |
| arc_governed_v3 | 0.6128 | archive_only |
| arc_governed_v4 | 0.7128 | promote |
| arc_governed_v5 | 0.7169 | promote |
| arc_governed_v6 | 0.7169 | archive_only |
| arc_governed_v6_conversation | 0.7333 | promote |
| arc_governed_v10_wave4 | 0.9237 | promote (superseded) |
| arc_governed_v11_wave5 | 0.8981 | archive_only |
| arc_governed_v11_2_wave5 | 0.9349 | promote (superseded) |
| **arc_governed_v11_3_wave5** | **0.9465** | **promote ★ INCUMBENT** |


---

## Complete package — everything worked on this session

This package now contains everything. Run in this order:

```bash
cd /path/to/ARC-Neuron-LLMBuilder

# Step 1: Copy all new files
cp /path/to/arc_v11_dropin/arc_core/context_window_manager.py  arc_core/
cp /path/to/arc_v11_dropin/arc_core/intent_receipt_engine.py   arc_core/
cp /path/to/arc_v11_dropin/datasets/distillation_sft/*.jsonl   datasets/distillation_sft/
cp /path/to/arc_v11_dropin/configs/stack/regression_floor.json configs/stack/

# Step 2: Run the auto-patcher (applies all 4 bug fixes + gitignore + scoreboard)
python3 /path/to/arc_v11_dropin/auto_apply.py

# Step 3: Build the v11.3 exemplar model from v10_wave4 base + SFT packs
python3 /path/to/arc_v11_dropin/build_v11_3_exemplar.py

# Step 4: Verify
python3 arc_core/context_window_manager.py    # → All self-tests passed.
python3 arc_core/intent_receipt_engine.py     # → All self-tests passed.
python3 -m pytest tests/ -q                   # → 136 passed
python3 scripts/validate_repo.py              # → ok: true, errors: []
```

If `validate_repo.py` fails with "missing required file: .env.direct-runtime.example",
run: `cp env.direct-runtime.example .env.direct-runtime.example`
(auto_apply.py does this automatically if env.direct-runtime.example exists)

### After verification — full promotion cycle

```bash
# Benchmark v11.3
python3 scripts/execution/run_model_benchmarks.py \
  --adapter exemplar \
  --artifact exports/candidates/arc_governed_v11_3_wave5/exemplar_train/exemplar_model.json \
  --prompt-profile full_benchmark_v6 \
  --output results/v11_3_benchmark_outputs.jsonl

# Score
python3 scripts/execution/score_benchmark_outputs.py \
  --input results/v11_3_benchmark_outputs.jsonl \
  --output results/v11_3_benchmark_scored.json

# Gate v2 (should promote at 0.9465)
python3 scripts/execution/promote_candidate.py \
  --scored results/v11_3_benchmark_scored.json \
  --model-name arc_governed_v11_3_wave5 \
  --candidate arc_governed_v11_3_wave5
```

Expected gate output:
```json
{"ok": true, "promoted": true, "decision": "promote",
 "overall_weighted_score": 0.9465, "regression_violations": []}
```
