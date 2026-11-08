#!/usr/bin/env python3
"""Build the "us" SFT corpus for the LLMBuilder 1B LoRA fine-tune.

Own data ONLY. Gary's hard rule (2026-11-07 ~08:05 PST): the actual training
must NEVER be polluted by external datasets. This compiler reads ONLY our own
sources (MEMORY.md, daily memory logs, our repo docs/papers, our public
posts/listings) and NEVER reads datasets/acquired/ (GSM8K is evaluation-only,
The Stack is held for license review, all other external datasets excluded).

Design principle (Gary, 2026-11-07 ~08:06 PST): testing is offloaded to the
continuous live running system (Lucid / the ping server, in real operation).
Evaluation is Gate v2 benchmark first, then live continuous testing in the
running system -- never by mixing external test datasets into training.

Outputs (datasets/us_corpus/):
  us_corpus.jsonl  -- SFT pairs in the repo seed schema
  manifest.json   -- per-source counts + hashes + exclusion statement
  README.md       -- what is in the corpus, what is excluded and why

Schema (exactly as datasets/acquired/gsm8k/gsm8k.jsonl):
  {id, source_repo, capability, domain, prompt, target, tags,
   promotion_lane, notes}
promotion_lane is "candidate_v2_only" for every row (new dataset family).

Pair types (from llmbuilder-1b-training-plan.md section 3):
  (a) knowledge -- "what did we decide about X?" -> the decision/fact
  (b) voice     -- prompts phrased the way Gary phrases them -> answers in
                  Slave's recorded phrasing (MEMORY.md is written in it)
  (c) work      -- "what does X do / how does Y work?" -> the doc answer

Targets are VERBATIM (lightly cleaned) source text. Prompts are deterministic
templates grounded in the source's own headings / bold topics / titles.
Nothing is invented, paraphrased by a model, or padded with external data.

Voice notes (73 mp3s in ~/workspace/your_files/) are NOT transcribed in this
pass: no Whisper installed, CPU transcription would take hours, and their
substance is already in MEMORY.md + daily logs. Transcription is deferred
Phase 1b (see datasets/us_corpus/README.md). Chat transcripts are NOT used:
that is still Gary's call and it has not been given.

Usage:
  python3 scripts/ops/build_us_corpus.py [--out datasets/us_corpus]
  [--max-pairs 5000]
Run from the repo root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HOME = Path.home()
WORKSPACE = HOME / "workspace"

PROMOTION_LANE = "candidate_v2_only"
MAX_PAIRS_DEFAULT = 5000

# ---------------------------------------------------------------------------
# Cleaning helpers
# ---------------------------------------------------------------------------

_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MD_IMG_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_MD_CODE_RE = re.compile(r"`([^`]+)`")
_MD_EM_RE = re.compile(r"(?<!\w)_(.+?)_(?!\w)")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean_inline(text: str) -> str:
    """Strip light markdown so targets read as plain prose."""
    text = _HTML_COMMENT_RE.sub("", text)
    text = _MD_IMG_RE.sub("", text)
    text = _MD_LINK_RE.sub(r"\1", text)
    text = _MD_BOLD_RE.sub(r"\1", text)
    text = _MD_CODE_RE.sub(r"\1", text)
    text = _MD_EM_RE.sub(r"\1", text)
    text = _HTML_TAG_RE.sub("", text)
    text = text.replace("*", "")
    return _WS_RE.sub(" ", text).strip()


def strip_code_fences(text: str) -> str:
    out, in_fence = [], False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(line)
    return "\n".join(out)


def clean_target(text: str, max_chars: int = 2500) -> str:
    """Plain-text target: drop fences/markers, collapse whitespace, cap."""
    text = strip_code_fences(text)
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("[BEGIN") or s.startswith("[END"):
            continue
        if s.startswith("<!--"):
            continue
        lines.append(s)
    text = clean_inline(" ".join(lines))
    if len(text) > max_chars:
        cut = text[:max_chars]
        # Prefer a sentence boundary; fall back to a word boundary.
        for sep in (". ", "! ", "? ", "; "):
            idx = cut.rfind(sep)
            if idx > max_chars * 0.6:
                cut = cut[: idx + 1]
                break
        else:
            idx = cut.rfind(" ")
            if idx > max_chars * 0.8:
                cut = cut[:idx]
        text = cut.strip()
    return text


def norm_prompt(prompt: str) -> str:
    return _WS_RE.sub(" ", prompt.strip().lower())


# ---------------------------------------------------------------------------
# Secret scan
# ---------------------------------------------------------------------------
# Patterns are matched against prompt+target. A hit DROPS the pair (the pair
# is logged by id + pattern name only -- never the matched value).
# Deliberately NOT flagged: SHA-256 file checksums labelled as such in the
# text (public release integrity hashes), referral code 7LU3P6 (public by
# design -- Gary publishes it), connector attempt UUIDs, GitHub usernames.

SECRET_PATTERNS = [
    ("private-key-block", re.compile(r"BEGIN (RSA |EC |OPENSSH |PGP )?PRIVATE KEY", re.I)),
    ("private-key-mention-value", re.compile(r"private[_ -]?key\s*[:=]\s*\S{16,}", re.I)),
    ("mnemonic-phrase", re.compile(r"\bmnemonic\b.{0,80}\b([a-z]{3,}\s+){11,}[a-z]{3,}\b", re.I)),
    ("seed-phrase", re.compile(r"seed phrase\s*[:=]\s*\S+", re.I)),
    ("api-key-sk", re.compile(r"\bsk-[A-Za-z0-9]{16,}\b")),
    ("api-key-ghp", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("api-key-aws", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("api-key-hf", re.compile(r"\bhf_[A-Za-z0-9]{20,}\b")),
    ("api-key-slack", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("api-key-generic", re.compile(r"\b(api[_-]?key|apikey)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}", re.I)),
    ("password-assign", re.compile(r"\bpassword\s*[:=]\s*['\"]?\S{4,}", re.I)),
    ("bearer-token", re.compile(r"\bearer\s+[A-Za-z0-9_\-\.]{16,}", re.I)),
    ("token-assign", re.compile(r"\b(access[_-]?token|auth[_-]?token|secret[_-]?token)\s*[:=]\s*['\"]?\S{8,}", re.I)),
    ("credential-url", re.compile(r"://[^/\s]*:[^@/\s]+@")),
    ("jwt-like", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")),
]
# NOTE: email addresses and phone numbers are NOT in SECRET_PATTERNS -- they
# are redacted (see REDACT_PATTERNS), not dropped, so the pair stays usable.

# A bare 64-hex string is dropped UNLESS the surrounding text labels it as a
# public checksum (SHA-256 / checksum / hash of a release file).
HEX64_RE = re.compile(r"\b[0-9a-f]{64}\b", re.I)
HEX64_OK_RE = re.compile(r"(sha-?256|checksum|file hash|integrity hash)", re.I)

# Emails / phones are redacted (not dropped) -- they are contact details,
# not credentials, and the pair is still usable without them.
REDACT_PATTERNS = [
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[email redacted]"),
    (re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s])\d{3}[-.\s]\d{4}(?!\d)"), "[phone redacted]"),
]


def secret_hit(text: str):
    """Return the name of the first secret pattern hit, or None."""
    for name, pat in SECRET_PATTERNS:
        if pat.search(text):
            return name
    for m in HEX64_RE.finditer(text):
        window = text[max(0, m.start() - 120): m.end() + 120]
        if not HEX64_OK_RE.search(window):
            return "unlabeled-hex64"
    return None


def redact(text: str) -> str:
    for pat, repl in REDACT_PATTERNS:
        text = pat.sub(repl, text)
    return text


# ---------------------------------------------------------------------------
# Markdown parsing
# ---------------------------------------------------------------------------

BULLET_RE = re.compile(r"^(\s*)[-*]\s+(.*)$")
HEADING_RE = re.compile(r"^(#{1,4})\s+(.*)$")


def parse_markdown_units(path: Path):
    """Yield (heading, bullet_text) for every bullet, merging continuations.

    Also yields section bodies separately via parse_sections().
    """
    text = path.read_text(encoding="utf-8", errors="ignore")
    heading = ""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        hm = HEADING_RE.match(line)
        if hm:
            heading = clean_inline(hm.group(2))
            i += 1
            continue
        bm = BULLET_RE.match(line)
        if bm:
            parts = [bm.group(2)]
            i += 1
            # Merge indented continuation lines until a blank line, a new
            # bullet, or a heading.
            while i < len(lines):
                nxt = lines[i]
                if not nxt.strip():
                    break
                if HEADING_RE.match(nxt) or BULLET_RE.match(nxt):
                    break
                if nxt.startswith(" ") or nxt.startswith("\t"):
                    parts.append(nxt.strip())
                    i += 1
                else:
                    break
            yield heading, " ".join(parts)
            continue
        i += 1


def parse_sections(path: Path):
    """Yield (heading, body_text) for each ## / ### section with real prose."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    text = strip_code_fences(text)
    sections = []
    heading, body = None, []
    for line in text.splitlines():
        hm = HEADING_RE.match(line)
        if hm and len(hm.group(1)) in (2, 3):
            if heading is not None:
                sections.append((heading, "\n".join(body)))
            heading, body = clean_inline(hm.group(2)), []
        elif heading is not None:
            body.append(line)
    if heading is not None:
        sections.append((heading, "\n".join(body)))
    return sections


