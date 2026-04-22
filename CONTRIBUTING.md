# Contributing to ARC-Neuron LLMBuilder

Thank you for considering a contribution. This repo is part of the **seven-repo ARC ecosystem** where each repo owns a frozen role. Contributions that preserve those boundaries land fast. Contributions that try to cross them rarely land at all.

## Before you start

1. Read [ARCHITECTURE.md](./ARCHITECTURE.md) to understand the four frozen roles.
2. Read [GOVERNANCE_DOCTRINE.md](./GOVERNANCE_DOCTRINE.md) — in particular the **ten governance invariants**.
3. Read [ECOSYSTEM.md](./ECOSYSTEM.md) to see which sibling repo really owns the change you have in mind.
4. Browse [open issues](https://github.com/GareBear99/ARC-Neuron-LLMBuilder/issues) and [Discussions](https://github.com/GareBear99/ARC-Neuron-LLMBuilder/discussions) to avoid duplicate work.

## Setup

```bash
git clone https://github.com/GareBear99/ARC-Neuron-LLMBuilder.git
cd ARC-Neuron-LLMBuilder

python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt "torch>=2.0" "numpy<2.0"
python3 scripts/ops/bootstrap_keys.py

python3 -m pytest tests/ -q         # must say: 87 passed
```

## Before you open a PR

Run all of these locally. Every one must pass.

```bash
python3 -m pytest tests/ -q                   # full test suite
python3 scripts/validate_repo.py              # repo structure validation
python3 scripts/ops/benchmark_omnibinary.py   # Omnibinary perf + fidelity
python3 scripts/ops/demo_proof_workflow.py    # 9-step end-to-end proof
make verify-store                             # Omnibinary live store integrity
```

If your PR touches the gate, floor model, or scoring, also run:

```bash
python3 scripts/ops/run_n_cycles.py --cycles 3 --tier tiny --steps 30
# must report: Verdict: ✓ STABLE
```

Attach the output of any that are relevant to your change.

## PR checklist (the template enforces this)

- [ ] All ten **governance invariants** in [GOVERNANCE_DOCTRINE.md](./GOVERNANCE_DOCTRINE.md) are preserved. If any is redefined, it is called out explicitly and the CHANGELOG is updated.
- [ ] `python3 -m pytest tests/ -q` passes locally.
- [ ] If this changes scoring or gate behavior, the 3-cycle stability proof is attached.
- [ ] If this affects Omnibinary or Arc-RAR formats, `benchmark_omnibinary.py` numbers and the demo proof workflow output are attached.
- [ ] New public APIs have tests in `tests/`.
- [ ] README / ARCHITECTURE / GOVERNANCE_DOCTRINE / QUICKSTART / USAGE / FAQ / GLOSSARY / ROADMAP are updated as needed.
- [ ] CHANGELOG entry added.

## Commit style

- Imperative mood in the subject line: "Add X", "Fix Y", "Harden Z".
- Wrap the body at ~72 columns.
- Include evidence in the body when the change affects governance: promotion receipt paths, scoreboard diffs, repeatability verdicts.
- Co-authors welcome: use the standard `Co-authored-by:` trailer.

Example:
```
gate: correctly archive ties instead of clearing incumbent flag

Previously, a candidate that tied the incumbent on overall weighted score
would clear the incumbent flag in the scoreboard update step, leaving the
system with no declared incumbent after a streak of archive-only cycles.

Fix: clear incumbent flags only when `promoted == True`. Archive-only and
reject decisions leave the incumbent untouched.

Evidence:
  - 5-cycle repeatability run now correctly preserves v5 as incumbent
    across all five archive-only decisions (reports/repeatability_*.json).
  - Added test_tie_archive_preserves_incumbent to test_omnibinary_pipeline_promotion.py.

Preserves all ten governance invariants.
```

## Code style

- Python 3.10+ type hints on all public functions.
- `from __future__ import annotations` at the top of every module.
- No wildcard imports.
- Single-line JSON for subprocess-facing scripts (see `train_arc_native_candidate.py` pattern) — downstream parsers expect compact output.
- No cross-imports between `adapters/` and `runtime/` that create cycles.
- Scorers stay deterministic on the same input.

## Dataset and benchmark contributions

- New benchmark tasks must conform to [specs/benchmark_schema_v2.yaml](./specs/benchmark_schema_v2.yaml).
- Every task needs `id`, `capability`, `domain`, `difficulty`, `prompt`, `reference`, `scoring`, `tags`.
- Adding a new capability bucket requires a corresponding entry in `scorers/rubric.py`.
- File via the [📊 Benchmark contribution proposal](./.github/ISSUE_TEMPLATE/04_benchmark_proposal.yml) issue template.

## Cross-repo changes

If your change affects more than one of the seven ARC repos:

1. Open a tracking issue in **this repo** (the integration surface).
2. Link it to per-repo sub-issues in each affected sibling.
3. Keep role boundaries intact — do not cross-own logic between repos.
4. Preserve receipts. Any cross-repo state change must be addressable after the fact.

## Code of Conduct

Be respectful and constructive. See [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md).

## License

By contributing, you agree that your contributions will be licensed under the MIT License, the same as the rest of the project. See [LICENSE](./LICENSE).

## Questions

- [💬 GitHub Discussions](https://github.com/GareBear99/ARC-Neuron-LLMBuilder/discussions) for general questions.
- [SUPPORT.md](./SUPPORT.md) for routing to the right channel.
- [github.com/sponsors/GareBear99](https://github.com/sponsors/GareBear99) if you want to fund the work.
