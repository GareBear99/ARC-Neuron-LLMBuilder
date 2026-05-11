"""tests/test_native_llamafile_adapter.py

Full test suite for adapters/native_llamafile_adapter.py.

Covers:
  compile_llamafile    — binary + gguf concat, idempotent, force flag
  assemble_llamafile   — parts → single binary, skip-if-exists, missing-parts error
  GGUFRegistry         — scan, resolve by slug/stem/path, add_external, list_models
  NativeLlamafileAdapter
    init               — all three initialization paths
    healthcheck        — ok/not-ok cases
    _ensure_runnable   — compiles on first call, caches result
    _build_cmd         — correct flags: -ngl 0, --silent-prompt, no -m for bundles
    _parse_token_stats — real llamafile stderr format
    word_stream        — word-at-a-time, newlines, loading timeout, inactivity timeout,
                         no timeout while flowing
    generate           — full text, error propagation, token stats in meta
    generate_streaming — callback gets one word per call, not cumulative text
    mount_model        — switches GGUF, invalidates compiled cache
    smokecheck         — calls generate, returns structured dict
  model_factory        — all aliases resolve to native_llamafile
"""
from __future__ import annotations

import sys
import textwrap
import time
from pathlib import Path
from typing import List

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.native_llamafile_adapter import (
    GGUFEntry,
    GGUFRegistry,
    NativeLlamafileAdapter,
    _words_to_text,
    assemble_llamafile,
    compile_llamafile,
    get_registry,
)
from runtime.model_factory import build_adapter, normalize_adapter_name


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fake_binary(tmp_path: Path, name: str = "llamafile") -> Path:
    """A minimal executable that does nothing."""
    p = tmp_path / name
    p.write_bytes(b"\x7fELF_FAKE_RUNTIME")
    p.chmod(0o755)
    return p


def _fake_gguf(tmp_path: Path, name: str = "model.gguf") -> Path:
    p = tmp_path / name
    p.write_bytes(b"GGUF_FAKE_PAYLOAD")
    return p


def _script(tmp_path: Path, body: str, name: str = "llamafile") -> Path:
    """Create a Python script disguised as the llamafile binary."""
    p = tmp_path / name
    p.write_text("#!/usr/bin/env python3\n" + textwrap.dedent(body))
    p.chmod(0o755)
    return p


def _adapter(
    tmp_path: Path,
    runtime: Path,
    gguf: Path | None = None,
    **kwargs,
) -> NativeLlamafileAdapter:
    if gguf is None:
        gguf = _fake_gguf(tmp_path)
    return NativeLlamafileAdapter(
        runtime_binary=runtime,
        model_path=gguf,
        auto_assemble=False,
        project_root=tmp_path,
        **kwargs,
    )


# ─────────────────────────────────────────────────────────────────────────────
# compile_llamafile
# ─────────────────────────────────────────────────────────────────────────────

class TestCompileLlamafile:
    def test_concatenates_runtime_and_gguf(self, tmp_path):
        rb = _fake_binary(tmp_path, "runtime")
        gguf = _fake_gguf(tmp_path)
        out = tmp_path / "out.llamafile"

        result = compile_llamafile(rb, gguf, out)

        assert result == out
        assert out.read_bytes() == rb.read_bytes() + gguf.read_bytes()
        assert out.stat().st_mode & 0o111  # executable

    def test_idempotent_without_force(self, tmp_path):
        rb = _fake_binary(tmp_path, "runtime")
        gguf = _fake_gguf(tmp_path)
        out = tmp_path / "out.llamafile"
        out.write_bytes(b"EXISTING")

        result = compile_llamafile(rb, gguf, out)

        assert result.read_bytes() == b"EXISTING"  # not overwritten

    def test_force_overwrites(self, tmp_path):
        rb = _fake_binary(tmp_path, "runtime")
        gguf = _fake_gguf(tmp_path)
        out = tmp_path / "out.llamafile"
        out.write_bytes(b"EXISTING")

        compile_llamafile(rb, gguf, out, force=True)

        assert out.read_bytes() != b"EXISTING"

    def test_raises_if_runtime_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="runtime binary"):
            compile_llamafile(tmp_path / "nope", _fake_gguf(tmp_path), tmp_path / "out")

    def test_raises_if_gguf_missing(self, tmp_path):
        rb = _fake_binary(tmp_path)
        with pytest.raises(FileNotFoundError, match="GGUF"):
            compile_llamafile(rb, tmp_path / "nope.gguf", tmp_path / "out")

    def test_creates_parent_dirs(self, tmp_path):
        rb = _fake_binary(tmp_path, "runtime")
        gguf = _fake_gguf(tmp_path)
        out = tmp_path / "deep" / "nested" / "model.llamafile"

        compile_llamafile(rb, gguf, out)

        assert out.exists()


