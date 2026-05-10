#!/usr/bin/env python3
"""
scoreboard_patch.py — standalone scoreboard migration for v2.1.0.
Adds calibration_error to all existing entries and marks v11_3 as incumbent.
Run from repo root: python3 /path/to/arc_v11_dropin/scoreboard_patch.py
"""
import json, pathlib, sys

ROOT = pathlib.Path.cwd()
sb_path = ROOT / 'results/scoreboard.json'
if not sb_path.exists():
    print(f"ERROR: {sb_path} not found.")
    sys.exit(1)

sb = json.load(sb_path.open())
changed = 0

# Add calibration_error to all entries that are missing it
for m in sb.get('models', []):
    if 'calibration' in m and 'calibration_error' not in m:
        m['calibration_error'] = round(1.0 - m['calibration'], 4)
        changed += 1

# If v11_3_wave5 exists in scoreboard, mark as incumbent
v11_3 = next((m for m in sb.get('models', []) if 'v11_3_wave5' in m.get('model', '')), None)
if v11_3:
    for m in sb.get('models', []):
        if 'v11_3_wave5' in m.get('model', ''):
            m['incumbent'] = True
        else:
            if m.get('incumbent'):
                m['incumbent'] = False
                m['superseded_by'] = 'arc_governed_v11_3_wave5'
                changed += 1
    changed += 1
else:
    print("NOTE: arc_governed_v11_3_wave5 not yet in scoreboard.")
    print("      It will be added when you run promote_candidate.py after benchmarking.")

json.dump(sb, sb_path.open('w'), indent=2)
print(f"Scoreboard patched: {changed} change(s) applied")
inc = next((m for m in sb.get('models',[]) if m.get('incumbent')), None)
print(f"Incumbent: {inc['model'] if inc else 'none'}")
