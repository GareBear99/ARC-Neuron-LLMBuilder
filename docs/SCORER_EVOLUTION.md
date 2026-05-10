# Scorer Evolution and Public Score Rules

ARC-Neuron LLMBuilder treats every score as a versioned measurement, not a timeless headline number.

A candidate score is only directly comparable when all of the following match:

```text
candidate artifact + benchmark manifest + scorer manifest + adapter + prompt profile
```

If any of those change, the score is still useful as provenance, but it belongs to a different measurement generation.

## Current public status

- **Current reproducible incumbent:** `arc_governed_v10_wave4`
- **Locked incumbent score:** `0.9237`
- **Locked incumbent scorer generation:** `v6-final-post-audit`
- **Locked incumbent benchmark version:** `seed_tasks_v3_audited`
- **Current validator benchmark inventory:** `168` tasks
- **Current dataset inventory:** `120` records
- **Current staged public verification target:** `136` tests

The current public benchmark inventory is larger than older proof-era inventories because new scorer lanes and root JSONL shards were added after earlier benchmark proofs. That expansion strengthens coverage, but it also means older and newer headline scores should not be compared without manifest locking.

## Historical proof generations

| Generation | Purpose | Comparison rule |
|---|---|---|
| v1.0.0-governed | Original governance proof, Gate v2 states, Omnibinary receipts, Arc-RAR bundles | Historical only; compare inside original proof bundle |
| v2.0.0-audited / v10 | Post-audit incumbent proof after benchmark/rubric remediation | Compare only inside the locked v10 scorer/benchmark generation |
| v2 candidate / 3.0 preparation | Candidate-isolated dataset and scorer expansion work | Compare only after a new candidate is trained, scored, and promoted through Gate v2 with matching manifests |

## Why added scorers matter

The expanded scorer surface reduces one-dimensional benchmark gaming. Instead of rewarding a single doctrine-shaped answer style, the system checks more behavior families, including:

- reasoning
- planning
- critique
- repair
- calibration
- compression
- continuity
- reflection
- instruction following
- English understanding
- out-of-domain behavior
- paraphrase stability
- quantization retention
- archive/runtime/state evidence
- deterministic compliance
- memory continuity

## Reviewer rule

When reviewing a result, require the receipt or report to identify:

```json
{
  "candidate_id": "...",
  "scorer_version": "...",
  "benchmark_version": "...",
  "adapter": "...",
  "prompt_profile": "...",
  "artifact_path": "...",
  "dataset_record_count": 120,
  "benchmark_task_count": 168
}
```

A result missing those fields should be treated as incomplete evidence, even if the score itself looks high.

## Public wording

Use this wording for public summaries:

> ARC-Neuron LLMBuilder is a scorer-expanded local AI governance lab. It builds, benchmarks, scores, gates, archives, and rolls back candidate models while preserving the evidence trail. Historic scores are preserved as provenance; current comparisons require matching scorer, benchmark, adapter, prompt profile, and candidate artifact manifests.
