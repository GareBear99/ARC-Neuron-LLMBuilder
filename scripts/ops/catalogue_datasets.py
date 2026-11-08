#!/usr/bin/env python3
"""scripts/ops/catalogue_datasets.py

Dataset catalogue generator + rule validator for ARC-Neuron LLMBuilder.

Reads every dataset on disk (``datasets/``, ``data/`` cognition families,
``benchmarks/``), merges the static registry of datasets that are
to-acquire / to-build / held / blocked, and writes the machine-readable
master index ``datasets/CATALOGUE.json``. It also writes a ``manifest.json``
into every dataset directory that lacks one (never overwriting an existing
manifest — the lucid/us/acquired manifests are authoritative).

Gary's rules, enforced here (hard fail = exit non-zero):
  1. Datasets NEVER touch the progression. They are externally tested and
     documented — that is it. No dataset under ``datasets/acquired/`` may
     appear in any trainer-read path.
  2. The dataset model never touches the repo. Only its catalogued data
     comes back, to progress the 3.0 commercial version natively.
  3. Clean progression. No external dataset pollution in training, ever.
     Training uses only our own data. Track A (Lucid corpus) is the only
     track; Track B (private "us" model) is OFF (Gary, 2026-11-08).
  4. The server LLMBuilder catalogues. The repo is the progression path.

Validation performed (run this script to check them all):
  - "acquired" is in ``_CORPUS_SKIP_PARTS`` in
    ``scripts/training/train_arc_native_candidate.py`` (closes the latent
    vector where ``collect_corpus`` would otherwise sweep acquired
    manifests if the corpus cap were raised).
  - No path under ``datasets/acquired/`` appears in the native trainer's
    ``collect_sft_corpus`` dir list.
  - The LoRA trainer default dataset is the Lucid corpus (Track A only).
  - Every present dataset directory has a README.md or a manifest.json.
  - No catalogue entry claims ``touches_progression: true``.

Usage:
  python3 scripts/ops/catalogue_datasets.py [--check-only]
  --check-only validates the rules without writing anything.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATASETS = ROOT / "datasets"
DATA = ROOT / "data"
BENCHMARKS = ROOT / "benchmarks"

SCHEMA_VERSION = "catalogue/1.0"

# ── static per-family classification (present on disk) ───────────────────────
# category: our-own | our-own-seed | benchmark | external-acquired
# role: training | training-held | evaluation | retrieval | eval-tasks
# lane: candidate_v2_only | candidate_v2 | incumbent (never for new data)
FAMILIES: dict[str, dict] = {
    # --- our own data: the two corpora (Track A trains, Track B held) ---
    "lucid_corpus": {
        "category": "our-own", "role": "training", "lane": "candidate_v2_only",
        "status": "present", "track": "A",
        "purpose": "Lucid-only product knowledge for the public instant-reply model (Track A, the only track).",
        "source": "Lucid repo markdown docs + help commands + Forge surface (build_lucid_corpus.py).",
        "license": "own-data", "license_status": "own-data",
    },
    "us_corpus": {
        "category": "our-own", "role": "training-held", "lane": "candidate_v2_only",
        "status": "held",
        "track": "B",
        "purpose": "Gary's own data (MEMORY.md, daily logs, papers, docs, posts, listings). HELD: Track B, the private Gary model, is OFF (Gary, 2026-11-08) — do NOT train a private Gary model. This corpus is built and kept as an artefact; it is not a training input unless Gary reverses that decision.",
        "source": "MEMORY.md, daily logs, papers, docs, posts, listings (build_us_corpus.py).",
        "license": "own-data", "license_status": "own-data",
    },
    # --- our own data: ARC-native seed / SFT families ---
    "arc_neuron_base": {
        "category": "our-own-seed", "role": "training", "lane": "candidate_v2",
        "status": "present",
        "purpose": "ARC-Core repo reasoning SFT (audit-report lessons). Read by the native trainer (collect_sft_corpus).",
        "source": "ARC-Core audit docs, self-curated.", "license": "own-data",
        "license_status": "own-data",
    },
    "arc_neuron_small": {
        "category": "our-own-seed", "role": "training", "lane": "candidate_v2",
        "status": "present",
        "purpose": "ARC-Neuron Small SFT (chat-style) + next-token text. Read by the native trainer.",
        "source": "ARC repos, self-curated.", "license": "own-data",
        "license_status": "own-data",
    },
    "distillation_sft": {
        "category": "our-own-seed", "role": "training", "lane": "candidate_v2",
        "status": "present",
        "purpose": "Self-curated ARC distillation SFT — waves 1-4, v4/v5/v6, phase-1 targeted records (instruction following, continuity, reflection). The largest seed family.",
        "source": "ARC audit findings + distillation waves, self-curated.",
        "license": "own-data", "license_status": "own-data",
    },
    "cleanroom_supervised": {
        "category": "our-own-seed", "role": "training", "lane": "candidate_v2",
        "status": "present",
        "purpose": "Cleanroom runtime doctrine SFT + preference + trace receipts.",
        "source": "arc-lucifer-cleanroom-runtime, self-curated.",
        "license": "own-data", "license_status": "own-data",
    },
    "distillation_eval": {
        "category": "our-own-seed", "role": "evaluation", "lane": "candidate_v2",
        "status": "present",
        "purpose": "Distillation eval seed tasks (rubric-scored). Evaluation, not training input.",
        "source": "ARC distillation eval, self-curated.",
        "license": "own-data", "license_status": "own-data",
    },
    "distillation_preference": {
        "category": "our-own-seed", "role": "training", "lane": "candidate_v2",
        "status": "present",
        "purpose": "Preference pairs (chosen/rejected) for boundedness and repair. One file is EMPTY (reflection_preference.jsonl, 0 rows) — noted, not hidden.",
        "source": "ARC distillation, self-curated.",
        "license": "own-data", "license_status": "own-data",
    },
    "execution_lane_reasoning": {
        "category": "our-own-seed", "role": "training", "lane": "candidate_v2",
        "status": "present",
        "purpose": "OmniBinary execution-lane / blocker / environment reasoning.",
        "source": "omnibinary-runtime docs, self-curated.",
        "license": "own-data", "license_status": "own-data",
    },
    "language_reasoning": {
        "category": "our-own-seed", "role": "training", "lane": "candidate_v2",
        "status": "present",
        "purpose": "Language-module reasoning: boundary honesty, transliteration/readiness, terminology.",
        "source": "arc-language-module docs, self-curated.",
        "license": "own-data", "license_status": "own-data",
    },
    "receipt_archive": {
        "category": "our-own-seed", "role": "training", "lane": "candidate_v2",
        "status": "present",
        "purpose": "Arc-RAR archive / replay / receipt discipline.",
        "source": "Arc-RAR docs, self-curated.", "license": "own-data",
        "license_status": "own-data",
    },
    "runtime_mindshape": {
        "category": "our-own-seed", "role": "training", "lane": "candidate_v2",
        "status": "present",
        "purpose": "Cleanroom/runtime doctrine: bounded planning, critique, repair posture.",
        "source": "cleanroom runtime doctrine, self-curated.",
        "license": "own-data", "license_status": "own-data",
    },
    "system_of_record": {
        "category": "our-own-seed", "role": "training", "lane": "candidate_v2",
        "status": "present",
        "purpose": "ARC-Core state-and-evidence discipline (proposal, state, evidence).",
        "source": "ARC-Core docs, self-curated.", "license": "own-data",
        "license_status": "own-data",
    },
    "workflow_pressure": {
        "category": "our-own-seed", "role": "training", "lane": "candidate_v2",
        "status": "present",
        "purpose": "Workflow-heavy long-horizon operator and tool-chain pressure tests.",
        "source": "Claude source archive, self-curated.",
        "license": "own-data", "license_status": "own-data",
    },
    # --- placeholder buckets: policy set, no data yet ---
    "base_text": {
        "category": "our-own-seed", "role": "training", "lane": "candidate_v2",
        "status": "empty",
        "purpose": "General-language pretraining bucket (policy: train). Empty — no data yet.",
        "source": "to be filled.", "license": "own-data",
        "license_status": "own-data",
    },
    "code_core": {
        "category": "our-own-seed", "role": "training", "lane": "candidate_v2",
        "status": "empty",
        "purpose": "Code and repo priors bucket (policy: train). Empty — no data yet.",
        "source": "to be filled.", "license": "own-data",
        "license_status": "own-data",
    },
    "domain_packs": {
        "category": "our-own-seed", "role": "retrieval", "lane": "candidate_v2",
        "status": "empty",
        "purpose": "Domain-specific corpora, retrieved live, not trained in (policy: retrieve_only; check license and terms before use). Empty — no data yet.",
        "source": "to be filled.", "license": "own-data",
        "license_status": "own-data",
    },
    "engineering_tasks": {
        "category": "our-own-seed", "role": "training", "lane": "candidate_v2",
        "status": "empty",
        "purpose": "Issue-to-patch, debugging, repair behaviours (policy: train). Empty — no data yet.",
        "source": "to be filled.", "license": "own-data",
        "license_status": "own-data",
    },
    "repo_capsules": {
        "category": "our-own-seed", "role": "retrieval", "lane": "candidate_v2",
        "status": "empty",
        "purpose": "Structured repo-state truth, refreshed outside the weights (policy: retrieve_only). Empty — no data yet.",
        "source": "to be filled.", "license": "own-data",
        "license_status": "own-data",
    },
    "review_and_diffs": {
        "category": "our-own-seed", "role": "training", "lane": "candidate_v2",
        "status": "empty",
        "purpose": "PR, diff, critique, regression-risk behaviour (policy: train). Empty — no data yet.",
        "source": "to be filled.", "license": "own-data",
        "license_status": "own-data",
    },
}

# Cognition seed families under data/ (read by collect_sft_corpus + prepare_distillation_corpus).
DATA_FAMILIES: dict[str, dict] = {
    "calibrate": {"purpose": "Calibration seed examples.", "role": "training"},
    "compress": {"purpose": "Compression seed examples.", "role": "training"},
    "critique": {"purpose": "Critique seed examples. The live gh-ai-operator feed (operator_reviews.jsonl) lands here when it arrives.", "role": "training"},
    "observe_infer": {"purpose": "Observe/infer seed examples.", "role": "training"},
    "plan": {"purpose": "Planning seed examples.", "role": "training"},
    "repair": {"purpose": "Repair seed examples.", "role": "training"},
}

# ── static registry: not on disk yet ─────────────────────────────────────────
# Every entry here is honest about its state: to_acquire / to_build / held /
# blocked / to_arrive. Nothing here claims to exist.
REGISTRY: list[dict] = [
    # NOTE: acquired/gsm8k and acquired/the-stack are NOT in this registry —
    # they are already on disk under datasets/acquired/ and the disk scan
    # covers them (enriched by ACQUIRED_INFO below). Listing them here too
    # would double-count them in the totals.
    # --- external acquisition targets (from DATASET_ACQUISITION_MATRIX_3_0.md + README roadmap) ---
    {"id": "acquired/flan", "name": "FLAN Collection", "category": "external-target",
     "role": "evaluation", "lane": "candidate_v2", "status": "to_acquire",
     "hf_id": "google-research/FLAN (see flan-collection on HF)", "license": "apache-2.0",
     "license_status": "permissive",
     "purpose": "Instruction following and task generalisation. Evaluation-only.",
     "source": "FLAN Collection (google-research). No converter registered yet — write one before acquiring.",
     "acquire": "python3 scripts/ops/acquire_hf_dataset.py --dataset <flan-hf-id> --limit 500  (converter needed first)"},
    {"id": "acquired/oasst1", "name": "OpenAssistant OASST1", "category": "external-target",
     "role": "evaluation", "lane": "candidate_v2", "status": "to_acquire",
     "hf_id": "OpenAssistant/oasst1", "license": "apache-2.0",
     "license_status": "permissive",
     "purpose": "Open assistant dialogue patterns. Evaluation-only.",
     "source": "Hugging Face OpenAssistant/oasst1. Converter IMPLEMENTED in acquire_hf_dataset.py but UNTESTED — needs a real pull to verify.",
     "acquire": "python3 scripts/ops/acquire_hf_dataset.py --dataset OpenAssistant/oasst1 --split train --limit 1000 --out datasets/acquired/oasst1"},
    {"id": "acquired/ultrachat", "name": "UltraChat / UltraChat 200k", "category": "external-target",
     "role": "evaluation", "lane": "candidate_v2", "status": "to_acquire",
     "hf_id": "HuggingFaceH4/ultrachat_200k", "license": "to-verify",
     "license_status": "to-verify",
     "purpose": "Multi-turn conversation. Evaluation-only. NOTE: this is a LARGE dataset (200k) — acquire with a small --limit first.",
     "source": "Hugging Face HuggingFaceH4/ultrachat_200k. Converter IMPLEMENTED but UNTESTED. License must be verified at acquisition (the license gate decides).",
     "acquire": "python3 scripts/ops/acquire_hf_dataset.py --dataset HuggingFaceH4/ultrachat_200k --config train_sft --limit 200"},
    {"id": "acquired/mentalchat16k", "name": "MentalChat16K", "category": "external-target",
     "role": "evaluation", "lane": "candidate_v2", "status": "to_acquire",
     "hf_id": "see paper 2503.13509", "license": "to-verify",
     "license_status": "to-verify",
     "purpose": "Lexical simplicity, empathy, de-escalation, support wording. NOT therapy authority. Safety-reviewed, candidate-v2 only. Evaluation-only.",
     "source": "MentalChat16K and related counseling/support-language data. No converter yet; license + safety review required before acquiring.",
     "acquire": "License + safety review first, then acquire via the acquire lane."},
    {"id": "acquired/wikilarge", "name": "WikiLarge", "category": "external-target",
     "role": "evaluation", "lane": "candidate_v2", "status": "to_acquire",
     "hf_id": "wikilarge (HF)", "license": "cc-by-sa-4.0",
     "license_status": "permissive",
     "purpose": "Plain-language rewriting and readability (text simplification). Evaluation-only.",
     "source": "WikiLarge / text simplification corpora (derived from Wikipedia). No converter yet.",
     "acquire": "Acquire via the acquire lane once a converter is registered."},
    {"id": "acquired/mbpp", "name": "MBPP", "category": "external-target",
     "role": "evaluation", "lane": "candidate_v2", "status": "to_acquire",
     "hf_id": "mbpp (verify HF id at acquisition)", "license": "cc-by-4.0",
     "license_status": "permissive",
     "purpose": "Python/code task solving. Evaluation-only.",
     "source": "MBPP (google-research). Canonical source: google-research/google-research (mbpp). No converter yet.",
     "acquire": "Acquire via the acquire lane once a converter is registered."},
    {"id": "acquired/humaneval", "name": "HumanEval", "category": "external-target",
     "role": "evaluation", "lane": "candidate_v2", "status": "to_acquire",
     "hf_id": "openai/openai_humaneval", "license": "mit",
     "license_status": "permissive",
     "purpose": "Code evaluation and repair benchmarking. Eval only by default.",
     "source": "HumanEval (openai/human-eval). No converter yet.",
     "acquire": "Acquire via the acquire lane once a converter is registered."},
    # --- additional evaluation benchmarks (standard eval suite; evaluation-only) ---
    {"id": "acquired/mmlu", "name": "MMLU", "category": "external-target",
     "role": "evaluation", "lane": "candidate_v2", "status": "to_acquire",
     "hf_id": "cais/mmlu", "license": "mit", "license_status": "permissive",
     "purpose": "Massive multitask general-knowledge evaluation. Evaluation-only.",
     "source": "Hugging Face cais/mmlu. No converter yet.",
     "acquire": "Acquire via the acquire lane once a converter is registered."},
    {"id": "acquired/hellaswag", "name": "HellaSwag", "category": "external-target",
     "role": "evaluation", "lane": "candidate_v2", "status": "to_acquire",
     "hf_id": "Rowan/hellaswag", "license": "mit", "license_status": "permissive",
     "purpose": "Commonsense reasoning evaluation. Evaluation-only.",
     "source": "Hugging Face Rowan/hellaswag. No converter yet.",
     "acquire": "Acquire via the acquire lane once a converter is registered."},
    {"id": "acquired/ai2_arc", "name": "AI2 ARC (Easy + Challenge)", "category": "external-target",
     "role": "evaluation", "lane": "candidate_v2", "status": "to_acquire",
     "hf_id": "allenai/ai2_arc", "license": "cc-by-sa-4.0",
     "license_status": "permissive",
     "purpose": "Grade-school science reasoning evaluation. Evaluation-only. NOTE: 'ARC' here is the AI2 Reasoning Challenge — NOT ARC-Neuron. Do not confuse the two.",
     "source": "Hugging Face allenai/ai2_arc. No converter yet.",
     "acquire": "Acquire via the acquire lane once a converter is registered."},
    {"id": "acquired/truthfulqa", "name": "TruthfulQA", "category": "external-target",
     "role": "evaluation", "lane": "candidate_v2", "status": "to_acquire",
     "hf_id": "truthfulqa/truthful_qa", "license": "apache-2.0",
     "license_status": "permissive",
     "purpose": "Truthfulness evaluation (does the model repeat common falsehoods?). Evaluation-only.",
     "source": "Hugging Face truthfulqa/truthful_qa. No converter yet.",
     "acquire": "Acquire via the acquire lane once a converter is registered."},
    {"id": "acquired/winogrande", "name": "Winogrande", "category": "external-target",
     "role": "evaluation", "lane": "candidate_v2", "status": "to_acquire",
     "hf_id": "winogrande", "license": "apache-2.0",
     "license_status": "permissive (verify at acquisition)",
     "purpose": "Commonsense reasoning evaluation (fill-in-the-blank). Evaluation-only.",
     "source": "Hugging Face winogrande. No converter yet; verify the Apache-2.0 license at acquisition.",
     "acquire": "Acquire via the acquire lane once a converter is registered."},
    {"id": "acquired/lambada", "name": "LAMBADA", "category": "external-target",
     "role": "evaluation", "lane": "candidate_v2", "status": "to_acquire",
     "hf_id": "cimec/lambada", "license": "cc-by-4.0",
     "license_status": "permissive",
     "purpose": "Long-range word-prediction evaluation (10,022 narrative passages; the last word is only guessable with the full passage). Evaluation-only.",
     "source": "Hugging Face cimec/lambada (dataset card: CC BY 4.0). No converter yet.",
     "acquire": "Acquire via the acquire lane once a converter is registered."},
    {"id": "acquired/piqa", "name": "PIQA", "category": "external-target",
     "role": "evaluation", "lane": "quarantine", "status": "held",
     "hf_id": "ybisk/piqa", "license": "afl-3.0", "license_status": "not-on-allowlist",
     "purpose": "Physical commonsense evaluation. HELD — license AFL-3.0 (Academic Free License) is NOT on the repo's permissive allowlist, so the acquire lane would hold it, like The Stack. A human must review the license before it can enter any lane. Note: HF dataset-loading scripts are deprecated for this dataset — use the auto-converted parquet mirror (refs/convert/parquet) when acquiring.",
     "source": "Hugging Face ybisk/piqa (license AFL-3.0, verified 2026-11-08).",
     "acquire": "HELD — do not acquire until a human reviews the AFL-3.0 license."},
    # --- our own data: to build (compile from our sources, Lucid-corpus pattern) ---
    {"id": "build/freeeq8_corpus", "name": "FreeEQ8 corpus", "category": "our-own-to-build",
     "role": "training", "lane": "candidate_v2_only", "status": "to_build",
     "license": "own-data", "license_status": "own-data",
     "purpose": "FreeEQ8 product knowledge (lock-free dynamic EQ, SVF/RBJ, Natural Phase, Smart EQ) for an audio/DSP instant-reply model and for the 3.0 commercial version's audio knowledge.",
     "source": "FreeEQ8 paper + docs on the VM (~/workspace/FreeEQ8/PAPER.md). 88 rows of it already live inside us_corpus (docs/FreeEQ8-PAPER) — a standalone corpus compiles the same sources the Lucid-corpus way. Builder: new script in the build_lucid_corpus.py pattern.",
     "acquire": "Build: compile FreeEQ8 paper + docs into SFT pairs (verbatim, secret-scanned, manifested)."},
    {"id": "build/therum_corpus", "name": "Therum corpus", "category": "our-own-to-build",
     "role": "training", "lane": "candidate_v2_only", "status": "to_build",
     "license": "own-data", "license_status": "own-data",
     "purpose": "Therum product knowledge (wavetable synth, JUCE + iPlug2) for a synth instant-reply model and for 3.0.",
     "source": "Therum papers on the VM (~/workspace/Therum_JUCE-Plugin/PAPER.md, ~/workspace/Therum_iPlug2-Plugin/PAPER.md). 52 rows already inside us_corpus.",
     "acquire": "Build: compile Therum papers + docs into SFT pairs."},
    {"id": "build/freevox8_corpus", "name": "FreeVox8 corpus", "category": "our-own-to-build",
     "role": "training", "lane": "candidate_v2_only", "status": "to_build",
     "license": "own-data", "license_status": "own-data",
     "purpose": "FreeVox8 product knowledge (Ghost FFT vocal processing) for a vocal instant-reply model and for 3.0.",
     "source": "FreeVox8 paper on the VM (~/workspace/FreeVox8/PAPER.md). 46 rows already inside us_corpus.",
     "acquire": "Build: compile FreeVox8 paper + docs into SFT pairs."},
    {"id": "build/itch_corpus", "name": "itch corpus", "category": "our-own-to-build",
     "role": "training", "lane": "candidate_v2_only", "status": "to_build",
     "license": "own-data", "license_status": "own-data",
     "purpose": "Store/commerce knowledge — all 112 itch listings (titles, descriptions, funnel lines) for a shop instant-reply model and for 3.0.",
     "source": "itch listings on the VM (~/workspace/itch-seo/all_items.json). 134 rows already inside us_corpus.",
     "acquire": "Build: compile the 112 listings into SFT pairs."},
    {"id": "build/packs_corpus", "name": "Sample packs corpus", "category": "our-own-to-build",
     "role": "training", "lane": "candidate_v2_only", "status": "to_build",
     "license": "own-data", "license_status": "own-data",
     "purpose": "Sample-pack knowledge (listen verdicts, pack notes, suitability) for an audio/sample instant-reply model and for 3.0.",
     "source": "Packs listen report on the VM (~/workspace/packs-listen-report.md).",
     "acquire": "Build: compile the listen report + pack metadata into SFT pairs."},
    {"id": "build/crypto_corpus", "name": "Crypto research corpus", "category": "our-own-to-build",
     "role": "training", "lane": "candidate_v2_only", "status": "to_build",
     "license": "own-data", "license_status": "own-data",
     "purpose": "Trading research knowledge (Harvest/BrokeBot/Charm findings, strategy catalogue, backtests, risk audit) for a research instant-reply model and for 3.0.",
     "source": "Crypto reports on the VM (~/workspace/crypto-bots/: strategy-catalogue.md, HARVEST_ER90_*.md, he-walkforward-backtest.md, LIVE_TRADING_RISK_AUDIT.md).",
     "acquire": "Build: compile the research reports into SFT pairs. (Paper-trading research only — never live-trading advice.)"},
    {"id": "build/hub_corpus", "name": "HUB corpus", "category": "our-own-to-build",
     "role": "training", "lane": "candidate_v2_only", "status": "to_build",
     "license": "own-data", "license_status": "own-data",
     "purpose": "HUB product knowledge (TizWildinEntertainmentHUB docs) for a hub instant-reply model and for 3.0.",
     "source": "HUB docs on the VM (~/workspace/TizWildinEntertainmentHUB/docs/). 112 rows already inside us_corpus.",
     "acquire": "Build: compile HUB docs into SFT pairs."},
    {"id": "build/voice_corpus", "name": "Voice-note corpus (Phase 1b)", "category": "our-own-to-build",
     "role": "training", "lane": "candidate_v2_only", "status": "to_build",
     "license": "own-data", "license_status": "own-data",
     "purpose": "Gary's voice, transcribed — 73 voice-note mp3s. Deferred (Phase 1b): needs Whisper transcription (slow on CPU, or the free T4). Substance already covered by MEMORY.md + daily logs.",
     "source": "Voice notes on the VM (~/workspace/your_files/voice-message-*.mp3).",
     "acquire": "Build (Phase 1b): transcribe with Whisper, then compile transcripts through the same compiler (same schema, same secret scan)."},
    {"id": "build/transcripts_corpus", "name": "Chat transcripts corpus", "category": "our-own-to-build",
     "role": "training", "lane": "candidate_v2_only", "status": "blocked",
     "license": "own-data", "license_status": "own-data",
     "purpose": "Gary's words as training data (chat transcripts). BLOCKED — using Gary's words as training data is Gary's call and it has NOT been given. Do NOT build.",
     "source": "Muse conversation store. Gary's call — not given.",
     "acquire": "BLOCKED — do not build until Gary explicitly approves."},
    {"id": "build/lucid_growth", "name": "Lucid corpus growth (2k / 10k)", "category": "our-own-to-build",
     "role": "training", "lane": "candidate_v2_only", "status": "to_build",
     "license": "own-data", "license_status": "own-data",
     "purpose": "Grow lucid_corpus from 1,650 rows toward the 2,000–5,000 credible-first-run target and the 10k goal. To 2k: code-comment pairs (TypeScript/Python doc comments in src/, electron/, LUCID-BACKEND/) and/or a third prompt template per section. To 10k: more Lucid docs written, real user questions + answers from the live system, and/or synthetic Q&A from the docs (human review gate before it enters training).",
     "source": "Lucid repo code + docs + live-system Q&A.",
     "acquire": "Build: extend build_lucid_corpus.py (code comments, third template), then rebuild."},
    # --- live feed: to arrive ---
    {"id": "live/operator_reviews", "name": "Operator reviews (gh-ai-operator feed)", "category": "our-own-live",
     "role": "training", "lane": "candidate_v2", "status": "to_arrive",
     "license": "own-data", "license_status": "own-data",
     "purpose": "Highest-trust self-curated learning data: the ARC GitHub AI Operator answers code-review issues on the Portfolio and emits every production review as a supervised training example. Lands nightly into data/critique/operator_reviews.jsonl (workflow ingest-operator-reviews.yml). Human-correction records get +0.05 confidence so Gate v2 weights them higher.",
     "source": "gh-ai-operator (GareBear99/gh-ai-operator) nightly workflow. File does NOT exist locally yet.",
     "acquire": "Arrives nightly via the workflow. No manual step."},
]


# Enrichment for the acquired datasets already on disk (the disk scan covers
# them; this adds the purpose / acquire command / converter status that the
# raw scan cannot know).
ACQUIRED_INFO: dict[str, dict] = {
    "gsm8k": {
        "purpose": "Grade-school arithmetic reasoning benchmark/reference. EVALUATION ONLY — never training data.",
        "acquire": "python3 scripts/ops/acquire_hf_dataset.py --dataset openai/gsm8k --limit 500",
        "hf_id": "openai/gsm8k",
        "converter": "VERIFIED (real pull 2026-11-06)",
        "notes": "Acquired 2026-11-06, quarantined (raw parquet) + manifested, pending Gate v2.",
    },
    "the-stack": {
        "purpose": "Code reference data. HELD — card license 'other' is not on the permissive allowlist. No download, no records, no conversion. A human must review the license before it can enter any lane.",
        "acquire": "HELD — do not acquire until a human reviews the license.",
        "hf_id": "bigcode/the-stack",
        "converter": "none (held)",
        "notes": "Manifest only. License review required.",
    },
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def count_jsonl(path: Path) -> int:
    n = 0
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


def schema_keys(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                return []
            if isinstance(obj, dict):
                return sorted(obj.keys())
            return []
    return []


def scan_dataset_dir(d: Path) -> dict:
    """Scan one dataset directory on disk: files, rows, bytes, schema."""
    files = []
    total_rows = 0
    total_bytes = 0
    schema: list[str] = []
    for p in sorted(d.rglob("*")):
        if not p.is_file():
            continue
        if p.name in ("README.md", "manifest.json"):
            continue
        size = p.stat().st_size
        total_bytes += size
        entry: dict = {
            "file": p.relative_to(d).as_posix(),
            "bytes": size,
            "sha256": sha256_file(p),
        }
        if p.suffix == ".jsonl":
            rows = count_jsonl(p)
            entry["rows"] = rows
            total_rows += rows
            if not schema:
                schema = schema_keys(p)
        elif p.suffix == ".txt":
            with p.open("r", encoding="utf-8", errors="ignore") as f:
                lines = sum(1 for line in f if line.strip())
            entry["rows"] = lines
            total_rows += lines
        elif p.suffix == ".parquet":
            entry["rows"] = None  # raw bytes; row count lives in the manifest
        files.append(entry)
    return {
        "files": files,
        "total_rows": total_rows,
        "total_bytes": total_bytes,
        "schema": schema,
    }


def write_manifest(d: Path, entry: dict, scan: dict) -> None:
    """Write manifest.json into a dataset dir that lacks one. Never overwrite."""
    manifest_path = d / "manifest.json"
    if manifest_path.exists():
        return
    manifest = {
        "schema_version": "catalogue/1.0",
        "dataset": d.name,
        "category": entry["category"],
        "role": entry["role"],
        "promotion_lane": entry["lane"],
        "status": entry["status"],
        "touches_progression": False,
        "purpose": entry["purpose"],
        "source": entry["source"],
        "license": entry["license"],
        "license_status": entry["license_status"],
        "total_rows": scan["total_rows"],
        "total_bytes": scan["total_bytes"],
        "schema": scan["schema"],
        "files": scan["files"],
        "notes": "Generated by scripts/ops/catalogue_datasets.py. The Lucid/Track A corpus and the held us corpus have their own authoritative manifests; this manifest covers a seed dataset.",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"  wrote {manifest_path.relative_to(ROOT)}")


def validate(check_only: bool) -> list[str]:
    """Validate Gary's hard rules against the repo. Returns a list of failures."""
    failures: list[str] = []

    # 1. "acquired" must be in _CORPUS_SKIP_PARTS (closes the latent vector).
    trainer = ROOT / "scripts" / "training" / "train_arc_native_candidate.py"
    text = trainer.read_text(encoding="utf-8")
    if '"acquired"' not in text and "'acquired'" not in text:
        failures.append(
            "train_arc_native_candidate.py: 'acquired' is NOT in "
            "_CORPUS_SKIP_PARTS — collect_corpus could sweep acquired "
            "manifests if the corpus cap were raised (latent vector)."
        )

    # 2. No acquired path in the native trainer's collect_sft_corpus dir list.
    if "datasets/acquired" in text or "datasets\" / \"acquired" in text:
        # Only flag it if it appears inside the sft_dirs list, not in a comment.
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("#"):
                continue
            if "acquired" in s and ("datasets" in s or "repo_root" in s):
                failures.append(
                    "train_arc_native_candidate.py: an acquired path appears "
                    f"in trainer code: {s}"
                )

    # 3. The LoRA trainer default dataset must be the Lucid corpus (Track A only).
    lora = ROOT / "scripts" / "training" / "train_lora.py"
    if lora.exists():
        lora_text = lora.read_text(encoding="utf-8")
        if 'datasets" / "us_corpus"' in lora_text or "datasets/us_corpus" in lora_text:
            # The us corpus may still be mentioned as the held Track B corpus,
            # but it must not be the DEFAULT_DATASET.
            for line in lora_text.splitlines():
                if line.strip().startswith("DEFAULT_DATASET") and "us_corpus" in line:
                    failures.append(
                        "train_lora.py: DEFAULT_DATASET still points at "
                        "us_corpus (Track B is OFF — Gary, 2026-11-08). "
                        "Default must be datasets/lucid_corpus/lucid_corpus.jsonl."
                    )

    # 4. Every present dataset directory must have a README.md or manifest.json.
    for d in sorted(DATASETS.iterdir()):
        if not d.is_dir():
            continue
        if d.name == "acquired":
            for sub in sorted(d.iterdir()):
                if sub.is_dir() and not (sub / "README.md").exists() and not (sub / "manifest.json").exists():
                    failures.append(f"datasets/acquired/{sub.name}: no README.md or manifest.json.")
            continue
        if not (d / "README.md").exists() and not (d / "manifest.json").exists():
            failures.append(f"datasets/{d.name}: no README.md or manifest.json.")

    # 5. No catalogue entry may claim touches_progression = true.
    # (Checked by construction: every entry below is written with False.)
    return failures


