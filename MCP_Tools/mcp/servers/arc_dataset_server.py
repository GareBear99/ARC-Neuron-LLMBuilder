"""Dataset MCP server scaffold for ARC-Neuron LLMBuilder."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


def dataset_scan(path: str, recursive: bool = True, allowed_extensions: Iterable[str] = (".jsonl", ".json", ".txt", ".md", ".csv")) -> dict:
    root = Path(path)
    pattern = "**/*" if recursive else "*"
    files = [p for p in root.glob(pattern) if p.is_file()] if root.exists() else []
    accepted = [str(p) for p in files if p.suffix.lower() in set(allowed_extensions)]
    rejected = [str(p) for p in files if p.suffix.lower() not in set(allowed_extensions)]
    return {"files_found": len(files), "accepted": accepted, "rejected": rejected}


def dataset_validate_jsonl(path: str, required_fields: Iterable[str] = ("instruction", "response")) -> dict:
    errors = []
    records = 0
    required = set(required_fields)
    for idx, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            missing = required - set(obj)
            if missing:
                errors.append({"line": idx, "error": f"missing fields: {sorted(missing)}"})
            records += 1
        except Exception as exc:
            errors.append({"line": idx, "error": str(exc)})
    return {"valid": not errors, "records": records, "errors": errors, "warnings": []}


def dataset_normalize(source_path: str, output_path: str, format: str = "instruction_response") -> dict:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    records_in = records_out = rejected = 0
    with Path(source_path).open("r", encoding="utf-8") as src, out.open("w", encoding="utf-8") as dst:
        for line in src:
            if not line.strip():
                continue
            records_in += 1
            try:
                obj = json.loads(line)
                normalized = {
                    "instruction": str(obj.get("instruction") or obj.get("prompt") or obj.get("input") or "").strip(),
                    "response": str(obj.get("response") or obj.get("completion") or obj.get("output") or "").strip(),
                    "source": obj.get("source", source_path),
                }
                if not normalized["instruction"] or not normalized["response"]:
                    rejected += 1
                    continue
                dst.write(json.dumps(normalized, ensure_ascii=False) + "\n")
                records_out += 1
            except Exception:
                rejected += 1
    return {"status": "success", "records_in": records_in, "records_out": records_out, "records_rejected": rejected, "output_path": output_path, "format": format}


def dataset_deduplicate(source_path: str, output_path: str) -> dict:
    seen = set()
    records_in = records_out = 0
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with Path(source_path).open("r", encoding="utf-8") as src, out.open("w", encoding="utf-8") as dst:
        for line in src:
            if not line.strip():
                continue
            records_in += 1
            key = line.strip()
            if key in seen:
                continue
            seen.add(key)
            dst.write(line if line.endswith("\n") else line + "\n")
            records_out += 1
    return {"records_in": records_in, "records_out": records_out, "duplicates_removed": records_in - records_out, "output_path": output_path}


def dataset_quality_score(path: str) -> dict:
    total = short = missing_source = 0
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        total += 1
        obj = json.loads(line)
        if len(str(obj.get("response", ""))) < 20:
            short += 1
        if not obj.get("source"):
            missing_source += 1
    penalty = (short + missing_source) / max(total, 1)
    return {"quality_score": round(max(0.0, 1.0 - penalty), 4), "records": total, "issues": {"short_responses": short, "missing_source": missing_source}}
