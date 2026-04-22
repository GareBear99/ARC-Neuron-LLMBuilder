# Support

## Before you ask

Most questions are already answered in one of these documents:

- **[README.md](./README.md)** — overview and current state
- **[QUICKSTART.md](./QUICKSTART.md)** — 10-minute tour
- **[USAGE.md](./USAGE.md)** — complete command reference
- **[FAQ.md](./FAQ.md)** — 20+ searchable questions
- **[EXAMPLES.md](./EXAMPLES.md)** — 10 runnable recipes
- **[GLOSSARY.md](./GLOSSARY.md)** — every ARC-specific term
- **[PROOF.md](./PROOF.md)** — every claim with a verification command

## First-run diagnostics

```bash
python3 -m pytest tests/ -q                   # should report 87 passed
python3 scripts/ops/benchmark_omnibinary.py   # Omnibinary PASS
python3 scripts/ops/demo_proof_workflow.py    # 9/9 steps green
make verify-store                             # Omnibinary live-store integrity
```

If any of these fail, include the output when you ask for help.

## Where to ask

| Channel | Use for |
|---|---|
| [💬 Discussions](https://github.com/GareBear99/ARC-Neuron-LLMBuilder/discussions) | General questions, show-and-tell, governed-cycle experiments, architectural discussion |
| [🐛 Bug report](./.github/ISSUE_TEMPLATE/01_bug_report.yml) | Something is broken |
| [✨ Feature request](./.github/ISSUE_TEMPLATE/02_feature_request.yml) | Propose a new capability |
| [⚖️ Gate behavior report](./.github/ISSUE_TEMPLATE/03_gate_behavior.yml) | Gate v2 made a decision you think is wrong |
| [📊 Benchmark proposal](./.github/ISSUE_TEMPLATE/04_benchmark_proposal.yml) | Contribute new benchmark tasks |
| [📚 Docs issue](./.github/ISSUE_TEMPLATE/05_docs.yml) | A doc is wrong / missing / confusing |
| [🔒 Security advisory](https://github.com/GareBear99/ARC-Neuron-LLMBuilder/security/advisories/new) | Private disclosure of a vulnerability |

## Cross-repo routing

If your question or issue really belongs to a sibling repo, please file there instead:

- Event / receipt / authority issues → [ARC-Core](https://github.com/GareBear99/ARC-Core)
- Deterministic execution kernel → [arc-lucifer-cleanroom-runtime](https://github.com/GareBear99/arc-lucifer-cleanroom-runtime)
- Cognition build doctrine → [arc-cognition-core](https://github.com/GareBear99/arc-cognition-core)
- Language / lexical truth → [arc-language-module](https://github.com/GareBear99/arc-language-module)
- Binary mirror / runtime ledger → [omnibinary-runtime](https://github.com/GareBear99/omnibinary-runtime)
- Archive / rollback bundles → [Arc-RAR](https://github.com/GareBear99/Arc-RAR)

In doubt? File here and we'll route. See [ECOSYSTEM.md](./ECOSYSTEM.md) for the full role contract.

## Response expectations

- Issues and Discussions posts are best-effort. No SLA.
- Security advisories: acknowledged within 72 hours per [SECURITY.md](./SECURITY.md).
- Priority is given to:
  - Bug reports with full reproduction steps and tests.
  - Gate behavior reports with the full `reports/promotion_decision.json` attached.
  - PRs that preserve all ten governance invariants.

## Supporting the project

If you rely on ARC-Neuron LLMBuilder or any of the seven ARC ecosystem repos in your work:

**[github.com/sponsors/GareBear99](https://github.com/sponsors/GareBear99)**

Sponsorship funds maintenance time across the whole ecosystem, not just this repo.
