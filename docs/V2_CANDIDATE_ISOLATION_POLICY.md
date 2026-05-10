# v2-Class Candidate Isolation Policy

Status: required policy before broad dataset expansion or 3.0 roadmap integration.

## Purpose

The current promoted lineage must not be polluted by experimental weights, new dataset families, mental-health/support-language data, synthetic data, external model outputs, or license-unclear corpora.

All such material enters a separate v2-class candidate lane until it proves safe.

## Model lanes

```text
floor_model/          known-safe protected baseline
incumbent_model/      current promoted model
candidate_v1/         same dataset class as incumbent
candidate_v2/         new dataset family or new objective class
candidate_v3/         3.0 integration candidates with full manifests
quarantine/           untrusted, unclear, or rejected material
```

## Promotion rule

A v2 candidate may only challenge the incumbent after it:

1. passes schema validation,
2. has complete dataset manifests,
3. has license classification for all sources,
4. improves one or more target capabilities,
5. does not breach any protected incumbent floor,
6. produces an archiveable promotion/rejection receipt,
7. has a rollback pointer.

## Protected floors

At minimum, the following floors are protected from regression:

- planning
- paraphrase stability
- instruction following
- continuity
- state evidence
- runtime reasoning
- refusal correctness
- license awareness
- provenance awareness
- ARC doctrine retention

## Default result for experimental data

Experimental data is `archive_only` unless explicitly promoted by a gate.