def bullet_topic(bullet: str, heading: str) -> str | None:
    """Short topic anchor from the bullet's own bold span, else its lead words."""
    m = re.search(r"\*\*(.+?)\*\*", bullet)
    if m:
        t = clean_inline(m.group(1)).strip(" :—-")
        if 3 <= len(t) <= 80:
            return t
    # A topical (non-date) heading works as the anchor.
    if heading and not re.search(r"\b20\d\d[-/]\d\d[-/]\d\d\b", heading) \
            and len(heading) <= 60 and heading.lower() not in ("facts",):
        return heading
    words = clean_inline(bullet).split()
    if len(words) >= 4:
        t = " ".join(words[:5]).strip(" ,:;—-")
        if len(t) >= 12:
            return t
    return None


DECISION_RE = re.compile(
    r"\b(decided|decision|cancelled|approved|standing rule|rule:|gary said|"
    r"do not|don't|never|must|only|blocked|confirmed)\b", re.I)


def bullet_pairs(bullet: str, heading: str):
    """Up to 2 (prompt_template, target) pairs for one memory bullet."""
    target = clean_target(bullet)
    if len(target) < 80:
        return []
    topic = bullet_topic(bullet, heading)
    if not topic:
        return []
    is_decision = bool(DECISION_RE.search(bullet))
    if is_decision:
        prompts = [
            f"What did we decide about {topic}?",
            f"What should I know about {topic}?",
        ]
    else:
        prompts = [
            f"What do we know about {topic}?",
            f"Tell me about {topic}.",
        ]
    return [(p, target) for p in prompts]