# ─────────────────────────────────────────────────────────────────────────────
# assemble_llamafile
# ─────────────────────────────────────────────────────────────────────────────

class TestAssembleLlamafile:
    def test_cats_parts_in_order(self, tmp_path):
        (tmp_path / "llamafile.part.aa").write_bytes(b"AAA")
        (tmp_path / "llamafile.part.ab").write_bytes(b"BBB")
        (tmp_path / "llamafile.part.ac").write_bytes(b"CCC")

        result = assemble_llamafile(tmp_path)

        assert result == tmp_path / "llamafile"
        assert result.read_bytes() == b"AAABBBCCC"
        assert result.stat().st_mode & 0o111

    def test_skips_if_binary_exists(self, tmp_path):
        binary = tmp_path / "llamafile"
        binary.write_bytes(b"PREBUILT")
        binary.chmod(0o755)

        result = assemble_llamafile(tmp_path)

        assert result.read_bytes() == b"PREBUILT"

    def test_raises_when_no_parts_and_no_binary(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="split parts"):
            assemble_llamafile(tmp_path)


# ─────────────────────────────────────────────────────────────────────────────
# GGUFRegistry
# ─────────────────────────────────────────────────────────────────────────────

class TestGGUFRegistry:
    def _make_project(self, tmp_path: Path) -> Path:
        """Create a fake project tree with GGUFs in standard locations."""
        (tmp_path / "artifacts" / "gguf").mkdir(parents=True)
        (tmp_path / "artifacts" / "gguf" / "Arc-Neuron-Small.gguf").write_bytes(b"G")
        (tmp_path / "artifacts" / "gguf" / "Arc-Tiny-Demo.gguf").write_bytes(b"G")

        export_dir = (
            tmp_path
            / "exports"
            / "candidates"
            / "pytest_run"
            / "lora_train"
            / "checkpoint"
        )
        export_dir.mkdir(parents=True)
        (export_dir / "arc_native_pytest.gguf").write_bytes(b"G")
        return tmp_path

    def test_scan_finds_artifacts_and_exports(self, tmp_path):
        root = self._make_project(tmp_path)
        reg = GGUFRegistry(root)
        names = {e.name for e in reg.scan()}
        assert "arc-neuron-small" in names
        assert "arc-tiny-demo" in names
        assert "arc-native-pytest" in names

    def test_resolve_by_exact_slug(self, tmp_path):
        root = self._make_project(tmp_path)
        reg = GGUFRegistry(root)
        entry = reg.resolve("arc-neuron-small")
        assert entry.source == "artifacts"

    def test_resolve_by_stem_substring(self, tmp_path):
        root = self._make_project(tmp_path)
        reg = GGUFRegistry(root)
        entry = reg.resolve("tiny-demo")
        assert "tiny" in entry.name

    def test_resolve_by_direct_path(self, tmp_path):
        root = self._make_project(tmp_path)
        gguf = tmp_path / "external" / "llama3.gguf"
        gguf.parent.mkdir()
        gguf.write_bytes(b"G")
        reg = GGUFRegistry(root)
        entry = reg.resolve(str(gguf))
        assert entry.source == "external"

    def test_resolve_raises_on_no_match(self, tmp_path):
        reg = GGUFRegistry(tmp_path)
        with pytest.raises(FileNotFoundError):
            reg.resolve("nonexistent-model")

    def test_add_external_registers_gguf(self, tmp_path):
        gguf = tmp_path / "custom.gguf"
        gguf.write_bytes(b"G")
        reg = GGUFRegistry(tmp_path)
        reg.add_external(gguf)
        names = {e.name for e in reg.scan()}
        assert "custom" in names

    def test_list_models_returns_dicts(self, tmp_path):
        root = self._make_project(tmp_path)
        reg = GGUFRegistry(root)
        models = reg.list_models()
        assert all({"name", "path", "source"} <= set(m) for m in models)

    def test_cache_is_invalidated_after_add_external(self, tmp_path):
        reg = GGUFRegistry(tmp_path)
        first = reg.scan()
        gguf = tmp_path / "new.gguf"
        gguf.write_bytes(b"G")
        reg.add_external(gguf)
        second = reg.scan()
        assert len(second) == len(first) + 1


