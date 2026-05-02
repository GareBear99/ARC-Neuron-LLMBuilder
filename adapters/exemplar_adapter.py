from __future__ import annotations

import json
import math
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

from adapters.base import ModelAdapter, ModelResponse

_TOKEN_RE = re.compile(r"[a-zA-Z0-9_']+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


def _norm(counter: Counter[str]) -> float:
    return math.sqrt(sum(v * v for v in counter.values())) or 1.0


def _cosine(a: Counter[str], b: Counter[str]) -> float:
    if not a or not b:
        return 0.0
    denom = _norm(a) * _norm(b)
    numer = sum(v * b.get(k, 0) for k, v in a.items())
    return numer / denom if denom else 0.0


class ExemplarAdapter(ModelAdapter):
    name = "exemplar"
    promotable = True

    def __init__(self, artifact: str | None = None, top_k: int = 3, **_: Any) -> None:
        if not artifact:
            raise ValueError("artifact is required for exemplar adapter")
        self.artifact_path = Path(artifact)
        payload = json.loads(self.artifact_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and "records" not in payload:
            self.artifact_path, payload = self._resolve_manifest_payload(self.artifact_path, payload)
        self.model = payload.get("candidate_id", self.artifact_path.stem)
        self.top_k = int(top_k)
        self.records: list[dict[str, Any]] = payload.get("records", [])
        # Build raw term-frequency vectors from pre-tokenized prompts
        raw_vectors: list[Counter[str]] = [Counter(r.get("prompt_tokens", [])) for r in self.records]
        # Compute IDF weights: log(N / df) for each term
        # This downweights ubiquitous terms (constraint, validate, test) that appear
        # in most records and upweights distinctive terms specific to a scenario.
        N = max(1, len(raw_vectors))
        df: dict[str, int] = {}
        for vec in raw_vectors:
            for term in vec:
                df[term] = df.get(term, 0) + 1
        import math
        self._idf: dict[str, float] = {term: math.log(N / count) for term, count in df.items()}
        # TF-IDF vectors: weight each term by its IDF score
        self._vectors: list[Counter[str]] = []
        for vec in raw_vectors:
            tfidf: Counter[str] = Counter()
            for term, tf in vec.items():
                tfidf[term] = tf * self._idf.get(term, 0.0)
            self._vectors.append(tfidf)

    def _resolve_manifest_payload(self, manifest_path: Path, payload: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
        candidates: list[Path] = []
        output_file = payload.get("output_file")
        if output_file:
            candidates.append((manifest_path.parent / str(output_file)).resolve())
        paths_artifact = payload.get("paths", {}).get("artifact") if isinstance(payload.get("paths"), dict) else None
        if paths_artifact:
            path_value = Path(str(paths_artifact))
            candidates.append(path_value)
            candidates.append((manifest_path.parent / path_value.name).resolve())
        for candidate in candidates:
            if candidate.exists():
                return candidate, json.loads(candidate.read_text(encoding="utf-8"))
        raise FileNotFoundError(f"could not resolve exemplar payload from manifest: {manifest_path}")

    def backend_identity(self) -> dict[str, Any]:
        return {
            "adapter": self.name,
            "artifact": str(self.artifact_path),
            "candidate": self.model,
            "records": len(self.records),
            "top_k": self.top_k,
        }

    def healthcheck(self) -> dict[str, Any]:
        return {
            "ok": self.artifact_path.exists() and bool(self.records),
            "adapter": self.name,
            "artifact": str(self.artifact_path),
            "records": len(self.records),
        }

    def generate(self, prompt: str, *, system_prompt: str = "", context: dict | None = None) -> ModelResponse:
        started = time.perf_counter()
        # Apply IDF to query tokens (same weighting as corpus vectors)
        raw_tokens = Counter(_tokenize(prompt))
        tokens = Counter({term: tf * self._idf.get(term, 0.0)
                          for term, tf in raw_tokens.items()
                          if self._idf.get(term, 0.0) > 0})
        request_cap = (context or {}).get("capability", "")
        scored: list[tuple[float, dict[str, Any]]] = []
        for vec, record in zip(self._vectors, self.records):
            score = _cosine(tokens, vec)
            if score > 0:
                # Boost records whose capability matches the request (2x boost).
                # Penalise generic/unknown records by 50% to prevent them from
                # dominating retrieval over capability-specific records.
                rec_cap = record.get("capability", "generic")
                if request_cap and rec_cap == request_cap:
                    score *= 2.0
                elif rec_cap in ("generic", "unknown", ""):
                    score *= 0.8
                scored.append((score, record))
        scored.sort(key=lambda x: x[0], reverse=True)

        # Strict capability-first retrieval.
        # When the requested capability has >= top_k records in the pool,
        # retrieve ONLY from that capability's records.
        # This prevents cross-capability vocabulary contamination.
        # Fall back to global only when there are literally no cap-matched records.
        if request_cap:
            cap_matched = [(s, rec) for s, rec in scored
                           if rec.get("capability") == request_cap and s > 0]
            if len(cap_matched) >= self.top_k:
                chosen = cap_matched[: self.top_k]
            elif cap_matched:
                # Have some but fewer than top_k — use all of them, pad with global
                global_rest = [item for item in scored
                                if item[1].get("capability") != request_cap]
                chosen = cap_matched + global_rest[: self.top_k - len(cap_matched)]
            else:
                # No cap-matched records at all — fall back to global
                chosen = scored[: self.top_k]
        else:
            chosen = scored[: self.top_k]

        lines: list[str] = []
        if system_prompt:
            lines.append(system_prompt.strip())
        if context and context.get("capability"):
            lines.append(f"Capability: {context['capability']}")

        if not chosen:
            lines.append(
                "No strong exemplar match was found. Preserve constraints, state unknowns, choose the smallest safe next step, and verify with evidence."
            )
        else:
            best = chosen[0][1]
            best_text = (best.get("target") or best.get("response") or "").strip()
            if best_text:
                lines.append(best_text)
            if len(chosen) > 1:
                lines.append("Supporting patterns:")
                for score, record in chosen[1:]:
                    summary = record.get("target") or record.get("response") or record.get("prompt") or ""
                    summary = " ".join(str(summary).split())[:200]
                    lines.append(f"- {summary}")
            lines.append("Confidence: bounded by retrieved exemplars and prompt overlap.")

        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return ModelResponse(
            text="\n".join(line for line in lines if line),
            meta={
                "adapter": self.name,
                "artifact": str(self.artifact_path),
                "matches": [
                    {
                        "score": round(score, 4),
                        "source_repo": rec.get("source_repo"),
                        "capability": rec.get("capability"),
                        "source_file": rec.get("source_file"),
                    }
                    for score, rec in chosen
                ],
            },
            ok=True,
            latency_ms=latency_ms,
            backend_identity=f"{self.name}:{self.model}",
        )
