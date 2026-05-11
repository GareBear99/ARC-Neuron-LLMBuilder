from __future__ import annotations

from typing import Any

from adapters.command_adapter import CommandAdapter
from adapters.echo_adapter import EchoAdapter
from adapters.exemplar_adapter import ExemplarAdapter
from adapters.heuristic_adapter import HeuristicAdapter
from adapters.llama_cpp_http_adapter import LlamaCppHttpAdapter
from adapters.native_llamafile_adapter import NativeLlamafileAdapter
from adapters.openai_compatible_adapter import OpenAICompatibleAdapter


_ADAPTER_ALIASES = {
    "echo": "echo",
    "heuristic": "heuristic",
    "exemplar": "exemplar",
    "local_exemplar": "exemplar",
    "command": "command",
    "local_command": "command",
    "llama_cli": "command",
    # native_llamafile — CPU subprocess, no server, word-at-a-time stream
    "native_llamafile": "native_llamafile",
    "llamafile_native": "native_llamafile",
    "llamafile_cpu": "native_llamafile",
    "llamafile_noserver": "native_llamafile",
    # legacy aliases kept for backward compat (now redirected to native)
    "llamafile_direct": "native_llamafile",
    "openai_compatible": "openai_compatible",
    "llamacpp_openai": "openai_compatible",
    "llamafile_openai": "openai_compatible",
    "llama_cpp_http": "llama_cpp_http",
    "gguf_http": "llama_cpp_http",
}


_ADAPTERS = {
    "command": CommandAdapter,
    "echo": EchoAdapter,
    "heuristic": HeuristicAdapter,
    "exemplar": ExemplarAdapter,
    "native_llamafile": NativeLlamafileAdapter,
    "openai_compatible": OpenAICompatibleAdapter,
    "llama_cpp_http": LlamaCppHttpAdapter,
}


def normalize_adapter_name(name: str) -> str:
    key = (name or "").strip().lower()
    if key not in _ADAPTER_ALIASES:
        raise ValueError(f"Unknown adapter: {name}")
    return _ADAPTER_ALIASES[key]


def build_adapter(name: str, **kwargs: Any):
    canonical = normalize_adapter_name(name)
    adapter_cls = _ADAPTERS[canonical]
    return adapter_cls(**kwargs)


def create_adapter(name: str, **kwargs: Any):
    return build_adapter(name, **kwargs)