# ─────────────────────────────────────────────────────────────────────────────
# NativeLlamafileAdapter — init & healthcheck
# ─────────────────────────────────────────────────────────────────────────────

class TestAdapterInit:
    def test_healthcheck_ok_with_runtime_and_gguf(self, tmp_path):
        rt = _fake_binary(tmp_path, "runtime")
        gguf = _fake_gguf(tmp_path)
        a = _adapter(tmp_path, rt, gguf)
        h = a.healthcheck()
        assert h["ok"] is True
        assert h["gguf_exists"] is True

    def test_healthcheck_fails_missing_runtime(self, tmp_path):
        gguf = _fake_gguf(tmp_path)
        a = NativeLlamafileAdapter(
            runtime_binary=tmp_path / "nope",
            model_path=gguf,
            auto_assemble=False,
        )
        assert a.healthcheck()["ok"] is False

    def test_healthcheck_fails_missing_gguf(self, tmp_path):
        rt = _fake_binary(tmp_path, "runtime")
        a = NativeLlamafileAdapter(
            runtime_binary=rt,
            model_path=tmp_path / "nope.gguf",
            auto_assemble=False,
        )
        assert a.healthcheck()["ok"] is False

    def test_healthcheck_ok_with_precompiled_binary(self, tmp_path):
        prebuilt = _fake_binary(tmp_path, "prebuilt.llamafile")
        gguf = _fake_gguf(tmp_path)
        a = NativeLlamafileAdapter(
            llamafile_path=prebuilt,
            model_path=gguf,
            auto_assemble=False,
        )
        assert a.healthcheck()["ok"] is True

    def test_healthcheck_lists_available_models(self, tmp_path):
        rt = _fake_binary(tmp_path, "runtime")
        gguf = _fake_gguf(tmp_path, "arc-small.gguf")
        # register as artifact
        art_dir = tmp_path / "artifacts" / "gguf"
        art_dir.mkdir(parents=True)
        (art_dir / "arc-small.gguf").write_bytes(b"G")
        a = _adapter(tmp_path, rt, gguf)
        h = a.healthcheck()
        assert isinstance(h["available_models"], list)

    def test_ensure_runnable_compiles_on_first_call(self, tmp_path):
        rt = _fake_binary(tmp_path, "runtime")
        gguf = _fake_gguf(tmp_path, "mymodel.gguf")
        a = _adapter(tmp_path, rt, gguf, compiled_dir=tmp_path / "bin")
        result = a._ensure_runnable()
        assert result.exists()
        assert result.name == "mymodel.llamafile"

    def test_ensure_runnable_caches_compiled_path(self, tmp_path):
        rt = _fake_binary(tmp_path, "runtime")
        gguf = _fake_gguf(tmp_path, "mymodel.gguf")
        a = _adapter(tmp_path, rt, gguf, compiled_dir=tmp_path / "bin")
        p1 = a._ensure_runnable()
        p2 = a._ensure_runnable()
        assert p1 == p2

    def test_ensure_runnable_raises_no_runtime(self, tmp_path):
        gguf = _fake_gguf(tmp_path)
        a = NativeLlamafileAdapter(model_path=gguf, auto_assemble=False)
        with pytest.raises(FileNotFoundError, match="runtime binary"):
            a._ensure_runnable()

    def test_ensure_runnable_raises_no_gguf(self, tmp_path):
        rt = _fake_binary(tmp_path, "runtime")
        a = NativeLlamafileAdapter(runtime_binary=rt, auto_assemble=False)
        with pytest.raises(FileNotFoundError, match="GGUF"):
            a._ensure_runnable()


