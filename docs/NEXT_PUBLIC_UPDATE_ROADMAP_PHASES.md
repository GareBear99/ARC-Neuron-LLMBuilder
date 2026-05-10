# Next public update roadmap phases


This graph is the next public-facing roadmap map. It keeps the current v10 proof base intact, then labels the next public update phases from credibility cleanup through targeted data, external backend proof, protected 3.0 integration, and the later Synth horizons. These are roadmap phases, not claims that future layers are already trained into the incumbent.

```mermaid
flowchart TD
    V10["Current reproducible incumbent<br/>arc_governed_v10_wave4<br/>0.9237 audited score"] --> P0["Phase 0 — Credibility cleanup<br/>README truth sync<br/>.env example<br/>stub-record evidence"]

    P0 --> P1["Phase 1 — Targeted v2 candidate data<br/>instruction_following<br/>continuity<br/>reflection"]

    P1 --> P2["Phase 2 — External GGUF backend proof<br/>llama_cpp_http / 1–3B model<br/>Gate v2 backend-agnostic validation"]

    P2 --> P3["Phase 3 / ARC-Neuron 3.0<br/>protected base-model roadmap<br/>dataset manifests<br/>license transition<br/>Language Module → corpus loop"]

    P3 --> P4["ARC-Neuron 4.0<br/>ProtoSynth / Neural Synth<br/>spatial projection<br/>time-to-space memory views"]

    P4 --> P5["ARC-Neuron 5.0<br/>Portal-style Synth companion mockup<br/>modular shell<br/>interactive operator interface"]

    P5 --> P7["ARC-Neuron 7.0<br/>working Synth AI companion<br/>AGI assistant<br/>buildable brain lab"]

    STREAM["ARC-StreamMemory<br/>visual/video memory add-on<br/>for all LLMs + ARC-style systems"] --> P2
    STREAM --> P3
    STREAM --> P4

    WARP["Warp pairing<br/>agentic terminal execution"] --> P1
    WARP --> P2
    WARP --> P3

    LANG["ARC Language Module<br/>lexical/provenance spine"] --> P1
    LANG --> P3
    LANG --> P4

    OMNI["Omnibinary Runtime<br/>event receipts + memory substrate"] --> P0
    OMNI --> P3

    RAR["Arc-RAR<br/>rollback/archive bundles"] --> P0
    RAR --> P3

    GATE["Gate v2<br/>no-regression promotion law"] -.guards.-> P1
    GATE -.guards.-> P2
    GATE -.guards.-> P3
    GATE -.guards.-> P4
    GATE -.guards.-> P5
    GATE -.guards.-> P7

    style V10 fill:#0e8a16,stroke:#fff,color:#fff
    style P0 fill:#57606a,stroke:#fff,color:#fff
    style P1 fill:#0969da,stroke:#fff,color:#fff
    style P2 fill:#8250df,stroke:#fff,color:#fff
    style P3 fill:#6f42c1,stroke:#fff,color:#fff
    style P4 fill:#1f6feb,stroke:#fff,color:#fff
    style P5 fill:#5319e7,stroke:#fff,color:#fff
    style P7 fill:#b60205,stroke:#fff,color:#fff
    style STREAM fill:#fbca04,color:#000
    style GATE fill:#d73a4a,stroke:#fff,color:#fff
```

| Phase | Public label | Purpose |
|---|---|---|
| Current | v10 audited incumbent | Preserve the reproducible proof base before new changes. |
| Phase 0 | Credibility cleanup | Fix stale README facts, missing env example, and stub-record evidence. |
| Phase 1 | Targeted v2 candidate data | Add surgical examples for weak lanes without polluting incumbent scoring. |
| Phase 2 | External GGUF backend proof | Prove Gate v2 works with a real 1–3B GGUF backend through `llama_cpp_http`. |
| Phase 3 / 3.0 | Protected base-model integration | Dataset manifests, license transition, v2 isolation, and Language Module → corpus loop. |
| 4.0 | ProtoSynth / Neural Synth projection | Spatial/visual cognition layer and time-to-space memory projection. |
| 5.0 | Portal-style Synth companion mockup | Full modular companion shell and operator-facing mockup. |
| 7.0 | Working Synth AI / brain lab | Synth AI companion, AGI assistant, and buildable brain lab target. |

Boundary: these phases are roadmap labels. They do not bypass Gate v2, dataset manifests, rollback evidence, or incumbent protection. ARC-StreamMemory, Warp pairing, ProtoSynth/Neural Synth, and the Synth companion shell attach around the governed ARC-Neuron loop; they do not silently replace the current incumbent.

Standalone roadmap doc: [NEXT_PUBLIC_UPDATE_ROADMAP_PHASES.md](./docs/NEXT_PUBLIC_UPDATE_ROADMAP_PHASES.md).

