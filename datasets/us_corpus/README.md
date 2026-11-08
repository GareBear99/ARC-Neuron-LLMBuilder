# "us" SFT corpus — LLMBuilder 1B LoRA fine-tune

> **HELD — DO NOT TRAIN (Gary, 2026-11-08 ~00:34–00:39 PST).** Gary
> corrected the plan: *"nothing just for me this is a product for
> users."* **Track A ONLY. Track B (private Gary model) is OFF — do NOT
> train a private Gary model.** This corpus was built for Track B, so it
> is HELD. It exists as a built artefact (3,674 rows, manifested); it is
> NOT a training input unless Gary reverses that decision. The trainer
> default is now the Lucid corpus (`datasets/lucid_corpus/` — Track A).
> See the master catalogue: `datasets/README.md` / `datasets/CATALOGUE.json`.

**Location:** `datasets/us_corpus/` (this directory)
**Built by:** `scripts/ops/build_us_corpus.py` (run from the repo root)
**Version:** 1 — built 2026-11-07
**Total rows:** 3,674 SFT pairs
**Schema:** `{id, source_repo, capability, domain, prompt, target, tags, promotion_lane, notes}`
— exactly the repo seed schema (as in `datasets/acquired/gsm8k/gsm8k.jsonl`).
Every row has `promotion_lane: "candidate_v2_only"` (new dataset family →
candidate_v2 lane by default, per the v2 class policy).

## What is in the corpus

General knowledge about our stuff and system, "in every way spoken" (Gary,
2026-11-07 ~03:57 PST): Gary's projects, Lucid, the work, the system. Three
pair types from the training plan (§3): **(a) knowledge** — "what did we
decide about X?" → the decision; **(b) voice** — prompts phrased the way Gary
phrases them → answers in Slave's recorded phrasing; **(c) work** — "what
does X do / how does Y work?" → the doc answer.

Targets are **verbatim (lightly cleaned) source text** — markdown stripped,
code fences dropped. Prompts are deterministic templates grounded in the
source's own headings, bold topics, titles, or listing names. Nothing is
invented, paraphrased by a model, or padded with external data.

| Source (`source_repo`) | Rows | What it is |
|---|---|---|
| `memory/MEMORY.md` | 436 | Curated facts, decisions, standing rules (580 lines) |
| `memory/daily-logs` | 1,918 | Daily logs 2026-11-03 → 2026-11-07 (day-to-day detail) |
| `docs/FreeEQ8-PAPER` | 88 | FreeEQ8 paper — lock-free dynamic EQ architecture |
| `docs/Therum-PAPER` | 52 | Therum papers (JUCE + iPlug2) |
| `docs/FreeVox8-PAPER` | 46 | FreeVox8 paper |
| `docs/llmbuilder-docs` | 308 | LLMBuilder repo docs (`docs/`, markdown only) |
| `docs/lucid-terminal` | 462 | Lucid docs + READMEs (185 md files; no node_modules / build output) |
| `docs/hub-docs` | 112 | TizWildinEntertainmentHUB docs (markdown only) |
| `devto-article` | 6 | dev.to wake-up call article |
| `threads-queue` | 112 | Threads poster queue — the post text (112 drafts) |
| `itch-listings` | 134 | itch store listings — titles + descriptions (112 items) |
| **Total** | **3,674** | |

Per-source row counts, file lists, source-file SHA-256s and the corpus
SHA-256 are in `manifest.json`. Rebuild any time with:

```
python3 scripts/ops/build_us_corpus.py [--max-pairs 5000]
```

## What is EXCLUDED and why

Gary's hard rule (2026-11-07 ~08:05 PST): **"without pollution of external
datasets in the actual training ever."** The actual training must NEVER be
polluted by external datasets. This corpus contains ONLY our own data.

- **GSM8K** (`datasets/acquired/gsm8k/gsm8k.jsonl`, 500 rows) — **EVALUATION-ONLY.**
  Never in training. Not copied into any trainer-read dir; the trainer script
  (`scripts/training/train_arc_native_candidate.py`) was NOT modified to read
  `datasets/acquired/`.
- **The Stack** (`datasets/acquired/the-stack/`, 0 rows) — **HELD for license
  review.** Not in training at all.
- **All other external datasets** (Hugging Face, etc.) — excluded by the hard
  rule above. No row's `source_repo` names an external dataset (verified: grep
  for `gsm8k`, `the-stack`, `huggingface`, etc. returns zero).
- **Chat transcripts** (Muse conversation store) — **NOT used.** Using Gary's
  words as training data is still Gary's call and it has not been given.
- **Voice notes** (73 mp3s in `~/workspace/your_files/`) — **NOT transcribed in
  this pass.** No Whisper installed, CPU transcription of 73 files would take
  hours, and their substance is already in MEMORY.md + daily logs. See
  Phase 1b below.
- **itch-seo docs** — the `~/workspace/itch-seo/docs/` directory holds no
  markdown files (json/xml/html only), so it contributed 0 rows.

## Evaluation — the design principle

Gary (2026-11-07 ~08:06 PST): testing is offloaded into a **continuous live
running system**. Because external datasets must never pollute training,
evaluation is **Gate v2 benchmark first, then live continuous testing in the
running system (Lucid / the ping server, in real operation)** — the live
system continuously tests and validates itself. Never by mixing external test
datasets into the training data.

## Cleaning (verified)

- **Dedupe:** by normalized prompt (lowercased, whitespace-collapsed). 176
  duplicate-prompt pairs dropped at build time.
- **Secret scan:** every pair scanned before writing (API keys, private-key
  blocks, mnemonics/seed phrases, password/token assignments, bearer tokens,
  credential URLs, JWTs, unlabeled 64-hex strings). **0 pairs dropped for
  secrets.** 16 pairs had an email address or phone number redacted to
  `[email redacted]` / `[phone redacted]`; the pairs were kept.
- **Empties:** pairs with an empty prompt/target, prompt < 12 chars, or
  target < 40 chars are dropped.
- Full dropped-pair log (id-free, prompt prefix + reason only) is in
  `manifest.json` under `cleaning.dropped_log` / `dropped_by_reason`.

## Deferred — Phase 1b: voice-note transcription

The 73 voice-note mp3s (`~/workspace/your_files/voice-message-*.mp3`) are not
in this corpus. Transcribing them needs Whisper on CPU (slow) or the free T4,
and their substance is already covered by MEMORY.md + the daily logs. When
transcription happens, the transcripts go through this same compiler (new
source family, same schema, same secret scan) and the manifest version bumps.
This corpus does not block on it.

## How the LoRA trainer reads this

The LoRA trainer (separate worker) reads `datasets/us_corpus/` directly via
an explicit `--dataset` argument. This corpus is deliberately NOT wired into
`collect_sft_corpus` in `train_arc_native_candidate.py` — that path is the
native-trainer dir list and must stay free of `datasets/acquired/`.

## Honest limits

- 3,674 pairs is inside the 2,000–5,000 credible-first-run target, but below
  the 10k+ the plan wants for the real "us" model. Reaching 10k honestly
  needs: Phase 1b voice-note transcription, Gary's call on chat transcripts
  (the biggest untapped "us" source — his words, his call), and/or more
  doc/code coverage (key source comments, READMEs beyond the ones ingested).
- Prompt phrasing is templated from source topics, not Gary's live phrasing
  (no transcripts). Voice pairs teach Slave's recorded phrasing via MEMORY.md
  and the public posts, not a transcript-derived style model.
- MEMORY.md is a living file — this corpus is a snapshot of it as of build
  time (source SHA-256 in `manifest.json`). Rebuild to pick up new entries.