# ─────────────────────────────────────────────────────────────────────────────
# _build_cmd
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildCmd:
    def _adapter_with_binary(self, tmp_path) -> NativeLlamafileAdapter:
        rt = _fake_binary(tmp_path, "runtime")
        gguf = _fake_gguf(tmp_path, "model.gguf")
        a = _adapter(tmp_path, rt, gguf, compiled_dir=tmp_path / "bin")
        a._ensure_runnable()          # compile so _build_cmd has a binary
        return a

    def test_contains_ngl_0(self, tmp_path):
        cmd = self._adapter_with_binary(tmp_path)._build_cmd("hi", "")
        assert "-ngl" in cmd
        assert "0" in cmd

    def test_contains_silent_prompt(self, tmp_path):
        cmd = self._adapter_with_binary(tmp_path)._build_cmd("hi", "")
        assert "--silent-prompt" in cmd

    def test_contains_m_flag_for_separate_gguf(self, tmp_path):
        cmd = self._adapter_with_binary(tmp_path)._build_cmd("hi", "")
        assert "-m" in cmd

    def test_prompt_in_cmd(self, tmp_path):
        cmd = self._adapter_with_binary(tmp_path)._build_cmd("TESTPROMPT", "")
        assert any("TESTPROMPT" in arg for arg in cmd)

    def test_system_prompt_prefixed(self, tmp_path):
        cmd = self._adapter_with_binary(tmp_path)._build_cmd("hello", "be helpful")
        full = " ".join(cmd)
        assert "<|system|>" in full
        assert "be helpful" in full


# ─────────────────────────────────────────────────────────────────────────────
# _parse_token_stats
# ─────────────────────────────────────────────────────────────────────────────

