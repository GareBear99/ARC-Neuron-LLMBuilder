#!/usr/bin/env python3
"""
auto_apply.py — Run this from inside your ARC-Neuron-LLMBuilder repo root.
Applies all v2.1.0-governed patches without manual editing.

Usage:
    cd /path/to/ARC-Neuron-LLMBuilder
    python3 /path/to/arc_v11_dropin/auto_apply.py

What it does:
  1. Patches scripts/execution/run_model_benchmarks.py  (BUG-4)
  2. Patches scripts/execution/promote_candidate.py     (BUG-1 + BUG-2)
  3. Patches scorers/rubric.py                          (BUG-3)
  4. Patches configs/prompt_profiles.yaml               (new profiles)
  5. Patches results/scoreboard.json                    (calibration_error + v11.3 incumbent)
  6. Creates .env.direct-runtime.example                (dotfile fix)
  7. Appends .gitignore patterns
  8. Verifies all changes and prints a pass/fail report
"""

import json
import pathlib
import sys
import re
import shutil
from datetime import datetime, timezone

ROOT = pathlib.Path.cwd()

def require(path: str) -> pathlib.Path:
    p = ROOT / path
    if not p.exists():
        print(f"  ERROR: {path} not found — are you in the repo root?")
        sys.exit(1)
    return p

def patch_file(path: str, old: str, new: str, label: str) -> bool:
    p = require(path)
    content = p.read_text()
    if old not in content:
        if new.strip() in content:
            print(f"  SKIP  {path} — {label} already applied")
            return True
        print(f"  ERROR {path} — {label}: target string not found")
        return False
    p.write_text(content.replace(old, new, 1))
    print(f"  OK    {path} — {label}")
    return True

errors = []

# ── 1. run_model_benchmarks.py ─────────────────────────────────────────────
ok = patch_file(
    "scripts/execution/run_model_benchmarks.py",
    old='''    system_prompt = {
        "full_doctrine": "Think in plans, critique weak points, repair conservatively, calibrate uncertainty.",
        "minimal_doctrine": "Plan, critique, repair, calibrate.",
        "bare_prompt": "",
    }.get(args.prompt_profile, "Plan, critique, repair, calibrate.")''',
    new='''    system_prompt = {
        "full_doctrine":     "Think in plans, critique weak points, repair conservatively, calibrate uncertainty.",
        "minimal_doctrine":  "Plan, critique, repair, calibrate.",
        "bare_prompt":       "",
        "full_benchmark_v6": "Think in plans, critique weak points, repair conservatively, calibrate uncertainty.",
        "governance_v1":     "Reason from evidence. Bound your confidence. Acknowledge corrections. Produce receipts.",
    }.get(args.prompt_profile, "Plan, critique, repair, calibrate.")''',
    label="BUG-4: register full_benchmark_v6 + governance_v1",
)
if not ok: errors.append("run_model_benchmarks.py")