def section_pairs(heading: str, body: str):
    """Up to 3 (prompt, target) pairs for one doc section.

    The third template ("Explain {h} in Lucid.") was added 2026-11-08 to
    close the lucid_corpus gap to 2,000+ rows for the Track A first run
    (Gary, 2026-11-08 ~11:48 PST — "get the first section of the plan
    done"). Same source, same verbatim target, a third prompt phrasing —
    legitimate augmentation, not a duplicate (same fact under a new
    phrasing, as build_memory_bullets already treats it)."""
    target = clean_target(body)
    if len(target) < 300:
        return []
    h = heading.strip().strip(":")
    if len(h) < 3 or len(h) > 90:
        return []
    return [
        (f"What does {h} cover?", target),
        (f"How does {h} work?", target),
        (f"Explain {h} in Lucid.", target),
    ]


# ---------------------------------------------------------------------------
# Source builders -- each returns a list of raw pair dicts (no ids yet)
# ---------------------------------------------------------------------------

def build_memory_bullets(files, source_repo: str, capability: str,
                         domain: str, tags, cap: int):
    rows, seen_pairs = [], set()
    for path in files:
        for heading, bullet in parse_markdown_units(path):
            for prompt, target in bullet_pairs(bullet, heading):
                # Dedupe by (prompt, target): the same fact under two prompt
                # phrasings is legitimate augmentation, not a duplicate.
                if (prompt, target) in seen_pairs:
                    continue
                seen_pairs.add((prompt, target))
                rows.append({
                    "source_repo": source_repo,
                    "capability": capability,
                    "domain": domain,
                    "prompt": prompt,
                    "target": target,
                    "tags": tags,
                    "notes": f"Own-data SFT pair from {path.name}; no external data.",
                })
                if len(rows) >= cap:
                    return rows
    return rows


