"""ARC-Neuron governed MCP client scaffold."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Optional

from .policy_gate import PolicyGate
from .receipt_writer import ReceiptWriter
from .tool_router import ToolRouter


class ArcMcpClient:
    def __init__(self, root: str | Path = ".") -> None:
        self.root = Path(root)
        self.policy_gate = PolicyGate(self.root)
        self.receipts = ReceiptWriter(self.root)
        self.router = ToolRouter()

    def call_tool(self, tool_name: str, target_paths: Optional[Iterable[str]] = None, approved: bool = False, **kwargs: Any) -> Any:
        decision = self.policy_gate.decide(tool_name, target_paths=target_paths, approved=approved)
        if not decision.allowed:
            self.receipts.write_receipt(
                action=tool_name,
                tool=tool_name,
                risk_class=decision.risk_class,
                policy_result=decision.policy_result,
                status="pending_approval" if decision.policy_result == "requires_approval" else "blocked",
                input_payload=kwargs,
                output_payload={"reason": decision.reason},
                evidence=[],
                notes=decision.reason,
            )
            raise PermissionError(decision.reason)
        result = self.router.call(tool_name, **kwargs)
        self.receipts.write_receipt(
            action=tool_name,
            tool=tool_name,
            risk_class=decision.risk_class,
            policy_result=decision.policy_result,
            status="success",
            input_payload=kwargs,
            output_payload=result,
            evidence=target_paths or [],
        )
        return result
