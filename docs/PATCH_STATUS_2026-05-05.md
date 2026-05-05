# Patch Status — 2026-05-05

This package was updated after a line/file/function audit pass.

## Fixed

- Added `.env.direct-runtime.example` so `python3 scripts/validate_repo.py` passes from a fresh ZIP.
- Changed PyPI classifier from `Development Status :: 5 - Production/Stable` to `Development Status :: 3 - Alpha`.
- Bumped package version from `1.0.0` to `1.0.1`.
- Hardened `scorers/rubric.py` so `avoids_false_certainty` only credits substantial answers with sentence structure, preventing one-word answers from earning calibration credit.
- Fixed unsafe JSON shell quoting in `scripts/production/release_flagship_event.sh`.
- Added generated-output directories to the native-training corpus skip list so training smoke runs do not ingest prior exports/reports.
- Added `ARC_NATIVE_SMOKE_FAST=1` smoke path for artifact-contract tests; normal operator training remains unchanged unless that explicit environment variable is set.
- Hardened PyTorch smoke-test execution against constrained OpenMP/PyTorch thread-pool behavior.

## Verified in this package

```bash
python3 scripts/validate_repo.py
bash -n scripts/production/release_flagship_event.sh
python3 -m py_compile scorers/rubric.py scripts/training/train_arc_native_candidate.py tests/test_arc_core_fixes.py
```

The repository validator passes with no errors. Full PyTorch test execution can still depend on local torch/OpenMP behavior, so use the validator plus targeted smoke tests as the release gate on older CPUs.
