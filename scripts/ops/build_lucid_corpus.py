#!/usr/bin/env python3
"""Build the Track A (Lucid-only, public) SFT corpus for the 1B LoRA fine-tune.

Track A is the PUBLIC instant-reply model for Lucid users. It knows LUCID --
the product -- not Gary's private life. This compiler reads ONLY Lucid public
product knowledge:
  - Lucid repo markdown docs (README, ARCHITECTURE, COMMANDS, feature docs,
    backend docs, guides) -- the product's own documentation.
  - src/data/helpData.ts -- the user-facing help commands (name, syntax,
    description, examples) shown in Lucid's Help panel.
  - src/components/Forge/ForgeView.tsx -- the Forge's user-facing surface
    only (what it is, its tabs). NOT Gary's private Forge design philosophy
    (binary model, tail-as-DNA), which lives in MEMORY.md and is Track B.

Explicitly EXCLUDED from Track A (Gary's correction, 2026-11-07 ~19:40 PST):
"why would we train random shit of mine for other people if were not
selling a product." So Track A contains NO MEMORY.md, NO daily logs, NO
Gary decisions, NO voice notes, NO transcripts, NO private papers, NO
itch listings, NO social posts. Those are Track B (private Gary model,
Gary-only, never served to others) or not training data at all.

Own data ONLY. Gary's hard rule (2026-11-07 ~08:05 PST): the actual training
must NEVER be polluted by external datasets. This compiler reads ONLY our own
Lucid sources and NEVER reads datasets/acquired/ (GSM8K is evaluation-only,
The Stack is held for license review, all other external datasets excluded).

Reuses the pair-generation, cleaning, secret-scan, redact, and dedupe
helpers from scripts/ops/build_us_corpus.py (imported, not duplicated).

Outputs (datasets/lucid_corpus/):
  lucid_corpus.jsonl -- SFT pairs in the repo seed schema
  manifest.json      -- per-source counts + hashes + exclusion statement
  README.md          -- what is in the corpus, what is excluded and why

Schema (exactly as datasets/acquired/gsm8k/gsm8k.jsonl):
  {id, source_repo, capability, domain, prompt, target, tags,
   promotion_lane, notes}
promotion_lane is "candidate_v2_only" for every row (new dataset family).

Targets are VERBATIM (lightly cleaned) source text. Prompts are deterministic
templates grounded in the source's own headings / command names. Nothing is
invented, paraphrased by a model, or padded with external data.

Usage:
  python3 scripts/ops/build_lucid_corpus.py [--out datasets/lucid_corpus]
  [--max-pairs 10000]
Run from the repo root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

# Reuse the us-corpus helpers (pair generation, cleaning, secret scan).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_us_corpus import (  # noqa: E402
    build_doc_sections,
    clean_target,
    norm_prompt,
    redact,
    secret_hit,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
HOME = Path.home()
WORKSPACE = HOME / "workspace"
LUCID = WORKSPACE / "lucid-terminal"

PROMOTION_LANE = "candidate_v2_only"
MAX_PAIRS_DEFAULT = 10000

EXCLUDED = [
    ("MEMORY.md (curated facts, decisions, standing rules)",
     "TRACK B ONLY. Gary's private decisions and standing rules -- not for "
     "other people. Track A is the public Lucid model; it must not know "
     "Gary's private life."),
    ("Daily memory logs (~/memory/2026-11-*.md)",
     "TRACK B ONLY. Day-to-day private detail -- not for other people."),
    ("Gary's decisions / voice notes / chat transcripts",
     "TRACK B ONLY (transcripts + voice notes are Gary's call; voice-note "
     "transcription is Track B Phase 1b). Never in the public model."),
    ("FreeEQ8 / Therum / FreeVox8 papers",
     "Not Lucid. They are Gary's other products' papers -- Track B's "
     "product-knowledge pool, not the Lucid model's knowledge."),
    ("LLMBuilder docs / HUB docs / itch listings / social posts / dev.to",
     "Not Lucid. Other products' docs and promotional text -- not what a "
     "Lucid user asks the instant-reply model about."),
    ("GSM8K (datasets/acquired/gsm8k/gsm8k.jsonl, 500 rows)",
     "EVALUATION-ONLY. Never in training, by Gary's hard rule."),
    ("The Stack (datasets/acquired/the-stack/, 0 rows)",
     "HELD for license review. Not in training at all."),
    ("All other external datasets (Hugging Face, etc.)",
     "Excluded by Gary's hard rule: no pollution of external datasets in "
     "the actual training, ever."),
]


def lucid_md_files():
    """All Lucid markdown docs, excluding build output and vendored code."""
    return sorted(
        p for p in LUCID.rglob("*.md")
        if "node_modules" not in p.parts
        and ".git" not in p.parts
        and "dist" not in p.parts
        and "build" not in p.parts
        and ".luc" not in p.parts
    )


def build_help_commands(path: Path, cap: int):
    """SFT pairs from src/data/helpData.ts command entries.

    Parses the HelpCommand objects (name, syntax, description, examples,
    tags) with regex -- the file is a static literal array, not dynamic code.
    """
    text = path.read_text(encoding="utf-8", errors="ignore")
    # Each command object has: name: 'x', syntax: 'y', description: 'z',
    # examples: [...], tags: [...]. Match them in order.
    cmd_re = re.compile(
        r"name:\s*'([^']+)'\s*,\s*syntax:\s*'([^']+)'\s*,\s*"
        r"description:\s*'([^']+)'\s*,\s*examples:\s*\[(.*?)\]",
        re.S,
    )
    rows = []
    for m in cmd_re.finditer(text):
        name, syntax, desc, examples_raw = m.groups()
        examples = re.findall(r"'([^']+)'", examples_raw)
        ex = "; ".join(examples[:3])
        target = f"{name} ({syntax}): {desc}."
        if ex:
            target += f" Examples: {ex}."
        target = clean_target(target)
        if len(target) < 40:
            continue
        rows.append({
            "source_repo": "lucid-help",
            "capability": "knowledge",
            "domain": "lucid",
            "prompt": f"How do I use the {name} command in Lucid?",
            "target": target,
            "tags": ["lucid_corpus", "knowledge", "lucid", "help"],
            "notes": "Own-data SFT pair from Lucid help data (src/data/helpData.ts); no external data.",
        })
        rows.append({
            "source_repo": "lucid-help",
            "capability": "knowledge",
            "domain": "lucid",
            "prompt": f"What does the {name} command do in Lucid?",
            "target": target,
            "tags": ["lucid_corpus", "knowledge", "lucid", "help"],
            "notes": "Own-data SFT pair from Lucid help data (src/data/helpData.ts); no external data.",
        })
        if len(rows) >= cap:
            break
    return rows


def build_forge_surface(path: Path, cap: int):
    """SFT pairs for the Forge's user-facing surface only.

    From ForgeView.tsx: the header comment (what the Forge is) and the tab
    labels (forge / dual / tail). NOT the deep design philosophy (binary
    model, tail-as-DNA) -- that is Gary's private design in MEMORY.md
    (Track B). Only what a Lucid user sees in the product.
    """
    text = path.read_text(encoding="utf-8", errors="ignore")
    rows = []
    # Header comment: "ForgeView — the Forge (LLMBuilder plugin): where
    # Homunculi are trained."
    hm = re.search(r"ForgeView — the Forge \(LLMBuilder plugin\): ([^\n*]+)", text)
    if hm:
        desc = hm.group(1).strip().rstrip(".")
        target = clean_target(
            f"The Forge is the LLMBuilder plugin in Lucid: {desc}. "
            "It is where Homunculi are trained."
        )
        if len(target) >= 40:
            rows.append({
                "source_repo": "lucid-forge",
                "capability": "knowledge",
                "domain": "lucid",
                "prompt": "What is the Forge in Lucid?",
                "target": target,
                "tags": ["lucid_corpus", "knowledge", "lucid", "forge"],
                "notes": "Own-data SFT pair from Lucid Forge view (user-facing surface only); no external data.",
            })
    # Tab labels: 'forge' | 'dual' | 'tail'
    tm = re.search(r"type ForgeTab\s*=\s*'([^']+)'\s*\|\s*'([^']+)'\s*\|\s*'([^']+)'", text)
    if tm:
        tabs = ", ".join(tm.groups())
        target = clean_target(
            f"The Forge view in Lucid has three tabs: {tabs}. "
            "Forge is the main view, Dual is the dual-unison view, "
            "and Tail is the tail view."
        )
        if len(target) >= 40:
            rows.append({
                "source_repo": "lucid-forge",
                "capability": "knowledge",
                "domain": "lucid",
                "prompt": "What tabs does the Forge have in Lucid?",
                "target": target,
                "tags": ["lucid_corpus", "knowledge", "lucid", "forge"],
                "notes": "Own-data SFT pair from Lucid Forge view (user-facing surface only); no external data.",
            })
    return rows[:cap]


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(REPO_ROOT / "datasets" / "lucid_corpus"))
    ap.add_argument("--max-pairs", type=int, default=MAX_PAIRS_DEFAULT)
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- gather ------------------------------------------------------------
    md_files = lucid_md_files()
    help_path = LUCID / "src" / "data" / "helpData.ts"
    forge_path = LUCID / "src" / "components" / "Forge" / "ForgeView.tsx"

    raw_by_source: dict[str, list[dict]] = {}
    raw_by_source["lucid-docs"] = build_doc_sections(
        md_files, "lucid-docs", "lucid",
        ["lucid_corpus", "work", "lucid"], 100000)
    print(f"  gathered lucid-docs: {len(raw_by_source['lucid-docs'])} raw pairs "
          f"from {len(md_files)} md files")
    raw_by_source["lucid-help"] = build_help_commands(help_path, 100000)
    print(f"  gathered lucid-help: {len(raw_by_source['lucid-help'])} raw pairs")
    raw_by_source["lucid-forge"] = build_forge_surface(forge_path, 100)
    print(f"  gathered lucid-forge: {len(raw_by_source['lucid-forge'])} raw pairs")

    # --- clean: secret-scan, redact, drop empties, dedupe by prompt --------
    # Track A rule (Gary's correction 2026-11-07 ~19:40 PST): the public
    # model must not talk about Gary by name. Drop any pair that mentions
    # "Gary" as a person -- the product docs should teach Lucid, not Gary.
    # (4 rows from phone-streaming-spike.md were dropped for this: they said
    # "Gary has not answered" / "(Gary's)" about open technical questions.
    # Benign, but the public model has no reason to name Gary.)
    gary_re = re.compile(r"\bgary\b", re.I)
    dropped: list[dict] = []
    redacted_count = 0
    seen_prompts: set[str] = set()
    kept: list[dict] = []
    per_source: dict[str, list[dict]] = {}
    for source_repo in ("lucid-docs", "lucid-help", "lucid-forge"):
        for row in raw_by_source[source_repo]:
            prompt = (row["prompt"] or "").strip()
            target = (row["target"] or "").strip()
            if not prompt or not target or len(prompt) < 12 or len(target) < 40:
                dropped.append({"source": source_repo, "reason": "empty-or-too-short",
                                "prompt": prompt[:80]})
                continue
            if gary_re.search(prompt + "\n" + target):
                dropped.append({"source": source_repo, "reason": "mentions-gary-by-name",
                                "prompt": prompt[:80]})
                continue
            hit = secret_hit(prompt + "\n" + target)
            if hit:
                dropped.append({"source": source_repo, "reason": f"secret-scan:{hit}",
                                "prompt": prompt[:80]})
                continue
            new_target = redact(target)
            if new_target != target:
                redacted_count += 1
                target = new_target
            key = norm_prompt(prompt)
            if key in seen_prompts:
                dropped.append({"source": source_repo, "reason": "duplicate-prompt",
                                "prompt": prompt[:80]})
                continue
            seen_prompts.add(key)
            row = dict(row, prompt=prompt, target=target)
            kept.append(row)
            per_source.setdefault(source_repo, []).append(row)
            if len(kept) >= args.max_pairs:
                break
        if len(kept) >= args.max_pairs:
            break

    # --- assign stable ids --------------------------------------------------
    for i, row in enumerate(kept, 1):
        slug = re.sub(r"[^a-z0-9]+", "_", row["source_repo"].lower()).strip("_")
        row["id"] = f"lucid_{slug}_{i:05d}"
        row["promotion_lane"] = PROMOTION_LANE
        kept[i - 1] = {k: row[k] for k in
                       ("id", "source_repo", "capability", "domain", "prompt",
                        "target", "tags", "promotion_lane", "notes")}

    # --- write corpus --------------------------------------------------------
    corpus_path = out_dir / "lucid_corpus.jsonl"
    lines = [json.dumps(r, ensure_ascii=False) for r in kept]
    corpus_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # --- manifest ------------------------------------------------------------
    source_files_map = {
        "lucid-docs": md_files,
        "lucid-help": [help_path],
        "lucid-forge": [forge_path],
    }
    manifest_sources = []
    for source_repo in ("lucid-docs", "lucid-help", "lucid-forge"):
        info = []
        for p in source_files_map[source_repo]:
            if p.is_file():
                info.append({"file": str(p), "bytes": p.stat().st_size,
                             "sha256": file_sha256(p)})
        src_rows = per_source.get(source_repo, [])
        src_text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in src_rows)
        manifest_sources.append({
            "source_repo": source_repo,
            "files": info,
            "rows": len(src_rows),
            "rows_sha256": hashlib.sha256(src_text.encode("utf-8")).hexdigest(),
        })

    manifest = {
        "corpus": "lucid_corpus",
        "version": "1",
        "built_by": "scripts/ops/build_lucid_corpus.py",
        "promotion_lane": PROMOTION_LANE,
        "schema": ["id", "source_repo", "capability", "domain", "prompt",
                   "target", "tags", "promotion_lane", "notes"],
        "total_rows": len(kept),
        "corpus_sha256": hashlib.sha256(corpus_path.read_bytes()).hexdigest(),
        "sources": manifest_sources,
        "excluded": [{"what": w, "why": y} for w, y in EXCLUDED],
        "exclusion_statement": (
            "This corpus contains ONLY Lucid public product knowledge. No "
            "Gary private data is in it: no MEMORY.md, no daily logs, no "
            "Gary decisions, no voice notes, no transcripts, no private "
            "papers, no itch listings, no social posts. GSM8K is "
            "evaluation-only, The Stack is held for license review, and all "
            "other external datasets are excluded by Gary's hard rule "
            "(2026-11-07): no pollution of external datasets in the actual "
            "training, ever. (Gary's correction 2026-11-07 ~19:40 PST: "
            "'why would we train random shit of mine for other people if "
            "were not selling a product' -- the public model must not know "
            "Gary's private stuff.)"),
        "evaluation_principle": (
            "Evaluation is Gate v2 benchmark first, then live continuous "
            "testing in the running system (Lucid / the ping server, in real "
            "operation) -- never by mixing external test datasets into the "
            "training."),
        "cleaning": {
            "dedupe": "by normalized prompt (lowercased, whitespace-collapsed)",
            "dropped_total": len(dropped),
            "dropped_by_reason": {},
            "redacted_pairs": redacted_count,
        },
        "dropped_log": dropped,
    }
    for d in dropped:
        r = d["reason"]
        manifest["cleaning"]["dropped_by_reason"][r] = \
            manifest["cleaning"]["dropped_by_reason"].get(r, 0) + 1
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"\nWROTE {corpus_path} : {len(kept)} rows")
    for s in manifest_sources:
        print(f"  {s['source_repo']}: {s['rows']}")
    print(f"DROPPED {len(dropped)} ({manifest['cleaning']['dropped_by_reason']})")
    print(f"REDACTED {redacted_count} pairs (email/phone)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
