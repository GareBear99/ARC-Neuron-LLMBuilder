#!/usr/bin/env python3
"""Validate the public SEO/indexing handoff files for ARC-Neuron.

This script does not contact search engines. It verifies that the repository
contains the metadata, topic, and public-indexing files needed before pushing to
GitHub and enabling Pages.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = [
    "docs/SEO_INDEXING_PLAYBOOK.md",
    "docs/seo_metadata.jsonld",
    "repo-metadata/repository_topics.txt",
    "repo-metadata/repository_description.txt",
    "repo-metadata/social_preview_prompt.md",
    "robots.txt",
    "index.md",
    "_config.yml",
]
REQUIRED_TOPICS = {
    "gguf",
    "local-ai",
    "llm-builder",
    "governed-ai",
    "model-governance",
    "ai-provenance",
    "offline-ai",
    "sovereign-ai",
    "model-promotion",
    "knowledge-preservation",
}
REQUIRED_README_PHRASES = [
    "Governed local AI cognition lab",
    "GGUF-oriented model candidates",
    "receipts, rollback, provenance",
    "regression-safe gates",
    "v11.3 / wave5 materials are treated as a staging candidate",
]


def fail(msg: str) -> None:
    print(f"[seo-validate] ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    missing = [path for path in REQUIRED_FILES if not (ROOT / path).exists()]
    if missing:
        fail("missing files: " + ", ".join(missing))

    topics = set((ROOT / "repo-metadata/repository_topics.txt").read_text().split())
    missing_topics = sorted(REQUIRED_TOPICS - topics)
    if missing_topics:
        fail("missing required topics: " + ", ".join(missing_topics))

    desc = (ROOT / "repo-metadata/repository_description.txt").read_text().strip()
    if len(desc) < 80 or len(desc) > 280:
        fail("repository description should be concise but descriptive, ideally 80-280 chars")

    readme = (ROOT / "README.md").read_text()
    for phrase in REQUIRED_README_PHRASES:
        if phrase not in readme:
            fail(f"README missing phrase: {phrase}")

    payload = json.loads((ROOT / "docs/seo_metadata.jsonld").read_text())
    if payload.get("@type") != "SoftwareSourceCode":
        fail("JSON-LD @type must be SoftwareSourceCode")
    if "ARC-Neuron" not in payload.get("name", ""):
        fail("JSON-LD name must identify ARC-Neuron")
    if "codeRepository" not in payload:
        fail("JSON-LD missing codeRepository")

    print(json.dumps({
        "ok": True,
        "required_files": len(REQUIRED_FILES),
        "topics": sorted(topics),
        "description_length": len(desc),
        "jsonld_type": payload.get("@type"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