def build(check_only: bool = False) -> dict:
    entries: list[dict] = []

    # --- datasets/ on disk ---
    for d in sorted(DATASETS.iterdir()):
        if not d.is_dir() or d.name == "acquired":
            continue
        info = FAMILIES.get(d.name)
        if info is None:
            print(f"  WARNING: datasets/{d.name} has no FAMILIES entry — skipping.")
            continue
        scan = scan_dataset_dir(d)
        manifest = d / "manifest.json"
        authoritative_rows = None
        if manifest.exists():
            try:
                m = json.loads(manifest.read_text(encoding="utf-8"))
                authoritative_rows = m.get("total_rows")
            except (json.JSONDecodeError, OSError):
                pass
        rows = authoritative_rows if authoritative_rows is not None else scan["total_rows"]
        if authoritative_rows is not None and authoritative_rows != scan["total_rows"]:
            print(
                f"  WARNING: datasets/{d.name} manifest says {authoritative_rows} rows "
                f"but disk has {scan['total_rows']} — manifest wins in the catalogue."
            )
        entry = {
            "id": f"datasets/{d.name}",
            "name": d.name,
            "category": info["category"],
            "role": info["role"],
            "promotion_lane": info["lane"],
            "status": info["status"],
            "touches_progression": False,
            "purpose": info["purpose"],
            "source": info["source"],
            "license": info["license"],
            "license_status": info["license_status"],
            "rows": rows,
            "bytes": scan["total_bytes"],
            "schema": scan["schema"],
            "files": [f["file"] for f in scan["files"]],
        }
        if "track" in info:
            entry["track"] = info["track"]
        entries.append(entry)
        if not check_only:
            write_manifest(d, info, scan)

    # --- datasets/acquired/ on disk ---
    acquired_dir = DATASETS / "acquired"
    if acquired_dir.is_dir():
        for sub in sorted(acquired_dir.iterdir()):
            if not sub.is_dir():
                continue
            scan = scan_dataset_dir(sub)
            manifest = sub / "manifest.json"
            rows = scan["total_rows"]
            license_ = "to-verify"
            license_status = "to-verify"
            if manifest.exists():
                try:
                    m = json.loads(manifest.read_text(encoding="utf-8"))
                    rows = m.get("counts", {}).get("converted", rows)
                    license_ = m.get("source", {}).get("license", license_)
                    license_status = m.get("source", {}).get("license_status", license_status)
                except (json.JSONDecodeError, OSError):
                    pass
            status = "present" if rows else "held"
            info = ACQUIRED_INFO.get(sub.name, {})
            entries.append({
                "id": f"datasets/acquired/{sub.name}",
                "name": sub.name,
                "category": "external-acquired",
                "role": "evaluation",
                "promotion_lane": "candidate_v2_only" if rows else "quarantine",
                "status": status,
                "touches_progression": False,
                "purpose": info.get("purpose", "External dataset, acquired through the acquisition lane. EVALUATION ONLY — never training data."),
                "source": f"Hugging Face (see datasets/acquired/{sub.name}/manifest.json).",
                "license": license_,
                "license_status": license_status,
                "rows": rows,
                "bytes": scan["total_bytes"],
                "schema": scan["schema"],
                "files": [f["file"] for f in scan["files"]],
                **({"acquire": info["acquire"]} if "acquire" in info else {}),
                **({"hf_id": info["hf_id"]} if "hf_id" in info else {}),
                **({"converter": info["converter"]} if "converter" in info else {}),
                **({"notes": info["notes"]} if "notes" in info else {}),
            })

    # --- data/ cognition families on disk ---
    for name in sorted(DATA_FAMILIES):
        d = DATA / name
        if not d.is_dir():
            continue
        scan = scan_dataset_dir(d)
        entries.append({
            "id": f"data/{name}",
            "name": name,
            "category": "our-own-seed",
            "role": DATA_FAMILIES[name]["role"],
            "promotion_lane": "candidate_v2",
            "status": "present",
            "touches_progression": False,
            "purpose": DATA_FAMILIES[name]["purpose"],
            "source": "ARC cognition seed examples, self-curated.",
            "license": "own-data",
            "license_status": "own-data",
            "rows": scan["total_rows"],
            "bytes": scan["total_bytes"],
            "schema": scan["schema"],
            "files": [f["file"] for f in scan["files"]],
        })

    # --- benchmarks/ families on disk (eval tasks, not training data) ---
    for d in sorted(BENCHMARKS.iterdir()):
        if not d.is_dir():
            continue
        scan = scan_dataset_dir(d)
        entries.append({
            "id": f"benchmarks/{d.name}",
            "name": d.name,
            "category": "benchmark",
            "role": "evaluation",
            "promotion_lane": "benchmark",
            "status": "present",
            "touches_progression": False,
            "purpose": f"Gate v2 benchmark family ({d.name}). Evaluation tasks, not training data.",
            "source": "ARC-Neuron benchmark suite, self-curated.",
            "license": "own-data",
            "license_status": "own-data",
            "rows": scan["total_rows"],
            "bytes": scan["total_bytes"],
            "schema": scan["schema"],
            "files": [f["file"] for f in scan["files"]],
        })
    root_bench = BENCHMARKS / "v2_memory_continuity_tasks.jsonl"
    if root_bench.exists():
        entries.append({
            "id": "benchmarks/v2_memory_continuity_tasks",
            "name": "v2_memory_continuity_tasks",
            "category": "benchmark",
            "role": "evaluation",
            "promotion_lane": "benchmark",
            "status": "present",
            "touches_progression": False,
            "purpose": "Memory/continuity regression tasks (Gate v2).",
            "source": "ARC-Neuron benchmark suite, self-curated.",
            "license": "own-data",
            "license_status": "own-data",
            "rows": count_jsonl(root_bench),
            "bytes": root_bench.stat().st_size,
            "schema": schema_keys(root_bench),
            "files": ["v2_memory_continuity_tasks.jsonl"],
        })

    # --- registry entries (to acquire / to build / held / blocked / to arrive) ---
    for reg in REGISTRY:
        entries.append({
            "id": reg["id"],
            "name": reg["name"],
            "category": reg["category"],
            "role": reg["role"],
            "promotion_lane": reg["lane"],
            "status": reg["status"],
            "touches_progression": False,
            "purpose": reg["purpose"],
            "source": reg["source"],
            "license": reg["license"],
            "license_status": reg["license_status"],
            "rows": reg.get("rows"),
            "bytes": None,
            "schema": [],
            "files": [],
            "acquire": reg["acquire"],
            **({"hf_id": reg["hf_id"]} if "hf_id" in reg else {}),
        })

    entries.sort(key=lambda e: e["id"])

    totals = {
        "entries": len(entries),
        "present_our_own_training_rows": sum(
            e["rows"] or 0 for e in entries
            if e["category"] in ("our-own", "our-own-seed") and e["role"] == "training" and e["status"] == "present"
        ),
        "present_evaluation_rows": sum(
            e["rows"] or 0 for e in entries
            if e["role"] == "evaluation" and e["status"] == "present"
        ),
        "benchmark_tasks": sum(
            e["rows"] or 0 for e in entries if e["category"] == "benchmark"
        ),
        "to_acquire": sum(1 for e in entries if e["status"] == "to_acquire"),
        "to_build": sum(1 for e in entries if e["status"] == "to_build"),
        "held": sum(1 for e in entries if e["status"] == "held"),
        "blocked": sum(1 for e in entries if e["status"] == "blocked"),
        "empty": sum(1 for e in entries if e["status"] == "empty"),
    }

    catalogue = {
        "schema_version": SCHEMA_VERSION,
        "rules": {
            "datasets_never_touch_progression": True,
            "dataset_model_never_touches_repo": True,
            "clean_progression": True,
            "no_external_pollution_in_training": True,
            "track_a_only": True,
            "track_b_off": True,
            "server_catalogues": True,
            "repo_is_progression_path": True,
            "note": "Datasets are externally tested and documented — that is it. Only catalogued data comes back to the repo to progress the 3.0 commercial version natively. (Gary, 2026-11-08.)",
        },
        "totals": totals,
        "datasets": entries,
    }
    return catalogue


def main() -> int:
    check_only = "--check-only" in sys.argv
    print("Validating rules...")
    failures = validate(check_only)
    if failures:
        print("RULE VIOLATIONS:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("  all rules pass.")
    if check_only:
        print("Check-only mode: nothing written.")
        return 0
    print("Building catalogue...")
    catalogue = build(check_only=False)
    out = DATASETS / "CATALOGUE.json"
    out.write_text(json.dumps(catalogue, indent=2) + "\n", encoding="utf-8")
    print(f"  wrote {out.relative_to(ROOT)}")
    t = catalogue["totals"]
    print(f"  entries: {t['entries']} | present our-own training rows: {t['present_our_own_training_rows']} | "
          f"present evaluation rows: {t['present_evaluation_rows']} | benchmark tasks: {t['benchmark_tasks']} | "
          f"to_acquire: {t['to_acquire']} | to_build: {t['to_build']} | held: {t['held']} | "
          f"blocked: {t['blocked']} | empty: {t['empty']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
