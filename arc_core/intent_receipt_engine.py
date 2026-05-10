"""arc_core/intent_receipt_engine.py — Intent-gated execution with signed receipts.

Solves deterministic_compliance gap by routing every governed action through
an intent validation gate that produces structured allow/deny/error receipts.

Design heritage:
  - Intent registry + data-intent binding:
    GareBear99/Proto-Synth_Grid_Engine Iteration10/CHANGELOG_v44
    (Autowrap Intent Validation + Authority Receipts + Module Manifest Checks)
  - 5-layer routing architecture:
    GareBear99/LuciferAI_Local COMPLETE_ROUTING_ARCHITECTURE.md
    (Category 1-6 routing, process_request flow, 5-tier fallback)
  - Lifecycle gate checks:
    Proto-Synth v44 (intent gate validation against boot/build lifecycle states)
  - Sub-task decomposition:
    LuciferAI_Local/core/mistral_task_parser.py
    (intent -> task -> subtask -> next_step chain)

Usage:
    from arc_core.intent_receipt_engine import IntentReceiptEngine
    engine  = IntentReceiptEngine()
    receipt = engine.validate("run the benchmark suite")
    if receipt["decision"] == "allow":
        ...
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

INTENT_KEYWORDS: dict[str, list[str]] = {
    "absorb":    ["absorb", "teach", "learn", "ingest", "import session",
                  "add term", "new term", "session absorption"],
    "train":     ["train", "training", "sft", "fine-tune", "finetune",
                  "export sft", "run training", "training cycle", "training run"],
    "benchmark": ["benchmark", "evaluate", "run benchmark", "run eval",
                  "evaluation", "run tasks", "test model", "run the benchmark",
                  "benchmark suite"],
    "gate":      ["gate", "promote", "promotion", "gate v2", "run gate",
                  "promotion decision", "check promotion", "candidate gate"],
    "archive":   ["archive", "bundle", "arc-rar", "snapshot", "create bundle",
                  "arc rar", "save bundle", "rollback bundle"],
    "query":     ["what is", "what are", "explain", "describe", "tell me about",
                  "show me", "list all", "retrieve", "lookup", "how does",
                  "what does", "what was", "get the", "find the score"],
}

STATE_CHANGING_INTENTS = frozenset({"absorb", "train", "gate", "archive"})
READ_ONLY_INTENTS      = frozenset({"query", "benchmark"})
REQUIRED_RECEIPT_FIELDS = frozenset({"receipt_id", "intent", "decision",
                                      "evidence", "bounded_by", "timestamp"})

SUBTASK_TEMPLATES: dict[str, list[dict[str, str]]] = {
    "absorb":    [{"step":"1","action":"parse_session_text","assigned_to":"arc_core"},
                  {"step":"2","action":"extract_terms_and_exemplars","assigned_to":"arc_core"},
                  {"step":"3","action":"approve_and_store_terms","assigned_to":"language_module"},
                  {"step":"4","action":"export_sft_records","assigned_to":"arc_core"},
                  {"step":"5","action":"write_obin_events","assigned_to":"omnibinary"}],
    "train":     [{"step":"1","action":"export_sft_dataset","assigned_to":"arc_core"},
                  {"step":"2","action":"run_training_loop","assigned_to":"trainer"},
                  {"step":"3","action":"validate_candidate_output","assigned_to":"arc_core"},
                  {"step":"4","action":"export_candidate_artifact","assigned_to":"arc_core"}],
    "benchmark": [{"step":"1","action":"load_benchmark_tasks","assigned_to":"arc_core"},
                  {"step":"2","action":"run_model_on_tasks","assigned_to":"adapter"},
                  {"step":"3","action":"score_outputs","assigned_to":"rubric_scorer"},
                  {"step":"4","action":"write_scored_jsonl","assigned_to":"arc_core"}],
    "gate":      [{"step":"1","action":"load_scored_outputs","assigned_to":"arc_core"},
                  {"step":"2","action":"check_floor_thresholds","assigned_to":"gate_v2"},
                  {"step":"3","action":"check_regression_ceilings","assigned_to":"gate_v2"},
                  {"step":"4","action":"write_promotion_decision","assigned_to":"gate_v2"},
                  {"step":"5","action":"update_scoreboard","assigned_to":"arc_core"}],
    "archive":   [{"step":"1","action":"validate_candidate_artifacts","assigned_to":"arc_core"},
                  {"step":"2","action":"create_arc_rar_bundle","assigned_to":"arc_core"},
                  {"step":"3","action":"verify_bundle_integrity","assigned_to":"arc_core"},
                  {"step":"4","action":"index_bundle_in_scoreboard","assigned_to":"arc_core"}],
    "query":     [{"step":"1","action":"parse_query_intent","assigned_to":"arc_core"},
                  {"step":"2","action":"retrieve_from_language_module","assigned_to":"language_module"},
                  {"step":"3","action":"generate_bounded_response","assigned_to":"adapter"}],
}

LIFECYCLE_BLOCKS: dict[str, dict[str, str]] = {
    "boot":  {i: f"Intent '{i}' blocked during system boot. Only query and benchmark allowed."
              for i in STATE_CHANGING_INTENTS},
    "train": {"gate":    "Intent 'gate' blocked while training. Wait for training to complete.",
              "archive": "Intent 'archive' blocked while training. Wait for training to complete."},
    "gate":  {"train":   "Intent 'train' blocked during gate evaluation.",
              "absorb":  "Intent 'absorb' blocked during gate evaluation."},
}


class IntentReceiptEngine:
    """Intent validation gate with signed receipt generation.

    Implements Proto-Synth v44 pattern:
    'Added intent receipts (allow/deny/error) so meaningful UI actions
    produce authority records.'
    """

    def __init__(self, lifecycle_state: str = "ready") -> None:
        self.lifecycle_state  = lifecycle_state
        self._receipt_count   = 0

    def validate(self, user_input: str) -> dict[str, Any]:
        """Parse intent, apply lifecycle gate, produce allow/deny/error receipt."""
        intent = self._parse_intent(user_input)
        return self._decide(intent, user_input)

    def validate_batch(self, inputs: list[str]) -> list[dict[str, Any]]:
        return [self.validate(i) for i in inputs]

    def is_allowed(self, user_input: str) -> bool:
        return self.validate(user_input).get("decision") == "allow"

    def set_lifecycle_state(self, state: str) -> None:
        valid = {"boot", "ready", "train", "gate"}
        if state not in valid:
            raise ValueError(f"Unknown lifecycle state '{state}'. Valid: {valid}")
        self.lifecycle_state = state

    def get_stats(self) -> dict[str, Any]:
        return {"lifecycle_state": self.lifecycle_state,
                "receipt_count": self._receipt_count,
                "supported_intents": list(INTENT_KEYWORDS)}

    # ── Intent parsing ─────────────────────────────────────────────────────── #

    def _parse_intent(self, text: str) -> str:
        lower = text.lower().strip()
        scores = {intent: sum(1 for kw in kws if kw in lower)
                  for intent, kws in INTENT_KEYWORDS.items()}
        scored = {k: v for k, v in scores.items() if v > 0}
        return max(scored, key=lambda k: scored[k]) if scored else "unknown"

    def _decide(self, intent: str, user_input: str) -> dict[str, Any]:
        self._receipt_count += 1

        if intent == "unknown":
            return self._receipt(intent, "deny",
                reason="Intent could not be determined. Supported intents: "
                       "absorb, train, benchmark, gate, archive, query. "
                       "Provide a more specific action verb.",
                evidence=f"input_text:{_shash(user_input)}", sub_tasks=[])

        block = LIFECYCLE_BLOCKS.get(self.lifecycle_state, {}).get(intent)
        if block:
            return self._receipt(intent, "deny", reason=block,
                evidence=f"lifecycle_state:{self.lifecycle_state}", sub_tasks=[])

        reason = (f"Read-only intent '{intent}' permitted in all lifecycle states."
                  if intent in READ_ONLY_INTENTS
                  else f"State-changing intent '{intent}' permitted in lifecycle '{self.lifecycle_state}'.")
        evidence = (f"intent_registry:{intent}" if intent in READ_ONLY_INTENTS
                    else f"lifecycle_state:{self.lifecycle_state}|intent_registry:{intent}")
        return self._receipt(intent, "allow", reason=reason, evidence=evidence,
                             sub_tasks=SUBTASK_TEMPLATES.get(intent, []))

    def _receipt(self, intent, decision, reason, evidence, sub_tasks) -> dict[str, Any]:
        ts = datetime.now(timezone.utc).isoformat()
        r: dict[str, Any] = {"intent": intent, "decision": decision, "reason": reason,
                              "evidence": evidence,
                              "bounded_by": "cognition_contract_v1|intent_receipt_engine_v1",
                              "timestamp": ts, "sub_tasks": sub_tasks, "format": "intent_receipt_v1"}
        r["receipt_id"] = _hash_receipt(r)
        return r


def _shash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:8]

def _hash_receipt(r: dict[str, Any]) -> str:
    payload = json.dumps({k: v for k, v in r.items() if k != "receipt_id"},
                         sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


if __name__ == "__main__":
    import sys
    print("IntentReceiptEngine — self test\n")
    engine = IntentReceiptEngine(lifecycle_state="ready")
    tests = [
        ("run the full benchmark suite",               "benchmark", "allow"),
        ("absorb this session into the language module","absorb",    "allow"),
        ("train a new candidate for 200 steps",         "train",     "allow"),
        ("run gate v2 on the scored outputs",           "gate",      "allow"),
        ("create an arc-rar bundle for archival",       "archive",   "allow"),
        ("what is the reflection score?",               "query",     "allow"),
        ("zorp the flibble",                            "unknown",   "deny"),
    ]
    ok = True
    for inp, exp_intent, exp_dec in tests:
        r = engine.validate(inp)
        passed = r["intent"] == exp_intent and r["decision"] == exp_dec and REQUIRED_RECEIPT_FIELDS.issubset(r)
        print(f"{'✓' if passed else '✗'} {inp[:50]}")
        print(f"    intent={r['intent']} decision={r['decision']} id={r['receipt_id']}")
        if not passed:
            ok = False

    print("\nLifecycle gate (boot blocks train):")
    engine.set_lifecycle_state("boot")
    r = engine.validate("train a new candidate")
    assert r["decision"] == "deny"
    print(f"✓ Train denied in boot state")
    engine.set_lifecycle_state("ready")
    r = engine.validate("train a new candidate")
    assert r["decision"] == "allow"
    print(f"✓ Train allowed in ready state")

    print("\nAll self-tests passed." if ok else "\nFAILURES detected.")
    sys.exit(0 if ok else 1)
