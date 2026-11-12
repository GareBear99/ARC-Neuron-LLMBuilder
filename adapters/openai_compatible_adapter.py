from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from adapters.base import ModelAdapter, ModelResponse


class OpenAICompatibleAdapter(ModelAdapter):
    name = "openai_compatible"

    def __init__(self, endpoint: str | None = None, model: str | None = None, api_key: str | None = None, timeout_seconds: int | None = None) -> None:
        self.endpoint = endpoint or os.environ.get("OPENAI_COMPATIBLE_BASE_URL") or os.environ.get("COGNITION_BASE_URL") or "http://127.0.0.1:8000/v1/chat/completions"
        self.model = model or os.environ.get("OPENAI_COMPATIBLE_MODEL") or os.environ.get("COGNITION_MODEL_NAME") or "local-model"
        self.api_key = api_key or os.environ.get("OPENAI_COMPATIBLE_API_KEY") or os.environ.get("COGNITION_API_KEY")
        self.timeout_seconds = int(timeout_seconds or os.environ.get("COGNITION_TIMEOUT_SECONDS") or 60)

    def backend_identity(self) -> dict[str, Any]:
        return {"adapter": self.name, "endpoint": self.endpoint, "model": self.model, "has_api_key": bool(self.api_key)}

    def _request_json(self, url: str, payload: dict[str, Any] | None = None, method: str = "GET") -> tuple[dict[str, Any] | None, str | None, int | None, float]:
        started = time.perf_counter()
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        # Cloudflare blocks urllib's default User-Agent (HTTP 403 / error 1010) on
        # /health and POST /v1/chat/completions; a browser UA gets through.
        headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                body = resp.read().decode("utf-8")
                status = getattr(resp, "status", 200)
            elapsed = round((time.perf_counter() - started) * 1000, 2)
            if not body.strip():
                return None, "Empty response body", status, elapsed
            return json.loads(body), None, status, elapsed
        except urllib.error.HTTPError as exc:
            elapsed = round((time.perf_counter() - started) * 1000, 2)
            try:
                body = exc.read().decode("utf-8")
            except Exception:
                body = ""
            return None, f"HTTP {exc.code}: {body or exc.reason}", exc.code, elapsed
        except urllib.error.URLError as exc:
            elapsed = round((time.perf_counter() - started) * 1000, 2)
            return None, f"URL error: {exc.reason}", None, elapsed
        except json.JSONDecodeError as exc:
            elapsed = round((time.perf_counter() - started) * 1000, 2)
            return None, f"Invalid JSON response: {exc}", None, elapsed
        except Exception as exc:
            elapsed = round((time.perf_counter() - started) * 1000, 2)
            return None, str(exc), None, elapsed

    def healthcheck(self) -> dict[str, Any]:
        chat_health_url = self.endpoint.replace('/v1/chat/completions', '/health')
        payload, error, status, latency_ms = self._request_json(chat_health_url, method='GET')
        if error:
            return {"ok": False, "endpoint": chat_health_url, "status": status, "latency_ms": latency_ms, "error": error, "identity": self.backend_identity()}
        return {"ok": True, "endpoint": chat_health_url, "status": status, "latency_ms": latency_ms, "payload": payload, "identity": self.backend_identity()}

    def generate(self, prompt: str, *, system_prompt: str = "", context: dict | None = None) -> ModelResponse:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt or "You are a cognition-core candidate."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
        }
        data, error, _status, latency_ms = self._request_json(self.endpoint, payload=payload, method='POST')
        if error is not None or data is None:
            return ModelResponse(text="", meta={"adapter": self.name, "endpoint": self.endpoint, "model": self.model}, ok=False, error=error, latency_ms=latency_ms, backend_identity=f"{self.name}:{self.model}@{self.endpoint}")
        try:
            choice = data["choices"][0]
            message = choice.get("message", {})
            usage = data.get("usage", {})
            text = message.get("content", "")
            if not isinstance(text, str) or not text.strip():
                raise KeyError("content")
            return ModelResponse(text=text, meta={"adapter": self.name, "endpoint": self.endpoint, "model": self.model}, ok=True, latency_ms=latency_ms, finish_reason=choice.get("finish_reason"), prompt_tokens=usage.get("prompt_tokens"), completion_tokens=usage.get("completion_tokens"), backend_identity=f"{self.name}:{self.model}@{self.endpoint}")
        except Exception:
            return ModelResponse(text="", meta={"adapter": self.name, "endpoint": self.endpoint, "model": self.model, "raw_response": data}, ok=False, error="Response missing choices[0].message.content", latency_ms=latency_ms, backend_identity=f"{self.name}:{self.model}@{self.endpoint}")
