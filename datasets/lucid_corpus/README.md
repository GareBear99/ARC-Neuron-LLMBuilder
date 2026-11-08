# Lucid-only SFT corpus — Track A (public instant-reply model)

> **Track A is the ONLY track (Gary, 2026-11-08).** The training is a
> product for users. Track B (private Gary model) is OFF. This corpus is
> the training data. The trainer default is this corpus
> (`datasets/lucid_corpus/lucid_corpus.jsonl`).
> Master catalogue: `datasets/README.md` / `datasets/CATALOGUE.json`.

**Location:** `datasets/lucid_corpus/` (this directory)
**Built by:** `scripts/ops/build_lucid_corpus.py` (run from the repo root)
**Version:** 1 — built 2026-11-07
**Total rows:** 1,650 SFT pairs
**Schema:** `{id, source_repo, capability, domain, prompt, target, tags, promotion_lane, notes}`
— exactly the repo seed schema (as in `datasets/acquired/gsm8k/gsm8k.jsonl`).
Every row has `promotion_lane: "candidate_v2_only"` (new dataset family →
candidate_v2 lane by default, per the v2 class policy).

## What this corpus is

Track A of the two-track 1B plan (see `~/workspace/llmbuilder-1b-training-plan.md`).
The PUBLIC instant-reply model for Lucid users. It knows **Lucid — the product** —
how it works, its features, its commands, its help, its Forge surface. It does
NOT know Gary's private life. A Lucid user asking "how do I use the ls command?"
or "what is the Forge?" gets an answer grounded in Lucid's own docs. A Lucid
user asking about Gary gets nothing — the model was never taught him.

Targets are **verbatim (lightly cleaned) source text** — markdown stripped,
code fences dropped. Prompts are deterministic templates grounded in the
source's own headings / command names. Nothing is invented, paraphrased by a
model, or padded with external data.

| Source (`source_repo`) | Rows | What it is |
|---|---|---|
| `lucid-docs` | 1,552 | Lucid repo markdown docs (185 md files) — README, ARCHITECTURE, COMMANDS, feature docs, backend docs, guides, changelogs |
| `lucid-help` | 96 | Lucid help commands from `src/data/helpData.ts` (48 commands × 2 prompts: "how do I use X?" / "what does X do?") |
| `lucid-forge` | 2 | Forge user-facing surface only — what the Forge is + its three tabs (forge / dual / tail), from `ForgeView.tsx` |
| **Total** | **1,650** | |

Per-source row counts, file lists, source-file SHA-256s and the corpus
SHA-256 are in `manifest.json`. Rebuild any time with:

```
python3 scripts/ops/build_lucid_corpus.py [--max-pairs 10000]
```

## Why this corpus exists — Gary's correction

The original plan (2026-11-07) trained the private "us" corpus — MEMORY.md,
daily logs, Gary's decisions, voice notes — into a model served to Lucid users
(other people) for free. Gary corrected it (2026-11-07 ~19:40 PST): *"why
would we train random shit of mine for other people if were not selling a
product."* He is right. So the plan split in two:

- **Track A (this corpus) — PUBLIC.** Lucid-only product knowledge, for Lucid
  users. This is the instant-reply model.
- **Track B (`datasets/us_corpus/`, 3,674 pairs) — PRIVATE.** Gary's stuff
  (MEMORY.md, daily logs, papers, docs, posts, listings, voice notes,
  transcripts if he approves). For Gary only. Never served to others.

## What is EXCLUDED and why

- **MEMORY.md + daily logs** — Track B only. Gary's private facts, decisions,
  standing rules, day-to-day detail. Not for other people.
- **Gary's decisions / voice notes / chat transcripts** — Track B only.
  Transcripts are Gary's call (not given); voice-note transcription is
  Track B Phase 1b.
- **FreeEQ8 / Therum / FreeVox8 papers** — not Lucid. Gary's other products'
  papers; Track B's product-knowledge pool, not the Lucid model's knowledge.
- **LLMBuilder docs / HUB docs / itch listings / social posts / dev.to** —
  not Lucid. Other products' docs and promotional text.
