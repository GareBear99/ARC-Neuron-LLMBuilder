"""Memory/archive MCP server scaffold."""
from __future__ import annotations

import json
from pathlib import Path


def memory_search_receipts(query: str, receipt_dir: str = "mcp/receipts", limit: int = 20) -> dict:
    root = Path(receipt_dir)
    matches = []
    if root.exists():
        for p in root.glob("*.json"):
            text = p.read_text(encoding="utf-8", errors="ignore")
            if query.lower() in text.lower():
                try:
                    obj = json.loads(text)
                    action = obj.get("action", "unknown")
                except Exception:
                    action = "unknown"
                matches.append({"receipt_path": str(p), "action": action})
                if len(matches) >= limit:
                    break
    return {"matches": matches}