def build_doc_sections(files, source_repo: str, domain: str, tags, cap: int):
    rows, seen_pairs = [], set()
    for path in sorted(files):
        if not path.is_file():
            continue
        for heading, body in parse_sections(path):
            for prompt, target in section_pairs(heading, body):
                if (prompt, target) in seen_pairs:
                    continue
                seen_pairs.add((prompt, target))
                rows.append({
                    "source_repo": source_repo,
                    "capability": "work",
                    "domain": domain,
                    "prompt": prompt,
                    "target": target,
                    "tags": tags,
                    "notes": f"Own-data SFT pair from {path.name}; no external data.",
                })
                if len(rows) >= cap:
                    return rows
    return rows


def build_threads_queue(queue_dir: Path, cap: int):
    rows = []
    for name in sorted(queue_dir.glob("*.json")):
        try:
            d = json.loads(name.read_text(encoding="utf-8"))
        except Exception:
            continue
        text = (d.get("text") or "").strip()
        if len(text) < 40:
            continue
        topic = re.sub(r"https?://\S+|#\w+", "", text).strip()
        topic = _WS_RE.sub(" ", topic)
        topic = " ".join(topic.split()[:6]).strip(" ,:;—-") or "our work"
        rows.append({
            "source_repo": "threads-queue",
            "capability": "voice",
            "domain": "social",
            "prompt": f"Write a Threads post about {topic}.",
            "target": text,
            "tags": ["us_corpus", "voice", "threads"],
            "notes": "Own-data SFT pair from Threads poster queue; no external data.",
        })
        if len(rows) >= cap:
            break
    return rows


def build_itch_listings(path: Path, cap: int):
    rows = []
    data = json.loads(path.read_text(encoding="utf-8"))
    for item in data.get("items", []):
        name = (item.get("name") or "").strip()
        desc = clean_target(item.get("description") or "")
        kind = item.get("kind") or "item"
        category = item.get("category") or "game asset"
        price_type = item.get("priceType") or ""
        price = item.get("price")
        price_bits = f", {price_type}" + (f" ${price}" if price else "")
        if len(desc) >= 40:
            rows.append({
                "source_repo": "itch-listings",
                "capability": "knowledge",
                "domain": "itch-listings",
                "prompt": f"What is {name}?",
                "target": f"{desc} ({name} is a {kind} in {category}{price_bits} on itch.)",
                "tags": ["us_corpus", "knowledge", "itch"],
                "notes": "Own-data SFT pair from itch store listings; no external data.",
            })
            rows.append({
                "source_repo": "itch-listings",
                "capability": "voice",
                "domain": "itch-listings",
                "prompt": f"Describe {name} from our itch store.",
                "target": desc,
                "tags": ["us_corpus", "voice", "itch"],
                "notes": "Own-data SFT pair from itch store listings; no external data.",
            })
        else:
            rows.append({
                "source_repo": "itch-listings",
                "capability": "knowledge",
                "domain": "itch-listings",
                "prompt": f"What is {name} on our itch store?",
                "target": f"{name} is a {kind} in {category}{price_bits} on our itch store (GareBearProductionz).",
                "tags": ["us_corpus", "knowledge", "itch"],
                "notes": "Own-data SFT pair from itch store listings; no external data.",
            })
        if len(rows) >= cap:
            break
    return rows


def build_devto(path: Path, cap: int):
    rows = []
    for heading, body in parse_sections(path):
        for prompt, target in section_pairs(heading, body):
            rows.append({
                "source_repo": "devto-article",
                "capability": "voice",
                "domain": "devto",
                "prompt": prompt,
                "target": target,
                "tags": ["us_corpus", "voice", "devto"],
                "notes": "Own-data SFT pair from dev.to wake-up article; no external data.",
            })
            if len(rows) >= cap:
                return rows
    # Whole-article fallback if sections were too thin.
    if not rows:
        target = clean_target(path.read_text(encoding="utf-8", errors="ignore"))
        if len(target) >= 300:
            rows.append({
                "source_repo": "devto-article",
                "capability": "voice",
                "domain": "devto",
                "prompt": "What is the dev.to wake-up call article about?",
                "target": target,
                "tags": ["us_corpus", "voice", "devto"],
                "notes": "Own-data SFT pair from dev.to wake-up article; no external data.",
            })
    return rows


