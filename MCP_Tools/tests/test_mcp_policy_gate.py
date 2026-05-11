from pathlib import Path

from mcp.client.policy_gate import PolicyGate


def test_unknown_tool_blocks():
    gate = PolicyGate(Path(__file__).resolve().parents[1])
    decision = gate.decide("not.real")
    assert not decision.allowed
    assert decision.policy_result == "blocked"


def test_read_only_tool_allowed():
    gate = PolicyGate(Path(__file__).resolve().parents[1])
    decision = gate.decide("dataset.scan")
    assert decision.allowed
    assert decision.risk_class == "read_only"


def test_approval_required_tool_pending():
    gate = PolicyGate(Path(__file__).resolve().parents[1])
    decision = gate.decide("model.promote_candidate")
    assert not decision.allowed
    assert decision.policy_result == "requires_approval"


def test_denied_secret_path_blocks():
    gate = PolicyGate(Path(__file__).resolve().parents[1])
    decision = gate.decide("repo.read_file", target_paths=[".env"])
    assert not decision.allowed
