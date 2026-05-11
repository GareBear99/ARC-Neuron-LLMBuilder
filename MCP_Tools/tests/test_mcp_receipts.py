import json
from pathlib import Path

from mcp.client.receipt_writer import ReceiptWriter


def test_receipt_writer_creates_required_fields(tmp_path):
    writer = ReceiptWriter(tmp_path)
    path = writer.write_receipt(
        action="dataset.scan",
        tool="dataset.scan",
        risk_class="read_only",
        policy_result="allowed",
        status="success",
        input_payload={"path": "datasets"},
        output_payload={"files_found": 0},
        evidence=[],
    )
    data = json.loads(Path(path).read_text())
    for key in ["receipt_id", "timestamp_utc", "action", "tool", "risk_class", "policy_result", "status", "input_hash", "output_hash", "evidence"]:
        assert key in data
