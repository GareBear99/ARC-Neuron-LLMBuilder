# ARC-StreamMemory Add-On Roadmap

**ARC-StreamMemory** is the visual/video memory add-on being built for **all LLMs, local models, agent runtimes, robotics loops, UI debuggers, and ARC-style systems**.

Repository: <https://github.com/GareBear99/ARC-StreamMemory>

## Role in the ARC-Neuron roadmap

ARC-Neuron is the governed model-growth, benchmark, promotion, and provenance layer. ARC-StreamMemory is the visual second-brain layer that gives LLMs inspectable memory from screens, video, snapshots, DAW/plugin sessions, game footage, browser work, robotics camera feeds, and app UI states.

It should be treated as an **add-on module**, not as a hidden dataset and not as promoted incumbent weights. Its outputs can become module attachments, evidence packets, evaluation traces, visual RAG inputs, or future candidate-lane data only after manifest, hash, provenance, and review gates are satisfied.

## What ARC-StreamMemory contributes

- AI visual memory and video memory for LLMs
- Screen recording for AI-readable replay
- Local-first multimodal memory modules
- Visual RAG / frame retrieval paths
- Deterministic video archive and frame hashing
- Robotics camera memory and sensor-synced capture planning
- FFmpeg frame sampling for AI inspection
- Reproducible visual evidence bundles
- Module attachment JSON for ARC-Neuron, ARC-Core, or other LLM runtimes
- ARC-Core-style receipts
- Omnibinary-style chunk maps
- Arc-RAR-style bundle manifests

## Why it matters

Most LLMs cannot remember what happened on screen unless a user manually describes it. ARC-StreamMemory turns visual activity into structured, hashed, replayable, AI-readable memory.

The intended system shape is:

```text
video / screen / camera / UI session
→ FFmpeg or ARC-FusionCapture ingest
→ frame-speed policy
→ frame hashes
→ seeded source spine
→ AI digest
→ ARC receipts
→ Omnibinary pointers
→ Arc-RAR bundle manifest
→ module attachment for an LLM or ARC-style runtime
```

## Compatibility target

ARC-StreamMemory is being designed to work beyond ARC-Neuron. The add-on target is any system that can consume structured JSON, markdown digests, frame indexes, hashes, and replayable evidence bundles.

Compatible target classes:

- ARC-Neuron / LLMBuilder
- ARC-Core authority/receipt systems
- Omnibinary memory ledgers
- Arc-RAR archive/restore packages
- local GGUF models
- desktop agent runtimes
- robotics camera loops
- UI testing and debugging agents
- audio/plugin visual regression workflows
- any LLM that can read module attachments

## Boundary

ARC-StreamMemory is not currently claimed as native live screen capture inside ARC-Neuron, not a promoted dataset source, and not incumbent weight training data. It is a public add-on path for visual memory, module attachments, reproducible evidence, and future candidate-lane evaluation.

## Roadmap placement

- **3.0**: protected ARC-Neuron base-model / dataset / licensing roadmap
- **4.0**: ProtoSynth / Neural Synth projection layer
- **4.x add-on**: ARC-StreamMemory visual memory module attachments for LLMs and ARC-style systems
- **5.0**: Portal-esque Synth companion mockup
- **7.0**: working Synth AI companion, AGI assistant, and buildable brain lab
