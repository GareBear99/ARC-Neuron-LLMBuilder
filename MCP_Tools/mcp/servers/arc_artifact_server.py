"""Artifact/release MCP server scaffold."""
from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path


def artifact_verify_hashes(package_path: str) -> dict:
    p = Path(package_path)
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    return {"status": "verified", "sha256": h, "path": str(p)}


def artifact_package_model(candidate: str, files: list[str], output_path: str) -> dict:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for file in files:
            p = Path(file)
            if p.exists() and p.is_file():
                z.write(p, arcname=p.name)
    return {"package_path": str(out), "candidate": candidate, "status": "created"}
