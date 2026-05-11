"""Repository MCP server scaffold."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable


def repo_read_tree(path: str = ".", max_depth: int = 4) -> dict:
    root = Path(path)
    items = []
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if len(rel.parts) <= max_depth:
            items.append(str(rel) + ("/" if p.is_dir() else ""))
    return {"tree": sorted(items)}


def repo_search(query: str, include: Iterable[str] = ("*.py", "*.md", "*.json"), path: str = ".") -> dict:
    root = Path(path)
    matches = []
    for pattern in include:
        for p in root.rglob(pattern):
            if not p.is_file():
                continue
            try:
                for lineno, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
                    if query.lower() in line.lower():
                        matches.append({"path": str(p), "line": lineno, "text": line.strip()[:300]})
            except Exception:
                continue
    return {"matches": matches}


def repo_read_file(path: str) -> dict:
    p = Path(path)
    return {"path": str(p), "content": p.read_text(encoding="utf-8", errors="ignore")}


def repo_create_patch(target_path: str, replacement: str, patch_path: str = "mcp/sandboxes/patches/generated.patch") -> dict:
    out = Path(patch_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    patch = f"--- a/{target_path}\n+++ b/{target_path}\n@@ GENERATED PATCH PLACEHOLDER @@\n{replacement}\n"
    out.write_text(patch, encoding="utf-8")
    return {"patch_path": str(out), "status": "created"}
