"""Evaluation MCP server scaffold."""
from __future__ import annotations

import json
from pathlib import Path


def eval_compare_candidates(incumbent_score: float, candidate_score: float) -> dict:
    delta = candidate_score - incumbent_score
    return {"incumbent_score": incumbent_score, "candidate_score": candidate_score, "delta": round(delta, 6), "promotion_recommended": delta > 0}


def eval_generate_report(candidate: str, output_path: str, summary: dict) -> dict:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"# Evaluation Report: {candidate}\n\n```json\n{json.dumps(summary, indent=2)}\n```\n", encoding="utf-8")
    return {"report_path": str(out), "status": "created"}