# ---------------------------------------------------------------------------
# Main build
# ---------------------------------------------------------------------------

SOURCE_PLAN = [
    # (source_repo, builder-kind, domain, tags, cap)
    ("memory/MEMORY.md", "memory", "us-facts", ["us_corpus", "knowledge", "memory"], 450),
    ("memory/daily-logs", "memory", "us-facts", ["us_corpus", "knowledge", "memory"], 2000),
    ("docs/FreeEQ8-PAPER", "docs", "freeeq8", ["us_corpus", "work", "freeeq8"], 150),
    ("docs/Therum-PAPER", "docs", "therum", ["us_corpus", "work", "therum"], 150),
    ("docs/FreeVox8-PAPER", "docs", "freevox8", ["us_corpus", "work", "freevox8"], 100),
    ("docs/llmbuilder-docs", "docs", "llmbuilder", ["us_corpus", "work", "llmbuilder"], 500),
    ("docs/lucid-terminal", "docs", "lucid", ["us_corpus", "work", "lucid"], 500),
    ("docs/hub-docs", "docs", "hub", ["us_corpus", "work", "hub"], 200),
    ("devto-article", "devto", "devto", ["us_corpus", "voice", "devto"], 20),
    ("threads-queue", "threads", "social", ["us_corpus", "voice", "threads"], 112),
    ("itch-listings", "itch", "itch-listings", ["us_corpus", "knowledge", "itch"], 250),
]

EXCLUDED = [
    ("GSM8K (datasets/acquired/gsm8k/gsm8k.jsonl, 500 rows)",
     "EVALUATION-ONLY. Never in training, by Gary's hard rule."),
    ("The Stack (datasets/acquired/the-stack/, 0 rows)",
     "HELD for license review. Not in training at all."),
    ("All other external datasets (Hugging Face, etc.)",
     "Excluded by Gary's hard rule: no pollution of external datasets in the actual training, ever."),
    ("Chat transcripts (Muse conversation store)",
     "NOT used: using Gary's words as training data is still Gary's call and it has not been given."),
    ("Voice notes (73 mp3s in ~/workspace/your_files/)",
     "NOT transcribed in this pass (no Whisper installed; CPU transcription would take hours; substance already in MEMORY.md + daily logs). Deferred Phase 1b."),
]


