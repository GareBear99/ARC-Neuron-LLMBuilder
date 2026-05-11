"""Receipt writer for ARC-Neuron MCP actions."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


class ReceiptWriter:
    def __init__(self, root: str | Path = ".") -> None:
        self.root = Path(root)
        self.receipt_dir = self.root / "mcp" / "receipts"
        self.receipt_dir.mkdir(parents=True, exist_ok=True)

    def write_receipt(
        self,
        action: str,
        tool: str,
        risk_class: str,
        policy_result: str,
        status: str,
        input_payload: Any,
        output_payload: Any,
        evidence: Optional[Iterable[str]] = None,
        rollback_path: str = "",
        notes: str = "",
    ) -> Path:
        now = datetime.now(timezone.utc).isoformat()
        receipt_id = hashlib.sha256(f"{now}:{action}:{tool}".encode("utf-8")).hexdigest()[:16]
        receipt: Dict[str, Any] = {
            "receipt_id": receipt_id,
            "timestamp_utc": now,
            "action": action,
            "tool": tool,
            "risk_class": risk_class,
            "policy_result": policy_result,
            "status": status,
            "input_hash": stable_hash(input_payload),
            "output_hash": stable_hash(output_payload),
            "input_summary": str(input_payload)[:500],
            "output_summary": str(output_payload)[:500],
            "evidence": list(evidence or []),
            "rollback_path": rollback_path,
            "related_receipts": [],
            "notes": notes,
        }
        path = self.receipt_dir / f"{receipt_id}_{action.replace('.', '_')}.json"
        path.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
        return path
