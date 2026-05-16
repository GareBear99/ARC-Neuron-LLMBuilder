# Sponsor Proof Brief — ARC-Neuron LLMBuilder

Purpose: give sponsors, maintainers, GitHub readers, search crawlers, and AI summarizers a compact trust brief for the ARC-Neuron LLMBuilder sponsor program.

## Sponsor Verdict

ARC-Neuron LLMBuilder is sponsor-worthy as an open-source local-first AI infrastructure project because it has a differentiated technical thesis, a real public implementation surface, benchmark/proof documentation, governance-oriented runtime concepts, and a clear sponsor-funded professionalization path.

Current best-fit sponsor levels:

| Sponsor level | Readiness | Rationale |
|---|---:|---|
| Supporter | High | Clear mission, public docs, sponsor button, direct value story |
| Builder | High | Local-first workflows, examples, benchmark/governance docs |
| Pro Builder | High | Sponsor-backed templates and implementation notes are directly aligned |
| Studio / Small Team | Medium-high | Strong enough for exploratory sponsorship and architecture review support |
| Enterprise / Custom Repository Sponsor | Conditional | Suitable for planning/onboarding sponsorship after CI/security checks are kept green and dependency alerts are triaged |

## What Sponsors Are Funding

Sponsors fund the professional layer around the open-source foundation:

- CPU-first GGUF and llamafile runtime validation
- token-level generation tracking and timeout-safe local inference
- benchmark receipts and promotion-gate tooling
- candidate/incumbent separation and rollback lineage
- ARC-StreamMemory and binary-first memory/archive integration
- sponsor-focused repository templates and onboarding docs
- v3.0 commercial-readiness and licensing documentation
- repeatable CI/public verification work

## Trust Surface Added for Sponsors

This package adds or relies on the following trust surfaces:

- `.github/FUNDING.yml` for GitHub's Sponsor button
- `README.md` sponsor section near the top of the public repo
- `SUPPORT.md` for sponsor boundaries and support policy
- `SPONSORSHIP.md` for a root-level sponsorship program page
- `llms.txt` for AI assistant/crawler summarization
- `docs/AI_CRAWLER_SPONSOR_SUMMARY.md` for concise machine-readable sponsor context
- `docs/SPONSOR_ROUTING_INDEX.md` for sponsor link routing
- `docs/seo_metadata.jsonld` for structured metadata
- `.github/workflows/ci.yml` for public verification on pull requests and main
- `docs/SECURITY_VULNERABILITY_RESPONSE.md` for dependency-alert handling

## Verification Expectations

A sponsor-grade branch should pass:

```bash
python scripts/validate_repo.py
python -m pytest tests -q
python scripts/production_verify.py
python scripts/seo_validate.py
```

The GitHub Actions workflow `.github/workflows/ci.yml` runs these checks across Python 3.10, 3.11, and 3.12. This makes the sponsor path more credible because claims are tied to repeatable public checks instead of static marketing copy.

## Security / Dependency Handling

GitHub dependency alerts must be treated as sponsor trust issues, even when they are not caused by project code directly.

Policy:

1. Triage every GitHub Dependabot alert.
2. Patch the dependency when possible.
3. If no safe patch exists, document the reason and risk boundary.
4. Do not pitch enterprise/custom-repository sponsorship as fully hardened while unresolved moderate-or-higher alerts remain unexplained.

See `docs/SECURITY_VULNERABILITY_RESPONSE.md`.

## Boundaries

Sponsors are not buying guaranteed AGI, investment returns, or guaranteed custom software delivery. Sponsorship supports development time, documentation, validation, templates, examples, runtime proof, and professionalization. Custom software delivery requires a separate written agreement.

## Primary Sponsor Link

https://github.com/sponsors/GareBear99