class TestParseTokenStats:
    SAMPLE_STDERR = (
        "llama_print_timings: prompt eval time = 1234.56 ms / 42 tokens\n"
        "llama_print_timings: eval time        =  987.65 ms / 128 runs\n"
    )

    def test_parses_prompt_tokens(self):
        s = NativeLlamafileAdapter._parse_token_stats(self.SAMPLE_STDERR)
        assert s["prompt_tokens"] == 42

    def test_parses_generated_tokens(self):
        s = NativeLlamafileAdapter._parse_token_stats(self.SAMPLE_STDERR)
        assert s["generated_tokens"] == 128

    def test_total_tokens_is_sum(self):
        s = NativeLlamafileAdapter._parse_token_stats(self.SAMPLE_STDERR)
        assert s["total_tokens"] == 170

    def test_returns_zeros_on_empty_stderr(self):
        s = NativeLlamafileAdapter._parse_token_stats("")
        assert s == {"prompt_tokens": 0, "generated_tokens": 0, "total_tokens": 0}

    def test_robust_to_garbage_input(self):
        s = NativeLlamafileAdapter._parse_token_stats("random garbage\n!@#$%")
        assert s["prompt_tokens"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# word_stream — uses real Python subprocesses as fake llamafile binaries
# ─────────────────────────────────────────────────────────────────────────────

class TestWordStream:
    """
    All fake llamafile scripts are Python scripts (#!/usr/bin/env python3)
    so they work cross-platform with no bash dependency.
    """

    def _streaming_adapter(
        self, tmp_path: Path, script_body: str, **kwargs
    ) -> NativeLlamafileAdapter:
        binary = _script(tmp_path, script_body)
        gguf = _fake_gguf(tmp_path)
        # Use precompiled path so _ensure_runnable returns binary directly
        return NativeLlamafileAdapter(
            llamafile_path=binary,
            model_path=gguf,
            auto_assemble=False,
            project_root=tmp_path,
            **kwargs,
        )

    def test_yields_one_word_at_a_time(self, tmp_path):
        a = self._streaming_adapter(
            tmp_path,
            "import sys\nsys.stdout.write('hello world foo bar')\n",
        )
        words = list(a.word_stream("test"))
        assert words == ["hello", "world", "foo", "bar"]

    def test_yields_newline_token(self, tmp_path):
        a = self._streaming_adapter(
            tmp_path,
            "import sys\nsys.stdout.write('line one\\nline two\\n')\n",
        )
        words = list(a.word_stream("test"))
        assert "\n" in words
        assert "one" in words
        assert "two" in words

    def test_no_double_append_words_vs_chars(self, tmp_path):
        """Words yielded must NOT duplicate: each word appears exactly once."""
        a = self._streaming_adapter(
            tmp_path,
            "import sys\nsys.stdout.write('alpha beta gamma')\n",
        )
        words = [w for w in a.word_stream("test") if w != "\n"]
        assert words == ["alpha", "beta", "gamma"]
        assert len(words) == 3

    def test_trailing_word_flushed_without_final_space(self, tmp_path):
        """Output with no trailing whitespace still yields the last word."""
        a = self._streaming_adapter(
            tmp_path,
            "import sys\nsys.stdout.write('one two three')\n",
        )
        words = [w for w in a.word_stream("test") if w != "\n"]
        assert words[-1] == "three"

    def test_loading_timeout_fires_when_silent(self, tmp_path):
        a = self._streaming_adapter(
            tmp_path,
            "import time\ntime.sleep(60)\n",
            loading_timeout_s=0.3,
        )
        t0 = time.perf_counter()
        with pytest.raises(RuntimeError, match="model load"):
            list(a.word_stream("test"))
        assert time.perf_counter() - t0 < 5.0

    def test_inactivity_timeout_fires_after_generation_starts(self, tmp_path):
        a = self._streaming_adapter(
            tmp_path,
            "import sys, time\nsys.stdout.write('hello ')\nsys.stdout.flush()\ntime.sleep(60)\n",
            inactivity_timeout_s=0.4,
        )
        t0 = time.perf_counter()
        with pytest.raises(RuntimeError, match="stalled"):
            list(a.word_stream("test"))
        assert time.perf_counter() - t0 < 5.0

    def test_no_timeout_while_tokens_flowing(self, tmp_path):
        """Slow but continuous output must complete without timeout."""
        a = self._streaming_adapter(
            tmp_path,
            "\n".join([
                "import sys, time",
                "words = ['one','two','three','four','five','six','seven','eight','nine','ten']",
                "for w in words:",
                "    sys.stdout.write(w + ' ')",
                "    sys.stdout.flush()",
                "    time.sleep(0.06)",
            ]),
            inactivity_timeout_s=2.0,
        )
        words = [w for w in a.word_stream("test") if w != "\n"]
        assert words == ["one","two","three","four","five","six","seven","eight","nine","ten"]

    def test_handles_tabs_as_word_boundary(self, tmp_path):
        a = self._streaming_adapter(
            tmp_path,
            "import sys\nsys.stdout.write('col1\\tcol2\\tcol3')\n",
        )
        words = [w for w in a.word_stream("test") if w != "\n"]
        assert words == ["col1", "col2", "col3"]

    def test_handles_unicode_output(self, tmp_path):
        a = self._streaming_adapter(
            tmp_path,
            "import sys\nsys.stdout.write('café naïve résumé')\n",
        )
        words = [w for w in a.word_stream("test") if w != "\n"]
        assert "café" in words
        assert "résumé" in words


# ─────────────────────────────────────────────────────────────────────────────
# generate
# ─────────────────────────────────────────────────────────────────────────────

class TestGenerate:
    def _adapter(self, tmp_path, script_body, **kwargs):
        binary = _script(tmp_path, script_body)
        gguf = _fake_gguf(tmp_path)
        return NativeLlamafileAdapter(
            llamafile_path=binary,
            model_path=gguf,
            auto_assemble=False,
            project_root=tmp_path,
            **kwargs,
        )

    def test_returns_model_response(self, tmp_path):
        from adapters.base import ModelResponse
        a = self._adapter(tmp_path, "import sys\nsys.stdout.write('The answer is 42')\n")
        resp = a.generate("question")
        assert isinstance(resp, ModelResponse)

    def test_ok_true_with_text(self, tmp_path):
        a = self._adapter(tmp_path, "import sys\nsys.stdout.write('hello world')\n")
        resp = a.generate("hi")
        assert resp.ok is True
        assert "hello" in resp.text
        assert resp.error is None

    def test_reconstructs_full_text_from_words(self, tmp_path):
        a = self._adapter(tmp_path, "import sys\nsys.stdout.write('one two three four five')\n")
        resp = a.generate("count")
        assert resp.text == "one two three four five"

    def test_ok_false_on_stall(self, tmp_path):
        a = self._adapter(
            tmp_path,
            "import time\ntime.sleep(60)\n",
            loading_timeout_s=0.3,
        )
        resp = a.generate("test")
        assert resp.ok is False
        assert resp.finish_reason in ("stalled", "load_timeout")
        assert resp.error is not None

    def test_ok_false_on_missing_binary(self, tmp_path):
        a = NativeLlamafileAdapter(auto_assemble=False)
        resp = a.generate("test")
        assert resp.ok is False
        assert resp.finish_reason == "failed"

    def test_token_stats_in_meta(self, tmp_path):
        stderr_line = (
            "llama_print_timings: prompt eval time = 100 ms / 10 tokens\n"
            "llama_print_timings: eval time = 200 ms / 50 runs\n"
        )
        a = self._adapter(
            tmp_path,
            f"import sys\nsys.stdout.write('hi')\nsys.stderr.write({stderr_line!r})\n",
        )
        resp = a.generate("test")
        assert "token_stats" in resp.meta

    def test_latency_ms_is_positive(self, tmp_path):
        a = self._adapter(tmp_path, "import sys\nsys.stdout.write('hi')\n")
        resp = a.generate("test")
        assert resp.latency_ms is not None
        assert resp.latency_ms > 0

    def test_word_count_in_meta(self, tmp_path):
        a = self._adapter(tmp_path, "import sys\nsys.stdout.write('one two three')\n")
        resp = a.generate("test")
        assert resp.meta["word_count"] == 3


# ─────────────────────────────────────────────────────────────────────────────
# generate_streaming
# ─────────────────────────────────────────────────────────────────────────────

class TestGenerateStreaming:
    def _adapter(self, tmp_path, script_body, **kwargs):
        binary = _script(tmp_path, script_body)
        gguf = _fake_gguf(tmp_path)
        return NativeLlamafileAdapter(
            llamafile_path=binary,
            model_path=gguf,
            auto_assemble=False,
            project_root=tmp_path,
            **kwargs,
        )

    def test_callback_receives_one_word_per_call(self, tmp_path):
        a = self._adapter(tmp_path, "import sys\nsys.stdout.write('one two three four five')\n")
        received: list[str] = []
        a.generate_streaming("test", stream_callback=received.append)
        assert received == ["one", "two", "three", "four", "five"]

    def test_callback_receives_newline_tokens(self, tmp_path):
        a = self._adapter(tmp_path, "import sys\nsys.stdout.write('line one\\nline two')\n")
        received: list[str] = []
        a.generate_streaming("test", stream_callback=received.append)
        assert "\n" in received

    def test_callback_not_cumulative_text(self, tmp_path):
        """Each callback arg must be a single word, NOT running accumulated text."""
        a = self._adapter(tmp_path, "import sys\nsys.stdout.write('alpha beta gamma')\n")
        received: list[str] = []
        a.generate_streaming("test", stream_callback=received.append)
        # No element should contain a space (which would mean it's accumulated)
        word_tokens = [r for r in received if r != "\n"]
        assert all(" " not in w for w in word_tokens)

    def test_response_text_matches_full_output(self, tmp_path):
        a = self._adapter(tmp_path, "import sys\nsys.stdout.write('the quick brown fox')\n")
        received: list[str] = []
        resp = a.generate_streaming("test", stream_callback=received.append)
        assert resp.text == "the quick brown fox"

    def test_no_callback_behaves_like_generate(self, tmp_path):
        a = self._adapter(tmp_path, "import sys\nsys.stdout.write('hello world')\n")
        resp = a.generate_streaming("test")
        assert resp.ok is True
        assert "hello" in resp.text

    def test_streaming_order_preserved(self, tmp_path):
        """Words must arrive in the same order they were emitted."""
        words_in_order = ["first", "second", "third", "fourth", "fifth"]
        output = " ".join(words_in_order)
        a = self._adapter(tmp_path, f"import sys\nsys.stdout.write({output!r})\n")
        received: list[str] = []
        a.generate_streaming("test", stream_callback=received.append)
        assert received == words_in_order


# ─────────────────────────────────────────────────────────────────────────────
# mount_model
# ─────────────────────────────────────────────────────────────────────────────

class TestMountModel:
    def test_mount_model_changes_gguf(self, tmp_path):
        rt = _fake_binary(tmp_path, "runtime")
        gguf1 = _fake_gguf(tmp_path, "model1.gguf")
        gguf2 = _fake_gguf(tmp_path, "model2.gguf")

        reg_dir = tmp_path / "artifacts" / "gguf"
        reg_dir.mkdir(parents=True)
        (reg_dir / "model2.gguf").write_bytes(b"G")

        a = _adapter(tmp_path, rt, gguf1)
        assert a._gguf_path.name == "model1.gguf"

        a.mount_model("model2")
        assert a._gguf_path.name == "model2.gguf"

    def test_mount_model_invalidates_compiled_cache(self, tmp_path):
        rt = _fake_binary(tmp_path, "runtime")
        gguf1 = _fake_gguf(tmp_path, "model1.gguf")
        a = _adapter(tmp_path, rt, gguf1, compiled_dir=tmp_path / "bin")
        a._ensure_runnable()
        old_compiled = a._compiled_path

        reg_dir = tmp_path / "artifacts" / "gguf"
        reg_dir.mkdir(parents=True)
        gguf2 = reg_dir / "model2.gguf"
        gguf2.write_bytes(b"G")

        a.mount_model("model2")
        assert a._compiled_path is None  # cache invalidated

    def test_mount_model_returns_self(self, tmp_path):
        rt = _fake_binary(tmp_path, "runtime")
        gguf = _fake_gguf(tmp_path, "model.gguf")
        reg_dir = tmp_path / "artifacts" / "gguf"
        reg_dir.mkdir(parents=True)
        (reg_dir / "model.gguf").write_bytes(b"G")
        a = _adapter(tmp_path, rt, gguf)
        result = a.mount_model("model")
        assert result is a


# ─────────────────────────────────────────────────────────────────────────────
# _words_to_text
# ─────────────────────────────────────────────────────────────────────────────

class TestWordsToText:
    def test_joins_with_spaces(self):
        assert _words_to_text(["hello", "world"]) == "hello world"

    def test_preserves_newlines(self):
        result = _words_to_text(["line", "one", "\n", "line", "two"])
        assert "line one" in result
        assert "\n" in result
        assert "line two" in result

    def test_no_leading_space_after_newline(self):
        result = _words_to_text(["before", "\n", "after"])
        assert "\n after" not in result
        assert "\nafter" in result

    def test_strips_outer_whitespace(self):
        result = _words_to_text(["\n", "word", "\n"])
        assert result == "word"

    def test_empty_list(self):
        assert _words_to_text([]) == ""

    def test_single_word(self):
        assert _words_to_text(["hello"]) == "hello"

    def test_only_newlines(self):
        assert _words_to_text(["\n", "\n"]) == ""


# ─────────────────────────────────────────────────────────────────────────────
# model_factory integration
# ─────────────────────────────────────────────────────────────────────────────

class TestModelFactory:
    @pytest.mark.parametrize("alias", [
        "native_llamafile",
        "llamafile_native",
        "llamafile_cpu",
        "llamafile_noserver",
        "llamafile_direct",
    ])
    def test_all_aliases_resolve_to_native_llamafile(self, alias):
        assert normalize_adapter_name(alias) == "native_llamafile"

    def test_build_adapter_returns_correct_type(self, tmp_path):
        rt = _fake_binary(tmp_path, "runtime")
        gguf = _fake_gguf(tmp_path)
        adapter = build_adapter(
            "native_llamafile",
            runtime_binary=rt,
            model_path=gguf,
            auto_assemble=False,
        )
        assert isinstance(adapter, NativeLlamafileAdapter)

    def test_built_adapter_healthcheck_ok(self, tmp_path):
        rt = _fake_binary(tmp_path, "runtime")
        gguf = _fake_gguf(tmp_path)
        adapter = build_adapter(
            "native_llamafile",
            runtime_binary=rt,
            model_path=gguf,
            auto_assemble=False,
        )
        assert adapter.healthcheck()["ok"] is True
