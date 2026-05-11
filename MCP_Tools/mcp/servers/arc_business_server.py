"""Business workflow MCP server scaffold. Draft-only by design."""
from __future__ import annotations

from pathlib import Path


def business_extract_sop(collection_path: str, topic: str) -> dict:
    sources = []
    steps = []
    for p in Path(collection_path).rglob("*.md") if Path(collection_path).exists() else []:
        text = p.read_text(encoding="utf-8", errors="ignore")
        if topic.lower() in text.lower():
            sources.append(str(p))
            steps.extend([line.strip("- 0123456789.") for line in text.splitlines() if line.strip().startswith(("-", "1.", "2.", "3."))][:5])
    return {"topic": topic, "steps": steps, "sources": sources}


def business_generate_ticket_response(ticket: str, sources: list[str] | None = None) -> dict:
    return {
        "draft": f"Thanks for reaching out. Based on the available internal sources, this needs review: {ticket}",
        "sources": sources or [],
        "confidence": 0.5 if not sources else 0.75,
        "requires_human_review": True,
        "external_send_allowed": False,
    }
