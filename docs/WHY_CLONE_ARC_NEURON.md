# Why Clone ARC-Neuron LLMBuilder

ARC-Neuron LLMBuilder is a local-first AI build lab for people who care about reproducible model growth, evidence, rollback, and device-portable memory instead of black-box prompt drift.

## Why it is worth cloning

1. **It runs locally first.** The current proof path is CPU-friendly and was verified on older Intel Mac hardware.
2. **It separates proof from roadmap.** The reproducible incumbent stays distinct from candidate lanes and future roadmap claims.
3. **It preserves evidence.** Benchmarks, receipts, manifests, promotion gates, and rollback bundles are treated as first-class artifacts.
4. **It protects the incumbent.** New weights and external datasets enter v2 candidate isolation before they can affect scoring.
5. **It is an AI memory architecture, not only a model script.** The ARC Language Module, Omnibinary, and Arc-RAR create a portable source spine for lexical knowledge, receipts, replay, and restore.
6. **It has a visible product path.** 3.0 is the protected model/dataset/licensing milestone; 4.0 connects ProtoSynth / Neural Synth; 5.0 becomes a Portal-esque companion mockup; 7.0 targets a working Synth AI companion and buildable brain lab.

## What to try first

```bash
git clone https://github.com/GareBear99/ARC-Neuron-LLMBuilder.git
cd ARC-Neuron-LLMBuilder
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/validate_repo.py
python scripts/production_verify.py
```

## What to inspect first

- `README.md` — public front door and current evidence boundary
- `PROOF.md` — reproducible proof and hardware provenance
- `docs/PRODUCTION_RELEASE_HANDOFF.md` — current handoff state
- `docs/DATASET_ACQUISITION_MATRIX_3_0.md` — external dataset acquisition roadmap
- `docs/V2_CANDIDATE_ISOLATION_POLICY.md` — how new weights/datasets are isolated
- `docs/SYNTH_COMPANION_ROADMAP_4_5_7.md` — 4.0/5.0/7.0 Synth path
- `repo-metadata/GITHUB_ABOUT_UPDATE.md` — exact public metadata to paste into GitHub About

## Current truth boundary

The repo is not claiming that external datasets are already trained into the incumbent. The current live evidence is self-curated ARC material plus the reproducible `arc_governed_v10_wave4` incumbent. The listed open-source datasets are acquisition candidates only until manifest, license, hash, quarantine, v2-candidate, benchmark, and Gate v2 checks pass.

## Clone-worthy search terms

local AI, offline LLM builder, GGUF model builder, governed AI, AI provenance, model promotion gate, regression-safe training, dataset governance, Omnibinary memory, Arc-RAR rollback, ARC Language Module, device-portable AI communication, time-to-space projection, ProtoSynth, Neural Synth, Synth companion, buildable brain lab.
