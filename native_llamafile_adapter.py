"""native_llamafile_adapter.py

Stable, complete adapter for running any GGUF via llamafile as a CPU-only
subprocess with tokenized, word-at-a-time streaming and activity-based
(never wall-clock) timeouts.

Three capabilities
──────────────────
1. COMPILE   compile_llamafile(runtime_binary, gguf, output)
             Cats the bare llamafile runtime binary and any .gguf together
             into a self-contained executable.  Same operation as
             scripts/runtime/compile_llamafile_from_binary.py but as a
             library call with no subprocess overhead.

2. DISCOVER  GGUFRegistry
             Scans artifacts/gguf/, exports/candidates/**,
             and any external paths you register.
             resolve("arc-neuron-small") → GGUFEntry(path, name, source)

3. STREAM    NativeLlamafileAdapter
             Runs the compiled llamafile as a subprocess.
             Reads stdout character-by-character in a background thread,
             accumulates into a word buffer, and flushes one complete word
             per yield/callback call — identical to LuciferAI_Local's
             NativeLlamafileBackend streaming model.

             Timeout model (matches LuciferAI TIMEOUT_FIX_IMPLEMENTATION.md):
               loading_timeout_s   — silence budget before the first character
                                     arrives (model is loading from disk)
               inactivity_timeout_s — silence budget between characters once
                                      generation has started
               NO wall-clock total timeout — while tokens are flowing, the
               call runs indefinitely.

Initialization paths (first match wins)
────────────────────────────────────────
A. llamafile_path=  pre-compiled/assembled binary + model_path= GGUF
B. runtime_binary= + model_path= / model_name= → compile on first use
C. auto-assemble from bin/llamafile.part.* + model_path= / model_name=

Env overrides (all optional)
────────────────────────────
  LLAMAFILE_RUNTIME_BINARY      path to the bare runtime binary
  LLAMAFILE_BIN                 path to an already-compiled llamafile
  LLAMAFILE_MODEL               path to the .gguf model
  LLAMAFILE_MODEL_NAME          short slug for registry lookup
  LLAMAFILE_COMPILED_DIR        output directory for compiled bundles
  LLAMAFILE_LOADING_TIMEOUT_S   (default 90)
  LLAMAFILE_INACTIVITY_TIMEOUT_S (default 45)
  LLAMAFILE_MAX_TOKENS          -n flag (default 512)
  LLAMAFILE_TEMPERATURE         --temp flag (default 0.7)
"""
from __future__ import annotations

import os
import platform
import queue
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional

from adapters.base import ModelAdapter, ModelResponse

# ── sentinel signalling end-of-stream from the reader thread ─────────────────
_EOF = object()

# ── project root (two levels up from adapters/) ──────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[1]


# ═══════════════════════════════════════════════════════════════════════════════
# 1.  COMPILE
# ═══════════════════════════════════════════════════════════════════════════════

def compile_llamafile(
    runtime_binary: Path | str,
    gguf: Path | str,
    output: Path | str,
    *,
    force: bool = False,
) -> Path:
    """Concatenate a llamafile runtime binary with a GGUF to make a
    self-contained, directly executable llamafile bundle.

    This is a pure-Python equivalent of the shell one-liner:
        cat llamafile_runtime model.gguf > model.llamafile && chmod +x model.llamafile

    Parameters
    ----------
    runtime_binary : the bare llamafile runtime executable (downloaded from
                     github.com/Mozilla-Ocho/llamafile/releases — take the
                     *-runtime* asset, NOT a pre-bundled model release).
    gguf           : any .gguf model file.
    output         : destination path for the compiled bundle.
    force          : overwrite if output already exists (default False).

    Returns the output path.
    """
    runtime_binary = Path(runtime_binary)
    gguf = Path(gguf)
    output = Path(output)

    if not runtime_binary.exists():
        raise FileNotFoundError(
            f"llamafile runtime binary not found: {runtime_binary}\n"
            "Download from https://github.com/Mozilla-Ocho/llamafile/releases"
        )
    if not gguf.exists():
        raise FileNotFoundError(f"GGUF model not found: {gguf}")
    if output.exists() and not force:
        return output

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as fh:
        fh.write(runtime_binary.read_bytes())
        fh.write(gguf.read_bytes())
    output.chmod(0o755)
    return output