- **Gary by name** — the builder drops any pair mentioning "Gary" as a person
  (4 rows dropped from `phone-streaming-spike.md`: "Gary has not answered" /
  "(Gary's)" about open technical questions). Benign, but the public model
  has no reason to name Gary. Verified: 0 "gary" mentions in the final corpus.
- **Forge deep design** — the Forge's design philosophy (binary model,
  pink/purple singles, dual unison, tail-as-DNA) lives in MEMORY.md (Track B).
  Track A has only the Forge's user-facing surface (what it is, its tabs).
- **GSM8K** (`datasets/acquired/gsm8k/gsm8k.jsonl`, 500 rows) — **EVALUATION-ONLY.**
  Never in training.
- **The Stack** (`datasets/acquired/the-stack/`, 0 rows) — **HELD for license
  review.** Not in training at all.
- **All other external datasets** (Hugging Face, etc.) — excluded by Gary's
  hard rule (2026-11-07 ~08:05 PST): **"without pollution of external
  datasets in the actual training ever."** This corpus contains ONLY our own
  Lucid data.

## Evaluation — the design principle

Gary (2026-11-07 ~08:06 PST): testing is offloaded into a **continuous live
running system**. Because external datasets must never pollute training,
evaluation is **Gate v2 benchmark first, then live continuous testing in the
running system (Lucid / the ping server, in real operation)** — the live
system continuously tests and validates itself. Never by mixing external test
datasets into the training data.

## Cleaning (verified)

- **Dedupe:** by normalized prompt (lowercased, whitespace-collapsed). 246
  duplicate-prompt pairs dropped at build time.
- **Gary-name filter:** 4 pairs dropped for mentioning "Gary" by name.
- **Secret scan:** every pair scanned before writing (API keys, private-key
  blocks, mnemonics/seed phrases, password/token assignments, bearer tokens,
  credential URLs, JWTs, unlabeled 64-hex strings). **0 pairs dropped for
  secrets.** The 46 "token" hits in the Lucid docs are false positives
  (token-tracking UI, Fernet token as a concept) — no real credentials.
- **Empties:** pairs with an empty prompt/target, prompt < 12 chars, or
  target < 40 chars are dropped.
- Full dropped-pair log (prompt prefix + reason only) is in `manifest.json`
  under `cleaning.dropped_log` / `dropped_by_reason`.

## Honest limits — the gap

- **1,650 rows is below the 2,000–5,000 credible-first-run target** (short by
  ~350 rows) and well below the 10k+ the plan wants for the real model
  (short by ~8,350 rows).
- The Lucid repo holds ~206k words of markdown docs, which yields ~1,556
  section pairs at 2 prompts per section. The docs are the bottleneck, not
  the compiler.
- **To reach 2k:** add code-comment pairs (TypeScript/Python doc comments in
  `src/`, `electron/`, `LUCID-BACKEND/`), and/or a third prompt template per
  section (e.g. "give me an example of X"). Both are honest extensions of
  the same sources, no new data needed.
- **To reach 10k:** NOT reachable from the current Lucid docs alone. It would
  need (a) much more Lucid documentation written, (b) real Lucid user
  questions + answers (the live system generates these over time — the
  continuous-testing loop is the honest source), and/or (c) synthetic Q&A
  generated from the docs (risks inventing content; needs a human review
  gate before it enters training). The 10k number is a goal, not a promise
  from the docs as they stand.
- The Forge is thin in Track A (2 rows) because the Forge has no markdown
  docs — it lives in code + audio. Its user-facing surface is what is here;
  the deep design stays in Track B.
- Help commands cover the 48 commands in `helpData.ts`. Commands added to
  Lucid after this build need a rebuild to enter the corpus.

## How the LoRA trainer reads this

The LoRA trainer reads `datasets/lucid_corpus/` directly via an explicit
`--dataset` argument (same pattern as `datasets/us_corpus/`). This corpus is
deliberately NOT wired into `collect_sft_corpus` in
`train_arc_native_candidate.py` — that path is the native-trainer dir list
and must stay free of `datasets/acquired/`.
