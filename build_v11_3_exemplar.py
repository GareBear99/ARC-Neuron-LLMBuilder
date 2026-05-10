#!/usr/bin/env python3
"""
build_v11_3_exemplar.py — Run from repo root after copying SFT packs.
Merges v10_wave4 base (669 records) + 7 v11 SFT packs (165 records)
into the v11.3 exemplar model (834 records total).

Usage:
    cd /path/to/ARC-Neuron-LLMBuilder
    python3 /path/to/arc_v11_dropin/build_v11_3_exemplar.py
"""
import json, pathlib, re, datetime, sys

ROOT = pathlib.Path.cwd()

def tokenize(text):
    return re.findall(r'[a-zA-Z0-9_]+', text.lower())

# Load v10_wave4 base
v10_path = ROOT / 'exports/candidates/arc_governed_v10_wave4/exemplar_train/exemplar_model.json'
if not v10_path.exists():
    print(f"ERROR: {v10_path} not found.")
    print("The v10_wave4 model must exist in your repo before running this script.")
    sys.exit(1)

v10 = json.load(v10_path.open())
base_records = v10['records']
print(f"v10_wave4 base: {len(base_records)} records")

# All 7 SFT packs
packs = [
    'datasets/distillation_sft/v6_reflection_sft.jsonl',
    'datasets/distillation_sft/v6_deterministic_compliance_sft.jsonl',
    'datasets/distillation_sft/v6_planning_sft.jsonl',
    'datasets/distillation_sft/v11_continuity_sft.jsonl',
    'datasets/distillation_sft/v11_intelligence_sft.jsonl',
    'datasets/distillation_sft/v11_surgical_sft.jsonl',
    'datasets/distillation_sft/v11_precision_sft.jsonl',
]

new_records, pack_counts = [], {}
for pack_path in packs:
    p = ROOT / pack_path
    if not p.exists():
        print(f"  MISSING: {pack_path} — copy from arc_v11_dropin first")
        continue
    count = 0
    for line in p.read_text().strip().splitlines():
        if not line.strip(): continue
        r = json.loads(line)
        new_records.append({
            'source_repo':  'ARC-Neuron-LLMBuilder',
            'source_file':  p.name,
            'capability':   r.get('capability', 'generic'),
            'domain':       r.get('domain', 'general'),
            'prompt':       r['prompt'],
            'prompt_tokens':tokenize(r['prompt']),
            'target':       r['target'],
        })
        count += 1
    pack_counts[p.name] = count
    print(f"  {p.name}: +{count}")

all_records = base_records + new_records
out = {
    'model_type':   'local_exemplar',
    'candidate_id': 'arc_governed_v11_3_wave5',
    'record_count': len(all_records),
    'built_at':     datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'base_model':   'arc_governed_v10_wave4',
    'sft_packs':    list(pack_counts.keys()),
    'records':      all_records,
}

out_dir = ROOT / 'exports/candidates/arc_governed_v11_3_wave5/exemplar_train'
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / 'exemplar_model.json'
out_path.write_text(json.dumps(out, indent=2))
print(f"\nv11.3 exemplar model built: {len(all_records)} records")
print(f"Written to: {out_path}")
print()
print("Next: run the benchmark")
print("  python3 scripts/execution/run_model_benchmarks.py \\")
print("    --adapter exemplar \\")
print("    --artifact exports/candidates/arc_governed_v11_3_wave5/exemplar_train/exemplar_model.json \\")
print("    --prompt-profile full_benchmark_v6 \\")
print("    --output results/v11_3_benchmark_outputs.jsonl")
