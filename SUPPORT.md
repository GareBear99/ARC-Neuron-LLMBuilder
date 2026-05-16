# Support ARC-Neuron LLMBuilder

ARC-Neuron LLMBuilder is a local-first AI lifecycle framework for benchmark receipts, model promotion gates, rollback lineage, reproducible runtime evidence, and governed small-model improvement.

## Sponsor Link

**GitHub Sponsors:** https://github.com/sponsors/GareBear99

## Why Sponsor This Project

This is not a coffee-donation repo. Sponsorship funds the professionalization layer around a local-first AI software factory:

- CPU-first GGUF / llamafile runtime testing
- token-level generation tracking and timeout-safe local inference
- benchmark receipt tooling
- candidate/incumbent promotion gates
- rollback lineage and reproducible release evidence
- ARC-StreamMemory integration
- binary-first memory/archive research
- sponsor-backed custom repository templates
- v3.0 commercialization and licensing-readiness documentation

## Sponsor Program

| Tier | Intended sponsor | What it supports |
|---|---|---|
| Supporter | Users who want the work to keep shipping | Maintenance, documentation, examples, and release validation |
| Builder | Solo developers using local-first AI tooling | Early implementation notes, sponsor updates, and priority issue visibility when feasible |
| Pro Builder | Serious builders using ARC workflows | Sponsor-focused repository templates, advanced setup notes, and roadmap input |
| Studio / Small Team | Teams exploring local-first AI infrastructure | Private checklists, custom repository template guidance, and documentation priority |
| Enterprise / Custom Repository Sponsor | Organizations needing onboarding or planning | Custom repository platform planning, commercial-readiness notes, and architecture support |

## Boundaries

Sponsors fund development time, documentation, templates, examples, runtime validation, packaging, and roadmap work. Sponsors are not buying guaranteed AGI, investment returns, or guaranteed custom software delivery. Custom software delivery requires a separate written agreement.

## Sponsor Conversion Links

- GitHub Sponsors: https://github.com/sponsors/GareBear99
- Sponsor platform setup: `docs/GITHUB_SPONSORS_PLATFORM_SETUP.md`
- Tier copy drafts: `sponsor_templates/SPONSOR_TIERS.md`
- AI/crawler summary: `docs/AI_CRAWLER_SPONSOR_SUMMARY.md`


## Sponsor Trust / Verification

Sponsor-facing claims should stay connected to public verification artifacts:

- `docs/SPONSOR_PROOF_BRIEF.md`
- `.github/workflows/ci.yml`
- `docs/ENTERPRISE_SPONSOR_READINESS.md`
- `docs/SECURITY_VULNERABILITY_RESPONSE.md`
- `docs/AI_CRAWLER_SPONSOR_SUMMARY.md`

Recommended local verification before sponsor-facing releases:

```bash
python scripts/validate_repo.py
python -m pytest tests -q
python scripts/production_verify.py
python scripts/seo_validate.py
```

Enterprise/custom-repository sponsorship should be framed as planning, onboarding, documentation, and architecture support unless a separate written delivery agreement exists.