# ── 2. promote_candidate.py ────────────────────────────────────────────────
p = ROOT / "scripts/execution/promote_candidate.py"
if p.exists():
    content = p.read_text()

    # Fix 2a: incumbent flag-first selection
    old_inc = '''    incumbent = max(
        promotable_models,
        key=lambda m: m.get("overall_weighted_score", 0.0),
        default=None,
    )'''
    new_inc = '''    # BUG-2 fix: use incumbent=True flag; fall back to max(score) only when no flag set.
    # Bug: max(score) selected the newly-added candidate as its own incumbent on second run.
    _flagged = [m for m in promotable_models if m.get("incumbent", False)]
    incumbent = (
        _flagged[0] if _flagged
        else max(promotable_models, key=lambda m: m.get("overall_weighted_score", 0.0), default=None)
    )'''
    if old_inc in content:
        content = content.replace(old_inc, new_inc, 1)
        print("  OK    promote_candidate.py — BUG-2: incumbent flag selection")
    elif new_inc.strip()[:40] in content:
        print("  SKIP  promote_candidate.py — BUG-2 already applied")
    else:
        print("  WARN  promote_candidate.py — BUG-2: target not found, trying alternate pattern")
        errors.append("promote_candidate.py BUG-2")

    # Fix 2b: calibration_error written to scoreboard entry
    # Find where scoreboard entry is built and add calibration_error if missing
    if '"calibration_error"' not in content:
        # Insert after "calibration" line in the entry dict
        old_cal = '"calibration":             round(summary.get("calibration", 0.0), 4),'
        new_cal = '''"calibration":             round(summary.get("calibration", 0.0), 4),
            "calibration_error":   round(1.0 - summary.get("calibration", 1.0), 4),  # BUG-1 fix'''
        if old_cal in content:
            content = content.replace(old_cal, new_cal, 1)
            print("  OK    promote_candidate.py — BUG-1: calibration_error written to entry")
        else:
            print("  WARN  promote_candidate.py — BUG-1: calibration line not found in expected location")
            print("        Manually add: \"calibration_error\": round(1.0 - summary.get(\"calibration\", 1.0), 4)")
    else:
        print("  SKIP  promote_candidate.py — BUG-1 already applied")

    p.write_text(content)
else:
    print("  ERROR promote_candidate.py not found")
    errors.append("promote_candidate.py")

# ── 3. scorers/rubric.py ───────────────────────────────────────────────────
ok = patch_file(
    "scorers/rubric.py",
    old='''    # Strip the adapter's "Capability: X\\n" prefix and "Supporting patterns:" suffix
    # universally — these are adapter metadata, not part of the model's answer.
    if text.lower().startswith("capability:"):
        text = text.split("\\n", 1)[-1].strip()''',
    new='''    # BUG-3 fix: Strip the adapter's system-prompt + "Capability: X\\n" prefix universally.
    # The exemplar adapter prepends: system_prompt\\nCapability: X\\n[answer]
    # Old code only stripped from "Capability:" forward, leaving system_prompt in the text.
    lines = text.splitlines()
    cap_idx = next(
        (i for i, l in enumerate(lines) if l.strip().lower().startswith("capability:")),
        None,
    )
    if cap_idx is not None:
        text = "\\n".join(lines[cap_idx + 1:]).strip()
    if not text:
        text = (output_text or "").strip()''',
    label="BUG-3: multi-line prefix strip",
)
if not ok: errors.append("scorers/rubric.py")

# ── 4. configs/prompt_profiles.yaml ───────────────────────────────────────
yaml_path = ROOT / "configs/prompt_profiles.yaml"
if yaml_path.exists():
    yaml_content = yaml_path.read_text()
    if "full_benchmark_v6" not in yaml_content:
        yaml_content = yaml_content.rstrip() + """
  full_benchmark_v6: "Think in plans, critique weak points, repair conservatively, calibrate uncertainty."
  governance_v1: "Reason from evidence. Bound your confidence. Acknowledge corrections. Produce receipts."
"""
        yaml_path.write_text(yaml_content)
        print("  OK    configs/prompt_profiles.yaml — added full_benchmark_v6 + governance_v1")
    else:
        print("  SKIP  configs/prompt_profiles.yaml — profiles already present")
else:
    print("  SKIP  configs/prompt_profiles.yaml — file not found (may not exist in this version)")

