"""ARC-Neuron MCP policy gate.

This module is intentionally dependency-light. It can load the policy YAML files
with PyYAML when available. If PyYAML is not installed, it falls back to a tiny
parser for the simple policy format used in this scaffold.
"""
from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


@dataclass
class PolicyDecision:
    allowed: bool
    policy_result: str
    risk_class: str
    approval_required: bool
    reason: str


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if yaml:
        return yaml.safe_load(text) or {}
    # Minimal fallback: enough for tests with simple keys; install PyYAML for real use.
    data: Dict[str, Any] = {}
    current = data
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if ":" in line and not line.startswith(" "):
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value:
                current[key] = value
            else:
                current[key] = {}
                current = current[key]
    return data


class PolicyGate:
    def __init__(self, root: str | Path = ".") -> None:
        self.root = Path(root)
        self.policy_dir = self.root / "mcp" / "policies"
        self.tool_permissions = _load_yaml(self.policy_dir / "tool_permissions.yml").get("tools", {})
        self.risk_classes = _load_yaml(self.policy_dir / "risk_classes.yml").get("risk_classes", {})
        self.allowed_paths = _load_yaml(self.policy_dir / "allowed_paths.yml")
        self.denied_paths = _load_yaml(self.policy_dir / "denied_paths.yml").get("denied_paths", [])

    def decide(self, tool_name: str, target_paths: Optional[Iterable[str]] = None, approved: bool = False) -> PolicyDecision:
        tool = self.tool_permissions.get(tool_name)
        if not tool:
            return PolicyDecision(False, "blocked", "unknown", False, f"Unknown tool: {tool_name}")
        if not tool.get("enabled", False):
            return PolicyDecision(False, "blocked", tool.get("risk_class", "unknown"), False, f"Disabled tool: {tool_name}")

        risk_class = tool.get("risk_class", "unknown")
        approval_required = bool(tool.get("approval_required") or self.risk_classes.get(risk_class, {}).get("approval_required"))

        for target in target_paths or []:
            if self._is_denied(target):
                return PolicyDecision(False, "blocked", risk_class, approval_required, f"Denied path: {target}")

        if approval_required and not approved:
            return PolicyDecision(False, "requires_approval", risk_class, True, f"Approval required for {tool_name}")

        return PolicyDecision(True, "allowed", risk_class, approval_required, "Allowed")

    def _is_denied(self, path: str) -> bool:
        normalized = path.replace("\\", "/")
        return any(fnmatch(normalized, pattern) for pattern in self.denied_paths)
