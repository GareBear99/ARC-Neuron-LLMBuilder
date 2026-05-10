from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "dist"
DIST.mkdir(exist_ok=True)
OUT = DIST / "cognition-core-release-bundle.zip"

# Production release bundles should be deterministic source capsules, not
# recursive snapshots of generated candidates, caches, prior bundles, or embedded
# ecosystem checkouts. The full ecosystem can be distributed separately as an
# archive attachment when intentionally requested.
INCLUDE_DIRS = {
    ".github",
    "adapters",
    "arc_core",
    "arc_neuron_small",
    "arc_neuron_tokenizer",
    "arc_tiny",
    "benchmarks",
    "configs",
    "data",
    "data_manifest",
    "datasets",
    "docs",
    "examples",
    "integrations",
    "manifests",
    "mcp",
    "ops",
    "repo-metadata",
    "runtime",
    "schemas",
    "scorers",
    "scripts",
    "specs",
    "templates",
    "tests",
}

INCLUDE_ROOT_FILES = {
    ".editorconfig",
    ".env.direct-runtime.example",
    ".gitignore",
    "ARCHITECTURE.md",
    "CHANGELOG.md",
    "CHANGELOG_v2.1.0.md",
    "CITATION.cff",
    "CODEOWNERS",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "Dockerfile",
    "ECOSYSTEM.md",
    "FAQ.md",
    "GLOSSARY.md",
    "GOVERNANCE_DOCTRINE.md",
    "LICENSE",
    "LICENSE_TRANSITIONAL_NOTICE.md",
    "Makefile",
    "MODEL_CARD_v10_wave4.md",
    "PROOF.md",
    "QUICKSTART.md",
    "README.md",
    "RELEASE_NOTES_v1.0.0.md",
    "ROADMAP.md",
    "SECURITY.md",
    "SUPPORT.md",
    "SYSTEM_STACK_MANIFEST.json",
    "USAGE.md",
    "_config.yml",
    "build_v11_3_exemplar.py",
    "cognition_lab.py",
    "docker-compose.local-backends.yml",
    "env.direct-runtime.example",
    "index.md",
    "pyproject.toml",
    "requirements.txt",
    "rubric.py",
    "ARC_Neuron_Model_Governance_Grinder_Plan.md",
}

SKIP_DIRS = {"__pycache__", ".pytest_cache", "dist", ".git"}
SKIP_SUFFIXES = {".pyc", ".pyo"}


def should_include(path: Path) -> bool:
    if not path.is_file():
        return False
    rel = path.relative_to(ROOT)
    if any(part in SKIP_DIRS for part in rel.parts):
        return False
    if path.suffix in SKIP_SUFFIXES:
        return False
    if len(rel.parts) == 1:
        return rel.name in INCLUDE_ROOT_FILES
    return rel.parts[0] in INCLUDE_DIRS


def main() -> None:
    count = 0
    with ZipFile(OUT, "w", compression=ZIP_DEFLATED) as zf:
        for path in sorted(ROOT.rglob("*")):
            if should_include(path):
                zf.write(path, path.relative_to(ROOT))
                count += 1
    print(json.dumps({"ok": True, "bundle": str(OUT.relative_to(ROOT)), "files": count}, indent=2))


if __name__ == "__main__":
    main()