def source_files():
    """Resolve the on-disk source files for each source_repo label."""
    return {
        "memory/MEMORY.md": [HOME / "MEMORY.md"],
        "memory/daily-logs": [HOME / "memory" / f"2026-11-0{d}.md" for d in (3, 4, 5, 6, 7)],
        "docs/FreeEQ8-PAPER": [WORKSPACE / "FreeEQ8" / "PAPER.md"],
        "docs/Therum-PAPER": [WORKSPACE / "Therum_JUCE-Plugin" / "PAPER.md",
                              WORKSPACE / "Therum_iPlug2-Plugin" / "PAPER.md"],
        "docs/FreeVox8-PAPER": [WORKSPACE / "FreeVox8" / "PAPER.md"],
        "docs/llmbuilder-docs": sorted((REPO_ROOT / "docs").glob("*.md")),
        "docs/lucid-terminal": sorted(
            p for p in (WORKSPACE / "lucid-terminal").rglob("*.md")
            if "node_modules" not in p.parts and ".git" not in p.parts
            and "dist" not in p.parts and "build" not in p.parts),
        "docs/hub-docs": sorted((WORKSPACE / "TizWildinEntertainmentHUB" / "docs").glob("*.md")),
        "docs/itch-seo": sorted((WORKSPACE / "itch-seo" / "docs").glob("*.md")),
        "devto-article": [WORKSPACE / "devto-wakeup-call.md"],
        "threads-queue": [WORKSPACE / "threads-poster" / "queue"],
        "itch-listings": [WORKSPACE / "itch-seo" / "all_items.json"],
    }


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(REPO_ROOT / "datasets" / "us_corpus"))
    ap.add_argument("--max-pairs", type=int, default=MAX_PAIRS_DEFAULT)
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    files = source_files()

    # --- gather (priority order = SOURCE_PLAN order) -----------------------
    raw_by_source: dict[str, list[dict]] = {}
    for source_repo, kind, domain, tags, cap in SOURCE_PLAN:
        src = files[source_repo]
        if kind == "memory":
            rows = build_memory_bullets(src, source_repo, "knowledge", domain, tags, cap)
        elif kind == "docs":
            rows = build_doc_sections(src, source_repo, domain, tags, cap)
        elif kind == "devto":
            rows = build_devto(src[0], cap)
        elif kind == "threads":
            rows = build_threads_queue(src[0], cap)
        elif kind == "itch":
            rows = build_itch_listings(src[0], cap)
        else:
            rows = []
        raw_by_source[source_repo] = rows
        print(f"  gathered {source_repo}: {len(rows)} raw pairs")

    # --- clean: secret-scan, redact, drop empties, dedupe by prompt --------
    dropped: list[dict] = []
    redacted_count = 0
    seen_prompts: set[str] = set()
    kept: list[dict] = []
    per_source: dict[str, list[dict]] = {}
    for source_repo, _, _, _, _ in SOURCE_PLAN:
        for row in raw_by_source[source_repo]:
            prompt = (row["prompt"] or "").strip()
            target = (row["target"] or "").strip()
            if not prompt or not target or len(prompt) < 12 or len(target) < 40:
                dropped.append({"source": source_repo, "reason": "empty-or-too-short",
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
        row["id"] = f"us_{slug}_{i:05d}"
        row["promotion_lane"] = PROMOTION_LANE
        # Canonical key order per the seed schema.
        kept[i - 1] = {k: row[k] for k in
                       ("id", "source_repo", "capability", "domain", "prompt",
                        "target", "tags", "promotion_lane", "notes")}

    # --- write corpus --------------------------------------------------------
    corpus_path = out_dir / "us_corpus.jsonl"
    lines = [json.dumps(r, ensure_ascii=False) for r in kept]
    corpus_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # --- manifest ------------------------------------------------------------
    manifest_sources = []
    for source_repo, _, _, _, _ in SOURCE_PLAN:
        src_files = files[source_repo]
        info = []
        for p in src_files:
            if p.is_file():
                info.append({"file": str(p), "bytes": p.stat().st_size,
                             "sha256": file_sha256(p)})
            elif p.is_dir():
                info.append({"file": str(p), "note": "directory; per-file list omitted"})
        src_rows = per_source.get(source_repo, [])
        src_text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in src_rows)
        manifest_sources.append({
            "source_repo": source_repo,
            "files": info,
            "rows": len(src_rows),
            "rows_sha256": hashlib.sha256(src_text.encode("utf-8")).hexdigest(),
        })

    manifest = {
        "corpus": "us_corpus",
        "version": "1",
        "built_by": "scripts/ops/build_us_corpus.py",
        "promotion_lane": PROMOTION_LANE,
        "schema": ["id", "source_repo", "capability", "domain", "prompt",
                   "target", "tags", "promotion_lane", "notes"],
        "total_rows": len(kept),
        "corpus_sha256": hashlib.sha256(corpus_path.read_bytes()).hexdigest(),
        "sources": manifest_sources,
        "excluded": [{"what": w, "why": y} for w, y in EXCLUDED],
        "exclusion_statement": (
            "This corpus contains ONLY our own data. No external dataset is in "
            "it: GSM8K is evaluation-only, The Stack is held for license review, "
            "and all other external datasets are excluded by Gary's hard rule "
            "(2026-11-07): no pollution of external datasets in the actual "
            "training, ever. Chat transcripts were not used (Gary's call, not "
            "given). Voice-note mp3s were not transcribed in this pass (deferred "
            "Phase 1b)."),
        "evaluation_principle": (
            "Evaluation is Gate v2 benchmark first, then live continuous testing "
            "in the running system (Lucid / the ping server, in real operation) "
            "-- never by mixing external test datasets into the training."),
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