def assemble_llamafile(bin_dir: Path | str) -> Path:
    """Assemble a split llamafile binary from bin/llamafile.part.* parts.

    Used when the repo ships the runtime binary split (like LuciferAI_Local).
    Returns the assembled binary path.
    Raises FileNotFoundError if neither the binary nor any parts are found.
    """
    bin_dir = Path(bin_dir)
    binary = bin_dir / "llamafile"
    if binary.exists():
        return binary

    parts = sorted(bin_dir.glob("llamafile.part.*"))
    if not parts:
        raise FileNotFoundError(
            f"No llamafile binary or split parts found in {bin_dir}.\n"
            "Download the runtime from "
            "https://github.com/Mozilla-Ocho/llamafile/releases and place it "
            "at bin/llamafile, or split it as bin/llamafile.part.aa, .ab, ..."
        )

    with binary.open("wb") as fh:
        for part in parts:
            fh.write(part.read_bytes())
    binary.chmod(0o755)
    return binary


# ═══════════════════════════════════════════════════════════════════════════════
# 2.  DISCOVER
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class GGUFEntry:
    """One discoverable GGUF model."""
    name: str        # short lowercase slug
    path: Path       # absolute resolved path
    source: str      # "artifacts" | "exports" | "external"
    size_bytes: int = 0

    def __post_init__(self) -> None:
        if self.size_bytes == 0 and self.path.exists():
            self.size_bytes = self.path.stat().st_size

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": str(self.path),
            "source": self.source,
            "size_bytes": self.size_bytes,
        }


def _slug(path: Path) -> str:
    return path.stem.lower().replace("_", "-")


class GGUFRegistry:
    """Discovers GGUFs from the package tree and any externally registered paths.

    Scan roots (relative to project root):
      artifacts/gguf/*.gguf
      exports/candidates/**/lora_train/checkpoint/*.gguf
      exports/candidates/**/gguf_export/*.gguf
    """

    _GLOBS = [
        ("artifacts/gguf/*.gguf",                              "artifacts"),
        ("exports/candidates/**/lora_train/checkpoint/*.gguf", "exports"),
        ("exports/candidates/**/gguf_export/*.gguf",           "exports"),
    ]

    def __init__(self, project_root: Path | str | None = None) -> None:
        self._root = Path(project_root) if project_root else _PROJECT_ROOT
        self._extra: list[Path] = []
        self._cache: list[GGUFEntry] | None = None

    def add_external(self, path: Path | str) -> None:
        """Register an external GGUF file."""
        self._extra.append(Path(path).resolve())
        self._cache = None

    def scan(self, *, force: bool = False) -> list[GGUFEntry]:
        """Return all discovered GGUFEntry objects (cached after first call)."""
        if self._cache is not None and not force:
            return self._cache

        seen: dict[Path, GGUFEntry] = {}

        def _add(path: Path, source: str) -> None:
            p = path.resolve()
            if p in seen or not p.exists():
                return
            seen[p] = GGUFEntry(name=_slug(p), path=p, source=source)

        for glob, source in self._GLOBS:
            for p in self._root.glob(glob):
                _add(p, source)
        for p in self._extra:
            _add(p, "external")

        self._cache = sorted(seen.values(), key=lambda e: e.name)
        return self._cache

    def resolve(self, name_or_path: str | Path) -> GGUFEntry:
        """Find a GGUF by name slug, filename stem, or direct path.

        Accepts:
          "arc-neuron-small"          → slug match
          "/abs/path/to/model.gguf"   → direct path (auto-registered)
          "relative/model.gguf"       → resolved relative to project root
        """
        # Direct file path
        p = Path(name_or_path)
        if p.suffix.lower() == ".gguf":
            if not p.is_absolute():
                p = self._root / p
            p = p.resolve()
            if p.exists():
                self.add_external(p)
                for entry in self.scan():
                    if entry.path == p:
                        return entry
            raise FileNotFoundError(f"GGUF not found: {p}")

        # Slug / stem lookup
        needle = str(name_or_path).lower().replace("_", "-")
        entries = self.scan()
        for e in entries:
            if e.name == needle:
                return e
        for e in entries:
            if needle in e.name or needle in e.path.stem.lower():
                return e

        available = [e.name for e in entries]
        raise FileNotFoundError(
            f"No GGUF found for {name_or_path!r}. "
            f"Available: {available or ['(none scanned yet)']}"
        )

    def list_models(self) -> list[dict[str, Any]]:
        return [e.as_dict() for e in self.scan()]


# module-level shared registry
_registry: GGUFRegistry | None = None


