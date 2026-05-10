# ARC-Neuron 3.0 Roadmap Integration Plan

Status: professional production roadmap for the protected full base-model release.

## Release doctrine

- 1.0 remains under the license it already shipped with.
- There is no formal public 2.0 release.
- Work between 1.0 and 3.0 is transitional development work.
- 3.0 is the protected full roadmap/base-model release.
- 3.0 must ship with manifests, receipts, connected datasets, scoring evidence, and a more suitable license that prevents unrestricted resale/repackaging.

## 3.0 goals

ARC-Neuron 3.0 should become a governed local cognition lab that can:

1. ingest approved datasets,
2. preserve source and transform lineage,
3. train candidate brains,
4. benchmark them against protected floors,
5. promote only evidence-backed improvements,
6. archive rejected candidates without destroying their evidence,
7. run locally with direct GGUF/runtime paths when available,
8. explain why a candidate changed.

## Required production gates

### Gate A — source governance

Every source must have:

- dataset card or source note
- license classification
- allowed-use classification
- PII/sensitive-data classification
- content hash
- ingestion date
- approval scope

### Gate B — candidate isolation

New dataset families enter `candidate_v2` or `candidate_v3`, not the incumbent lane.

### Gate C — benchmark replay

Promotion evidence must be reproducible from files shipped in the repo or release artifact.

### Gate D — floor protection

A candidate cannot promote if it improves new skills while weakening protected old floors.

### Gate E — archive bundle

A 3.0 release must include an archive pointer or bundle manifest for:

- source manifests
- dataset manifests
- model/candidate manifests
- benchmark outputs
- scored outputs
- promotion report
- scoreboard update
- rollback pointer

## Immediate next steps

1. Freeze current v10_wave4 incumbent as the pre-3.0 reference.
2. Mark v11.3 as candidate/staging unless reproducible promotion evidence is regenerated.
3. Add v2-class candidate isolation policy.
4. Add dataset manifest templates.
5. Build a dataset acquisition matrix.
6. Add license transition notice.
7. Run validation and record the result.
8. Only update scoreboard when promotion is reproduced.

