# Security Policy

## Supported versions

| Version | Status | Support |
|---|---|---|
| v1.0.0-governed | **current** | ✅ security fixes |
| v0.3.x alpha | superseded | ❌ upgrade recommended |
| < v0.3 | legacy | ❌ not supported |

## Reporting a vulnerability

Please report suspected vulnerabilities **privately** via GitHub Security Advisories:

**https://github.com/GareBear99/ARC-Neuron-LLMBuilder/security/advisories/new**

Do not open a public issue for security matters.

## What qualifies as a security issue

- **Unsafe command execution** — any path through an adapter that executes user-supplied content as shell, python, or other code.
- **Adapter secret leakage** — API keys, tokens, or local credentials surfaced in receipts, logs, Arc-RAR bundles, or Omnibinary events.
- **Path traversal** — in bundle extraction, capsule handling, attachment tooling, or any I/O path that takes a user-controlled path component.
- **Malformed input breaks validation** — inputs that cause the scorer, promotion gate, or benchmark task loader to skip validation or silently accept invalid data.
- **Omnibinary integrity violations** — ways to write to the ledger that bypass the SHA-256 verification path or leave the index in an inconsistent state that `verify()` does not catch.
- **Gate v2 bypass** — any way to make `promote_candidate.py` accept a candidate that should have been rejected by the hard-reject floor, the floor model, or a regression ceiling.
- **Non-promotable adapter bypass** — any way for the `heuristic` or `echo` adapter to become an incumbent.
- **Receipt forgery** — any way to produce a promotion receipt that references a state that did not actually exist.

## What does NOT qualify

- Gate v2 correctly rejecting your candidate. If the decision is accurate given the scores, that is the gate working as designed. File a "⚖️ Gate behavior report" issue (public) instead.
- Low scores from a small model on complex benchmarks. This is expected behavior at the Tiny/Small tier.
- Requests for new adapters, new benchmarks, or new capability lanes. File a feature request.

## Response process

1. We acknowledge within 72 hours.
2. We triage and assign a severity (Critical / High / Medium / Low).
3. We develop and test a fix in a private branch.
4. We publish a coordinated advisory with credit (unless you prefer anonymity) and a patched release.
5. We backport fixes to supported versions only.

## Scope — cross-repo

Vulnerabilities that cross ARC ecosystem repos (ARC-Core, Cleanroom Runtime, Cognition Core, Language Module, OmniBinary, Arc-RAR) should be reported against the home repo of the primary responsibility:

- Receipt signing / event authority → [ARC-Core](https://github.com/GareBear99/ARC-Core/security/advisories/new)
- Deterministic execution boundaries → [arc-lucifer-cleanroom-runtime](https://github.com/GareBear99/arc-lucifer-cleanroom-runtime/security/advisories/new)
- Binary ledger / runtime-event substrate → [omnibinary-runtime](https://github.com/GareBear99/omnibinary-runtime/security/advisories/new)
- Archive bundle format → [Arc-RAR](https://github.com/GareBear99/Arc-RAR/security/advisories/new)
- Language module governance → [arc-language-module](https://github.com/GareBear99/arc-language-module/security/advisories/new)
- Cognition build/promote flow → [arc-cognition-core](https://github.com/GareBear99/arc-cognition-core/security/advisories/new)
- Canonical pipeline / gate / local governance → this repo

If in doubt, file in this repo and we will route.

## Secrets and key management

- **`.github/FUNDING.yml`** is the only intentional identity surface. It contains no secrets.
- **`scripts/ops/bootstrap_keys.py`** is the single source of truth for generating runtime secrets.
- **`.gitignore`** excludes `*.key`, `*.pem`, `*.p12`, `**/data/keys/*`, SQLite runtime DBs, and large binary artifacts.
- **Demo keys in release zips** are placeholders and should be rotated with `bootstrap_keys.py --force` on first clone.

## Dependencies

The runtime core depends on: `PyYAML`, `jsonschema`, `requests`, and (for training) `torch` + `numpy`. Vulnerabilities in upstream packages are tracked via GitHub's Dependabot alerts on this repo.


## Dependency Alert / Sponsor Trust Response

GitHub Dependabot alerts are handled as sponsor-trust issues. Moderate-or-higher dependency alerts should be resolved or documented before the project is pitched as enterprise-hardened.

See: `docs/SECURITY_VULNERABILITY_RESPONSE.md`