def get_registry(project_root: Path | str | None = None) -> GGUFRegistry:
    global _registry
    if _registry is None:
        _registry = GGUFRegistry(project_root)
    return _registry


# ═══════════════════════════════════════════════════════════════════════════════
# 3.  STREAM — NativeLlamafileAdapter
# ═══════════════════════════════════════════════════════════════════════════════

class NativeLlamafileAdapter(ModelAdapter):
    """Runs any GGUF via a compiled llamafile subprocess.

    No server is started.  -ngl 0 forces pure CPU execution.
    Output is read character-by-character in a background thread,
    buffered into words, and delivered one complete word at a time
    via a generator or stream_callback — matching LuciferAI_Local's
    NativeLlamafileBackend streaming model exactly.
    """

    name = "native_llamafile"
    promotable = True

    # ── init ──────────────────────────────────────────────────────────────────

    def __init__(
        self,
        *,
        # Path A: pre-compiled/assembled single binary
        llamafile_path: str | Path | None = None,
        # Path B/C: runtime binary + GGUF (compiled on first use)
        runtime_binary: str | Path | None = None,
        model_path: str | Path | None = None,
        model_name: str | None = None,
        compiled_dir: str | Path | None = None,
        # Generation settings
        max_tokens: int | None = None,
        temperature: float | None = None,
        # Timeout settings
        loading_timeout_s: float | None = None,
        inactivity_timeout_s: float | None = None,
        # Misc
        auto_assemble: bool = True,
        project_root: str | Path | None = None,
    ) -> None:

        self._root = Path(project_root) if project_root else _PROJECT_ROOT
        self._registry = GGUFRegistry(self._root)

        # Resolve runtime binary
        self._runtime_binary: Path | None = self._resolve_runtime(
            runtime_binary, auto_assemble
        )

        # Resolve GGUF
        self._gguf_path: Path | None = self._resolve_gguf(model_path, model_name)

        # Compiled output directory
        self._compiled_dir = Path(
            compiled_dir
            or os.environ.get("LLAMAFILE_COMPILED_DIR", "")
            or self._root / "bin"
        )

        # Pre-compiled binary (skips compile step entirely)
        if llamafile_path:
            self._llamafile_path: Path | None = Path(llamafile_path)
        elif os.environ.get("LLAMAFILE_BIN"):
            self._llamafile_path = Path(os.environ["LLAMAFILE_BIN"])
        else:
            self._llamafile_path = None

        # Cached compiled path (set after first compile)
        self._compiled_path: Path | None = None

        self.max_tokens: int = int(
            max_tokens or os.environ.get("LLAMAFILE_MAX_TOKENS", 512)
        )
        self.temperature: float = float(
            temperature or os.environ.get("LLAMAFILE_TEMPERATURE", 0.7)
        )
        self.loading_timeout_s: float = float(
            loading_timeout_s
            or os.environ.get("LLAMAFILE_LOADING_TIMEOUT_S", 90)
        )
        self.inactivity_timeout_s: float = float(
            inactivity_timeout_s
            or os.environ.get("LLAMAFILE_INACTIVITY_TIMEOUT_S", 45)
        )

    # ── resolution helpers ────────────────────────────────────────────────────

    def _resolve_runtime(
        self, runtime_binary: str | Path | None, auto_assemble: bool
    ) -> Path | None:
        if runtime_binary:
            return Path(runtime_binary)
        env = os.environ.get("LLAMAFILE_RUNTIME_BINARY", "")
        if env:
            return Path(env)
        if auto_assemble:
            bin_dir = self._root / "bin"
            if bin_dir.is_dir():
                try:
                    return assemble_llamafile(bin_dir)
                except FileNotFoundError:
                    pass
        return None

    def _resolve_gguf(
        self, model_path: str | Path | None, model_name: str | None
    ) -> Path | None:
        if model_path:
            p = Path(model_path)
            return (self._root / p).resolve() if not p.is_absolute() else p.resolve()
        env = os.environ.get("LLAMAFILE_MODEL", "")
        if env:
            return Path(env)
        name = model_name or os.environ.get("LLAMAFILE_MODEL_NAME", "")
        if name:
            try:
                return self._registry.resolve(name).path
            except FileNotFoundError:
                pass
        return None

    # ── compile on first use ──────────────────────────────────────────────────

    def _ensure_runnable(self) -> Path:
        """Return the path to the executable llamafile, compiling if needed."""
        # Pre-compiled binary supplied directly
        if self._llamafile_path and self._llamafile_path.exists():
            return self._llamafile_path

        # Already compiled in a prior call
        if self._compiled_path and self._compiled_path.exists():
            return self._compiled_path

        # Need both runtime binary and GGUF
        if not self._runtime_binary or not self._runtime_binary.exists():
            raise FileNotFoundError(
                "No llamafile runtime binary found.\n"
                "Provide runtime_binary=, set LLAMAFILE_RUNTIME_BINARY,\n"
                "or place bin/llamafile (or bin/llamafile.part.*) in the project.\n"
                "Download: https://github.com/Mozilla-Ocho/llamafile/releases"
            )
        if not self._gguf_path or not self._gguf_path.exists():
            available = [e.name for e in self._registry.scan()]
            raise FileNotFoundError(
                "No GGUF model found.\n"
                "Provide model_path=, model_name=, or set LLAMAFILE_MODEL.\n"
                f"Package models available: {available or ['(none)']}"
            )

        stem = self._gguf_path.stem
        output = self._compiled_dir / f"{stem}.llamafile"
        self._compiled_path = compile_llamafile(
            self._runtime_binary, self._gguf_path, output
        )
        return self._compiled_path

    # ── subprocess command ────────────────────────────────────────────────────

    def _build_cmd(self, prompt: str, system_prompt: str) -> list[str]:
        binary = str(self._ensure_runnable())

        # Format prompt with system prefix when provided
        if system_prompt.strip():
            full_prompt = (
                f"<|system|>\n{system_prompt}\n"
                f"<|user|>\n{prompt}\n"
                f"<|assistant|>\n"
            )
        else:
            full_prompt = prompt

        base_args = [
            "-p", full_prompt,
            "-n", str(self.max_tokens),
            "--temp", str(self.temperature),
            "-ngl", "0",           # CPU only — no Metal/CUDA, no server
            "--silent-prompt",     # don't echo prompt to stdout
        ]

        # Pass -m only when we have a separate GGUF (not a self-contained bundle)
        if self._gguf_path and self._gguf_path.exists():
            model_args: list[str] = ["-m", str(self._gguf_path)]
        else:
            model_args = []

        # macOS: APE binaries must be invoked via sh
        if platform.system() == "Darwin":
            return ["sh", binary] + model_args + base_args
        return [binary] + model_args + base_args

    # ── token stats from stderr ───────────────────────────────────────────────

    @staticmethod
    def _parse_token_stats(stderr: str) -> dict[str, int]:
        """Parse llama_print_timings lines from llamafile stderr.

        llamafile emits:
          llama_print_timings: prompt eval time = Xms / N tokens
          llama_print_timings: eval time        = Xms / N runs
        """
        stats = {"prompt_tokens": 0, "generated_tokens": 0, "total_tokens": 0}
        try:
            pm = re.search(
                r"prompt eval time\s*=\s*[\d.]+\s*ms\s*/\s*(\d+)\s+tokens",
                stderr,
            )
            if pm:
                stats["prompt_tokens"] = int(pm.group(1))

            gm = re.search(
                r"(?<!prompt )eval time\s*=\s*[\d.]+\s*ms\s*/\s*(\d+)\s+runs",
                stderr,
            )
            if gm:
                stats["generated_tokens"] = int(gm.group(1))

            stats["total_tokens"] = stats["prompt_tokens"] + stats["generated_tokens"]
        except Exception:
            pass
        return stats

    # ── healthcheck / inspection ──────────────────────────────────────────────

    def healthcheck(self) -> dict[str, Any]:
        runtime_ok = bool(
            self._runtime_binary and self._runtime_binary.exists()
        ) or bool(
            self._llamafile_path and self._llamafile_path.exists()
        )
        model_ok = bool(self._gguf_path and self._gguf_path.exists())
        return {
            "ok": runtime_ok and model_ok,
            "adapter": self.name,
            "runtime_binary": str(self._runtime_binary) if self._runtime_binary else None,
            "runtime_exists": runtime_ok,
            "gguf_path": str(self._gguf_path) if self._gguf_path else None,
            "gguf_exists": model_ok,
            "compiled_path": str(self._compiled_path) if self._compiled_path else None,
            "loading_timeout_s": self.loading_timeout_s,
            "inactivity_timeout_s": self.inactivity_timeout_s,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "available_models": self._registry.list_models(),
        }

    def backend_identity(self) -> dict[str, Any]:
        return {
            "adapter": self.name,
            "gguf": str(self._gguf_path) if self._gguf_path else None,
            "runtime": str(self._runtime_binary) if self._runtime_binary else None,
        }

    def list_models(self) -> list[dict[str, Any]]:
        """Return all GGUF models the package knows about."""
        return self._registry.list_models()

    def mount_model(self, name_or_path: str | Path) -> "NativeLlamafileAdapter":
        """Switch to a different model by name or path.  Returns self for chaining.

        adapter.mount_model("arc-neuron-small").generate("hello")
        adapter.mount_model("/path/to/llama3-8b.gguf").generate("hello")
        """
        entry = self._registry.resolve(name_or_path)
        self._gguf_path = entry.path
        self._compiled_path = None   # force recompile with new model
        return self

    def smokecheck(self, prompt: str = "Reply with the single word READY.") -> dict[str, Any]:
        response = self.generate(prompt, system_prompt="backend smokecheck")
        return {
            "ok": response.ok and bool(response.text.strip()),
            "text": response.text[:120],
            "error": response.error,
            "finish_reason": response.finish_reason,
            "latency_ms": response.latency_ms,
            "prompt_tokens": response.prompt_tokens,
            "completion_tokens": response.completion_tokens,
        }

    # ═══════════════════════════════════════════════════════════════════════
    # CORE: word-at-a-time streaming generator
    # ═══════════════════════════════════════════════════════════════════════

    def word_stream(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
    ) -> Generator[str, None, None]:
        """Yield one complete word at a time as llamafile generates output.

        Matching LuciferAI_Local NativeLlamafileBackend streaming exactly:
          - subprocess stdout opened with text=True, bufsize=0
          - background reader thread calls pipe.read(1) in a loop
          - main loop accumulates a word buffer, flushes on whitespace
          - newlines yielded as the single string "\\n"
          - activity timer reset on EVERY character received
          - NO wall-clock total timeout
          - loading_timeout_s fires only if process is silent from the start
          - inactivity_timeout_s fires only if generation stalls mid-stream

        Yields
        ------
        str — one word at a time, or "\\n" for line breaks.
        """
        cmd = self._build_cmd(prompt, system_prompt)
        char_queue: queue.Queue = queue.Queue()
        stderr_chunks: list[str] = []

        # ── start subprocess ──────────────────────────────────────────────
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,      # text mode — chars not bytes, matches LuciferAI
            bufsize=0,      # unbuffered — essential for low-latency streaming
        )

        # ── reader thread: read stdout one char at a time ─────────────────
        def _read_stdout(pipe, q: queue.Queue) -> None:
            try:
                while True:
                    ch = pipe.read(1)
                    if not ch:
                        break
                    q.put(ch)
            except Exception:
                pass
            finally:
                q.put(_EOF)

        # ── reader thread: drain stderr (needed for token stats) ──────────
        def _read_stderr(pipe, chunks: list) -> None:
            try:
                chunks.append(pipe.read())
            except Exception:
                pass

        stdout_thread = threading.Thread(
            target=_read_stdout, args=(proc.stdout, char_queue), daemon=True
        )
        stderr_thread = threading.Thread(
            target=_read_stderr, args=(proc.stderr, stderr_chunks), daemon=True
        )
        stdout_thread.start()
        stderr_thread.start()

        # ── streaming loop ────────────────────────────────────────────────
        word_buf: list[str] = []
        model_loading = True           # True until first character arrives
        last_activity = time.perf_counter()
        started = time.perf_counter()

        try:
            while True:
                try:
                    ch = char_queue.get(timeout=0.05)
                except queue.Empty:
                    # ── timeout checks (activity-based only) ──────────────
                    now = time.perf_counter()
                    silence = now - last_activity

                    if model_loading and silence > self.loading_timeout_s:
                        proc.kill()
                        raise RuntimeError(
                            f"llamafile: no output for {silence:.1f}s during "
                            f"model load (loading_timeout_s={self.loading_timeout_s}). "
                            "Verify the runtime binary and GGUF are valid."
                        )

                    if not model_loading and silence > self.inactivity_timeout_s:
                        proc.kill()
                        raise RuntimeError(
                            f"llamafile: generation stalled — no character for "
                            f"{silence:.1f}s "
                            f"(inactivity_timeout_s={self.inactivity_timeout_s})."
                        )
                    continue

                # ── end of stream ─────────────────────────────────────────
                if ch is _EOF:
                    if word_buf:
                        yield "".join(word_buf)
                        word_buf = []
                    break

                # ── first character: model finished loading ───────────────
                if model_loading:
                    model_loading = False

                # ── reset inactivity timer on every character ─────────────
                last_activity = time.perf_counter()

                # ── word boundary detection ───────────────────────────────
                if ch in (" ", "\t"):
                    if word_buf:
                        yield "".join(word_buf)
                        word_buf = []
                elif ch in ("\n", "\r"):
                    if word_buf:
                        yield "".join(word_buf)
                        word_buf = []
                    yield "\n"
                else:
                    word_buf.append(ch)

        finally:
            try:
                proc.kill()
            except Exception:
                pass
            try:
                proc.wait(timeout=3)
            except Exception:
                pass
            stdout_thread.join(timeout=2)
            stderr_thread.join(timeout=2)

        # surface stderr text for token stats (stored on instance for generate())
        self._last_stderr = "".join(stderr_chunks)

    # ═══════════════════════════════════════════════════════════════════════
    # generate  — standard ModelAdapter interface
    # ═══════════════════════════════════════════════════════════════════════

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        context: dict | None = None,
    ) -> ModelResponse:
        """Collect full output from word_stream and return a ModelResponse."""
        self._last_stderr = ""
        started = time.perf_counter()
        words: list[str] = []
        error: str | None = None
        finish_reason = "completed"

        try:
            for word in self.word_stream(prompt, system_prompt=system_prompt):
                words.append(word)
        except RuntimeError as exc:
            error = str(exc)
            finish_reason = "stalled" if "stalled" in error else "load_timeout"
        except FileNotFoundError as exc:
            error = str(exc)
            finish_reason = "failed"

        text = _words_to_text(words)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        stats = self._parse_token_stats(self._last_stderr)

        return ModelResponse(
            text=text,
            ok=error is None and bool(text),
            error=error,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            prompt_tokens=stats["prompt_tokens"] or None,
            completion_tokens=stats["generated_tokens"] or None,
            meta={
                "adapter": self.name,
                "gguf": str(self._gguf_path) if self._gguf_path else None,
                "word_count": sum(1 for w in words if w != "\n"),
                "token_stats": stats,
            },
            backend_identity=(
                f"{self.name}:{self._gguf_path.name}"
                if self._gguf_path else self.name
            ),
        )

    # ═══════════════════════════════════════════════════════════════════════
    # generate_streaming  — word-callback variant
    # ═══════════════════════════════════════════════════════════════════════

    def generate_streaming(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        stream_callback: Callable[[str], None] | None = None,
        context: dict | None = None,
    ) -> ModelResponse:
        """Stream words via stream_callback (one word per call) and return
        the full ModelResponse when generation is complete.

        stream_callback receives:
          - one complete word (no trailing space)
          - "\\n" for line breaks

        If stream_callback is None this behaves identically to generate().
        """
        self._last_stderr = ""
        started = time.perf_counter()
        words: list[str] = []
        error: str | None = None
        finish_reason = "completed"

        try:
            for word in self.word_stream(prompt, system_prompt=system_prompt):
                words.append(word)
                if stream_callback is not None:
                    stream_callback(word)
        except RuntimeError as exc:
            error = str(exc)
            finish_reason = "stalled" if "stalled" in error else "load_timeout"
        except FileNotFoundError as exc:
            error = str(exc)
            finish_reason = "failed"

        text = _words_to_text(words)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        stats = self._parse_token_stats(self._last_stderr)

        return ModelResponse(
            text=text,
            ok=error is None and bool(text),
            error=error,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            prompt_tokens=stats["prompt_tokens"] or None,
            completion_tokens=stats["generated_tokens"] or None,
            meta={
                "adapter": self.name,
                "gguf": str(self._gguf_path) if self._gguf_path else None,
                "word_count": sum(1 for w in words if w != "\n"),
                "token_stats": stats,
            },
            backend_identity=(
                f"{self.name}:{self._gguf_path.name}"
                if self._gguf_path else self.name
            ),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Utility
# ═══════════════════════════════════════════════════════════════════════════════

def _words_to_text(words: list[str]) -> str:
    """Reconstruct prose from a list of words and "\\n" newline tokens."""
    out: list[str] = []
    for word in words:
        if word == "\n":
            out.append("\n")
        else:
            if out and out[-1] != "\n":
                out.append(" ")
            out.append(word)
    return "".join(out).strip()