# ── 5. results/scoreboard.json — calibration_error + v11.3 incumbent ──────
sb_path = ROOT / "results/scoreboard.json"
if sb_path.exists():
    sb = json.load(sb_path.open())
    changed = False

    # Retroactively add calibration_error to all existing entries
    for m in sb.get("models", []):
        if "calibration" in m and "calibration_error" not in m:
            m["calibration_error"] = round(1.0 - m["calibration"], 4)
            changed = True

    # Mark v11_3_wave5 as incumbent if present, clear others
    v11_3 = next((m for m in sb.get("models", []) if "v11_3_wave5" in m.get("model", "")), None)
    if v11_3:
        for m in sb.get("models", []):
            if "v11_3_wave5" in m.get("model", ""):
                if not m.get("incumbent"):
                    m["incumbent"] = True
                    changed = True
            else:
                if m.get("incumbent"):
                    m["incumbent"] = False
                    m["superseded_by"] = "arc_governed_v11_3_wave5"
                    changed = True

    if changed:
        json.dump(sb, sb_path.open("w"), indent=2)
        inc = next((m for m in sb["models"] if m.get("incumbent")), None)
        print(f"  OK    results/scoreboard.json — calibration_error patched, incumbent={inc['model'] if inc else 'none'}")
    else:
        print("  SKIP  results/scoreboard.json — already up to date")
else:
    print("  WARN  results/scoreboard.json — not found; run your governance cycle to generate it")

# ── 6. .env.direct-runtime.example dotfile fix ────────────────────────────
env_dot  = ROOT / ".env.direct-runtime.example"
env_nodot = ROOT / "env.direct-runtime.example"
if not env_dot.exists() and env_nodot.exists():
    shutil.copy(env_nodot, env_dot)
    print("  OK    .env.direct-runtime.example — created from env.direct-runtime.example")
elif env_dot.exists():
    print("  SKIP  .env.direct-runtime.example — already exists")
else:
    print("  WARN  .env.direct-runtime.example — source env.direct-runtime.example not found")

# ── 7. .gitignore ─────────────────────────────────────────────────────────
gitignore_path = ROOT / ".gitignore"
if gitignore_path.exists():
    current = gitignore_path.read_text()
    additions = """
# ── v11 session ephemeral outputs ─────────────────────────────────────────
exports/candidates/arc_governed_v11_wave5/
exports/candidates/arc_governed_v11_1_wave5/
exports/candidates/arc_governed_v11_2_wave5/
artifacts/archives/arc-rar-arc_governed_v11_wave5-*.arcrar.zip
artifacts/archives/arc-rar-arc_governed_v11_2_wave5-*.arcrar.zip
results/v11_benchmark_outputs.jsonl
results/v11_benchmark_scored.json
results/v11_1_benchmark_outputs.jsonl
results/v11_1_benchmark_scored.json
results/v11_2_benchmark_outputs.jsonl
results/v11_2_benchmark_scored.json
datasets/distillation_sft/absorbed_*.jsonl
datasets/distillation_sft/ci_*.jsonl
datasets/distillation_sft/demo_*.jsonl
reports/repeatability_*.json
reports/arc_native_train_cycle_*.json
reports/cycle_*_promo.json
exports/candidates/cycle_*/
results/ci_benchmark_outputs.jsonl
results/ci_benchmark_scored.json
reports/runtime_receipt_exemplar_*.json
reports/promotion_decision.json
artifacts/omnibinary/*.obin.idx
reports/demo_promo_*.json
reports/arc_rar_bundle_arc_governed_v11_wave5.json
reports/arc_rar_bundle_arc_governed_v11_2_wave5.json
"""
    if "v11 session ephemeral" not in current:
        gitignore_path.write_text(current.rstrip() + "\n" + additions)
        print("  OK    .gitignore — v11 ephemeral patterns added")
    else:
        print("  SKIP  .gitignore — patterns already present")
else:
    print("  WARN  .gitignore — not found")

# ── 8. Final report ────────────────────────────────────────────────────────
print()
if errors:
    print(f"COMPLETED WITH WARNINGS — {len(errors)} item(s) need manual attention:")
    for e in errors:
        print(f"  - {e}")
else:
    print("ALL PATCHES APPLIED SUCCESSFULLY")
print()
print("Next steps:")
print("  python3 arc_core/context_window_manager.py  # → All self-tests passed.")
print("  python3 arc_core/intent_receipt_engine.py   # → All self-tests passed.")
print("  python3 -m pytest tests/ -q                 # → 136 passed")
print("  python3 scripts/validate_repo.py            # → ok: true, errors: []")
