import json

from mcp.servers.arc_dataset_server import dataset_deduplicate, dataset_normalize, dataset_validate_jsonl


def test_dataset_validate_and_normalize(tmp_path):
    source = tmp_path / "in.jsonl"
    source.write_text(json.dumps({"instruction": "Hello", "response": "World response text"}) + "\n")
    assert dataset_validate_jsonl(str(source))["valid"]
    out = tmp_path / "out.jsonl"
    result = dataset_normalize(str(source), str(out))
    assert result["records_out"] == 1
    dedup = tmp_path / "dedup.jsonl"
    d = dataset_deduplicate(str(out), str(dedup))
    assert d["records_out"] == 1
