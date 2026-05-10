"""arc_core/context_window_manager.py — Governed context window management for ARC-Neuron.

Solves the context window parsing problem documented in LuciferAI_Local v1.0.

Design heritage:
  - Trim-from-middle strategy: GareBear99/LuciferAI_Local core/llm_backend.py
    (LLMBackend.chat, conversation_history management) and core/memory_system.py
    (MemorySystem, model-specific session_depth configs).
  - System-message preservation: LuciferAI_Local memory_system.py
    (_load_last_session, get_context).
  - Model-tier depth config: LuciferAI_Local memory_system.py
    (memory_configs dict keyed by model name).

ARC-Neuron additions:
  - SHA-256 receipt for every trim event (governance audit trail).
  - Floor-preserving system message injection for doctrine and capability floors.
  - Omnibinary-compatible receipt schema.

Usage:
    from arc_core.context_window_manager import ContextWindowManager
    mgr = ContextWindowManager(model_tier="v10_wave4", max_depth=128)
    trimmed = mgr.trim(messages)
    receipt  = mgr.last_receipt
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

# Model-tier depth configuration (messages, not tokens)
# Adapted from LuciferAI_Local/core/memory_system.py memory_configs dict
MODEL_TIER_DEPTHS: dict[str, int] = {
    "tiny":              32,
    "arc_tiny":          32,
    "v6_conversation":   64,
    "arc_governed_v6":   64,
    "v10_wave4":        128,
    "arc_governed_v10": 128,
    "v11_wave5":        128,
    "arc_governed_v11": 128,
    "large":            256,
    "default":           64,
}

PRESERVED_ROLES = frozenset({"system"})
ARC_DOCTRINE_TAG = "[ARC_DOCTRINE]"
ARC_FLOOR_TAG    = "[ARC_FLOOR]"


class ContextWindowManager:
    """Governed sliding context window with trim-from-middle strategy.

    Key insight from LuciferAI_Local: when history exceeds window depth,
    naive head/tail truncation loses either system instructions or recent context.
    Trim-from-middle preserves both: system messages are always kept, the most
    recent N exchange pairs are kept, older mid-session context is dropped.

    This matches LuciferAI_Local/core/llm_backend.py LLMBackend.chat():
    "Keep system messages and trim from the middle. Keep most recent messages."
    """

    def __init__(self, model_tier: str = "default", max_depth: int | None = None) -> None:
        self.model_tier = model_tier
        self.max_depth: int = (
            max_depth if max_depth is not None
            else MODEL_TIER_DEPTHS.get(model_tier, MODEL_TIER_DEPTHS["default"])
        )
        self.last_receipt: dict[str, Any] | None = None
        self._trim_event_count: int = 0

    def trim(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        """Return window-bounded message list using trim-from-middle strategy."""
        if len(messages) <= self.max_depth:
            self.last_receipt = self._no_op_receipt(len(messages))
            return list(messages)

        system_msgs = [m for m in messages if m.get("role") in PRESERVED_ROLES]
        other_msgs  = [m for m in messages if m.get("role") not in PRESERVED_ROLES]
        budget      = max(0, self.max_depth - len(system_msgs))
        kept        = other_msgs[-budget:] if budget > 0 else []
        dropped     = other_msgs[:-budget] if budget > 0 else other_msgs

        trimmed = system_msgs + kept
        self._trim_event_count += 1
        self.last_receipt = self._trim_receipt(
            before=len(messages), after=len(trimmed),
            dropped=len(dropped), system_preserved=len(system_msgs),
            recent_kept=len(kept),
            dropped_hash=self._hash_msgs(dropped),
        )
        return trimmed

    def inject_doctrine(self, messages: list[dict[str, str]], doctrine_text: str) -> list[dict[str, str]]:
        """Prepend a doctrine system message that survives all future trims."""
        msg = {"role": "system", "content": f"{ARC_DOCTRINE_TAG} {doctrine_text}"}
        return [msg] + [m for m in messages if m != msg]

    def inject_floor_reminder(self, messages: list[dict[str, str]], floor_summary: str) -> list[dict[str, str]]:
        """Prepend a floor-threshold system message that survives all trims."""
        msg = {"role": "system", "content": f"{ARC_FLOOR_TAG} Active floor thresholds: {floor_summary}"}
        return [msg] + [m for m in messages if m != msg]

    def get_stats(self) -> dict[str, Any]:
        return {"model_tier": self.model_tier, "max_depth": self.max_depth,
                "trim_event_count": self._trim_event_count, "last_receipt": self.last_receipt}

    # ── Receipt helpers ────────────────────────────────────────────────────── #

    def _trim_receipt(self, before, after, dropped, system_preserved, recent_kept, dropped_hash) -> dict[str, Any]:
        ts = datetime.now(timezone.utc).isoformat()
        r: dict[str, Any] = {
            "event": "context_window_trim", "strategy": "trim_from_middle",
            "model_tier": self.model_tier, "max_depth": self.max_depth,
            "before_count": before, "after_count": after, "dropped_count": dropped,
            "system_preserved": system_preserved, "recent_pairs_kept": recent_kept // 2,
            "dropped_content_hash": dropped_hash,
            "bounded_by": "context_window_doctrine_v1", "timestamp": ts,
        }
        r["receipt_id"] = self._hash_receipt(r)
        return r

    def _no_op_receipt(self, count: int) -> dict[str, Any]:
        return {"event": "context_window_no_trim", "model_tier": self.model_tier,
                "max_depth": self.max_depth, "message_count": count,
                "bounded_by": "context_window_doctrine_v1",
                "timestamp": datetime.now(timezone.utc).isoformat()}

    @staticmethod
    def _hash_msgs(msgs: list[dict[str, str]]) -> str:
        return hashlib.sha256(json.dumps(msgs, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]

    @staticmethod
    def _hash_receipt(r: dict[str, Any]) -> str:
        payload = json.dumps({k: v for k, v in r.items() if k != "receipt_id"}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


def trim_messages(messages: list[dict[str, str]], model_tier: str = "default",
                  max_depth: int | None = None) -> tuple[list[dict[str, str]], dict[str, Any] | None]:
    """Convenience: trim a message list, return (trimmed, receipt|None)."""
    mgr = ContextWindowManager(model_tier=model_tier, max_depth=max_depth)
    trimmed = mgr.trim(messages)
    return trimmed, mgr.last_receipt if len(trimmed) < len(messages) else None


if __name__ == "__main__":
    import sys
    print("ContextWindowManager — self test\n")
    sys_msg  = {"role": "system", "content": "[ARC_DOCTRINE] Govern all changes."}
    messages = [sys_msg]
    for i in range(50):
        messages += [{"role": "user", "content": f"User {i}"},
                     {"role": "assistant", "content": f"Reply {i}"}]
    mgr     = ContextWindowManager(model_tier="tiny")
    trimmed = mgr.trim(messages)
    r       = mgr.last_receipt
    print(f"Input: {len(messages)}  Trimmed: {len(trimmed)}")
    print(f"System preserved: {r['system_preserved']}  Pairs kept: {r['recent_pairs_kept']}")
    print(f"Receipt ID: {r['receipt_id']}  Bounded by: {r['bounded_by']}")
    assert any(m["role"] == "system" for m in trimmed), "FAIL: system message dropped"
    assert len(trimmed) <= mgr.max_depth, f"FAIL: exceeds max_depth"
    print("\nAll self-tests passed.")
    sys.exit(0)
