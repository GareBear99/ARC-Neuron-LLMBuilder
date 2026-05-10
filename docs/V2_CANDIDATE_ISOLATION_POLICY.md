# v2 Candidate Isolation Policy

New weights, new datasets, new adapters, and new support-language data must not overwrite the incumbent lane.

## Rule

External or newly mixed data enters a candidate class first. It must remain separate from the public incumbent until it passes benchmark, floor, provenance, and rollback checks.

## Why

A dataset can improve tone while damaging planning. A new adapter can improve speed while damaging refusal correctness. A model can improve benchmark average while breaking a protected capability.

ARC-Neuron treats those as candidate events, not automatic upgrades.

## Required checks

- dataset/source manifest;
- license record;
- raw and transformed hashes;
- candidate namespace;
- benchmark output;
- scored report;
- comparison against incumbent;
- promotion/rejection receipt;
- rollback path.
