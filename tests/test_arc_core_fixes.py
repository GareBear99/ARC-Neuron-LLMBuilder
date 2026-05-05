"""tests/test_arc_core_fixes.py

Covers every finding from the DARPA-level audit:

1. Shared transformer base — arc_tiny and arc_neuron_small must not share
   any mutable class state; architecture bug fixed in one propagates to both.

2. Rubric scorer bug — avoids_false_certainty must NOT fire on short/empty
   outputs; only awards the point when the text is substantial.

3. GGUF I/O round-trip — write_gguf / read_gguf must be lossless (F32).

4. arc-native training smoke — train_arc_native_candidate produces real .pt
   and .gguf artifacts and a correct manifest in under 60 s (tiny tier,
   10 steps).

5. train_lora_candidate routing — detects arc-native base models and routes
   to the native path instead of scaffold.
"""
from __future__ import annotations

import gc
import json
import contextlib
import io
import os
import runpy
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch", reason="torch not installed — skipping transformer/GGUF tests")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _run_training_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run repo training scripts in-process for deterministic CI smoke tests.

    The tests already import and execute PyTorch models before reaching the CLI
    checks. On older CPUs and constrained Linux containers, forking a second
    Python/PyTorch process after OpenMP worker pools have initialized can hang.
    This helper preserves the command-line contract by patching ``sys.argv`` and
    executing the target script as ``__main__``, while still returning a
    CompletedProcess-shaped object for the existing assertions.
    """
    gc.collect()
    torch.set_num_threads(1)
    old_argv = sys.argv[:]
    old_env = {k: os.environ.get(k) for k in (
        "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"
    )}
    os.environ.update({
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "ARC_NATIVE_INPROCESS": "1",
        "ARC_NATIVE_SMOKE_FAST": "1",
    })
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = 0
    try:
        script = Path(args[1])
        sys.argv = [str(script), *args[2:]]
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                runpy.run_path(str(script), run_name="__main__")
            except SystemExit as exc:
                code = int(exc.code or 0) if isinstance(exc.code, int) else 1
    except Exception as exc:
        code = 1
        stderr.write(f"{type(exc).__name__}: {exc}\n")
    finally:
        sys.argv = old_argv
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return subprocess.CompletedProcess(args=args, returncode=code, stdout=stdout.getvalue(), stderr=stderr.getvalue())


# ── 1. Shared transformer base ────────────────────────────────────────────────

def test_shared_base_import():
    from arc_core.transformer import CausalTransformerLM, TransformerConfig
    from arc_tiny.model import TinyConfig, TinyTransformerLM
    from arc_neuron_small.model import SmallConfig, SmallTransformerLM
    assert TinyTransformerLM  is CausalTransformerLM, "arc_tiny must alias CausalTransformerLM"
    assert SmallTransformerLM is CausalTransformerLM, "arc_neuron_small must alias CausalTransformerLM"


def test_tiny_and_small_configs_differ():
    from arc_tiny.model import TinyConfig
    from arc_neuron_small.model import SmallConfig
    t, s = TinyConfig(), SmallConfig()
    assert t.block_size != s.block_size, "Tiny and Small must have different block_size"
    assert t.n_layer    != s.n_layer,    "Tiny and Small must have different n_layer"


def test_shared_base_forward_tiny():
    from arc_tiny.model import TinyConfig, TinyTransformerLM
    cfg = TinyConfig(vocab_size=256, block_size=16, n_layer=1, n_head=2, n_embd=16)
    model = TinyTransformerLM(cfg)
    idx = torch.randint(0, 256, (2, 10))
    logits, loss = model(idx, targets=idx)
    assert logits.shape == (2, 10, 256)
    assert loss is not None


def test_shared_base_forward_small():
    from arc_neuron_small.model import SmallConfig, SmallTransformerLM
    cfg = SmallConfig(vocab_size=256, block_size=32, n_layer=2, n_head=4, n_embd=32)
    model = SmallTransformerLM(cfg)
    idx = torch.randint(0, 256, (1, 20))
    logits, loss = model(idx, targets=idx)
    assert logits.shape == (1, 20, 256)
    assert loss is not None


def test_weight_tying():
    """Output head and token embedding must share the same tensor (weight tying)."""
    from arc_core.transformer import CausalTransformerLM, TransformerConfig
    cfg = TransformerConfig(vocab_size=64, block_size=8, n_layer=1, n_head=2, n_embd=16)
    model = CausalTransformerLM(cfg)
    assert model.head.weight.data_ptr() == model.token_emb.weight.data_ptr(), \
        "head.weight and token_emb.weight must be the same tensor (weight tying)"


def test_block_size_guard():
    """Sequences longer than block_size must raise ValueError, not silently corrupt."""
    from arc_core.transformer import CausalTransformerLM, TransformerConfig
    cfg = TransformerConfig(vocab_size=64, block_size=8, n_layer=1, n_head=2, n_embd=16)
    model = CausalTransformerLM(cfg)
    idx = torch.zeros(1, 9, dtype=torch.long)   # 9 > block_size=8
    with pytest.raises(ValueError, match="block_size"):
        model(idx)


def test_param_count_property():
    from arc_core.transformer import CausalTransformerLM, TransformerConfig
    cfg = TransformerConfig(vocab_size=256, block_size=64, n_layer=2, n_head=4, n_embd=64)
    model = CausalTransformerLM(cfg)
    assert model.param_count() > 0
    # param_count_approx should be in the same order of magnitude
    approx = cfg.param_count_approx
    real   = model.param_count()
    assert 0.5 < approx / real < 2.0, f"param_count_approx={approx} too far from real={real}"


# ── 2. Rubric scorer bug ──────────────────────────────────────────────────────

def test_rubric_avoids_false_certainty_no_fire_on_short_text():
    """A one-word or very short output must NOT earn the avoids_false_certainty point."""
    from scorers.rubric import score_record
    result = score_record("ok", task={"capability": "calibration"})
    assert "avoids_false_certainty" not in result["matched_checks"], \
        "Short text must not earn avoids_false_certainty"


def test_rubric_avoids_false_certainty_no_fire_on_empty():
    from scorers.rubric import score_record
    result = score_record("", task={"capability": "calibration"})
    assert result["raw_score"] == 0
    assert "avoids_false_certainty" not in result["matched_checks"]


def test_rubric_avoids_false_certainty_fires_on_substantial_text():
    """Substantial text without overconfidence words should earn the point."""
    substantial = (
        "Based on the available evidence, this approach is likely to succeed. "
        "There is uncertainty about the edge cases, and confidence is bounded "
        "by our limited observability of the downstream system."
    )
    from scorers.rubric import score_record
    result = score_record(substantial, task={"capability": "calibration"})
    assert "avoids_false_certainty" in result["matched_checks"], \
        "Substantial text without overconfidence words should earn avoids_false_certainty"


def test_rubric_avoids_false_certainty_blocked_by_bad_word():
    """Substantial text WITH overconfidence words must NOT earn the point."""
    text = (
        "I am definitely certain this will work. "
        "The outcome is guaranteed and there is no risk of failure. "
        "Based on evidence this is certainly the right approach to take here."
    )
    from scorers.rubric import score_record
    result = score_record(text, task={"capability": "calibration"})
    assert "avoids_false_certainty" not in result["matched_checks"], \
        "Text with overconfidence words must not earn avoids_false_certainty"


def test_rubric_avoids_additional_claims_not_on_short_text():
    from scorers.rubric import score_record
    result = score_record("yes", task={"capability": "paraphrase_stability"})
    assert "avoids_additional_claims" not in result["matched_checks"]


def test_rubric_empty_returns_zero():
    from scorers.rubric import score_record
    result = score_record("")
    assert result["raw_score"] == 0
    assert result["normalized_score"] == 0.0


def test_rubric_all_capabilities_score():
    """Every declared capability should score without raising an exception."""
    from scorers.rubric import score_record
    capabilities = [
        "planning", "reasoning", "critique", "repair",
        "compression", "calibration", "paraphrase_stability",
        "quantization_retention", "generic",
    ]
    long_text = (
        "First, we plan the smallest targeted steps to preserve the existing interface "
        "and validate the outcome. Risk exists around regression and blast radius. "
        "Evidence is required before promotion. Confidence is bounded; we may need "
        "further validation. The goal is to retain core behavior without additional "
        "promises. Fix is narrow, surgical, and includes a regression test. "
        "Given only the available evidence, inference is bounded."
    )
    for cap in capabilities:
        result = score_record(long_text, task={"capability": cap})
        assert isinstance(result["normalized_score"], float)
        assert 0.0 <= result["normalized_score"] <= 1.0


# ── 3. GGUF I/O round-trip ───────────────────────────────────────────────────

def test_gguf_roundtrip_lossless():
    from arc_tiny.gguf_io import write_gguf, read_gguf
    rng = np.random.default_rng(42)
    tensors_in = {
        "layer0.weight": rng.standard_normal((16, 8)).astype(np.float32),
        "layer0.bias":   rng.standard_normal((16,)).astype(np.float32),
        "layer1.weight": rng.standard_normal((8, 16)).astype(np.float32),
    }
    metadata_in = {
        "general.architecture": "test",
        "general.alignment":    32,
        "general.name":         "roundtrip test",
        "arc_test.vocab_size":  256,
        "arc_test.flag":        True,
        "arc_test.scale":       0.5,
        "arc_test.tokens":      ["a", "b", "c"],
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.gguf"
        write_gguf(path, metadata_in, tensors_in)
        assert path.stat().st_size > 0
        metadata_out, tensors_out = read_gguf(path)
    for key, arr_in in tensors_in.items():
        assert key in tensors_out, f"Missing tensor: {key}"
        np.testing.assert_array_equal(arr_in, tensors_out[key],
                                      err_msg=f"Tensor {key} not lossless")
    for key, val in metadata_in.items():
        assert key in metadata_out, f"Missing metadata key: {key}"
        assert metadata_out[key] == val, f"Metadata mismatch for {key}"


def test_gguf_bad_magic_raises():
    from arc_tiny.gguf_io import read_gguf
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "bad.gguf"
        path.write_bytes(b"NOPE" + b"\x00" * 100)
        with pytest.raises(ValueError, match="not a GGUF"):
            read_gguf(path)


def test_gguf_alignment_constraint():
    from arc_tiny.gguf_io import write_gguf
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "bad_align.gguf"
        with pytest.raises(ValueError, match="alignment"):
            write_gguf(path, {"general.alignment": 7}, {"w": np.zeros((4,), np.float32)})


# ── 4. ARC-native training smoke ─────────────────────────────────────────────

def test_arc_native_training_tiny_smoke():
    """10-step tiny training must produce .pt, .gguf, and a valid manifest."""
    script = ROOT / "scripts" / "training" / "train_arc_native_candidate.py"
    candidate = "pytest_arc_native_tiny"
    proc = _run_training_cli([
        sys.executable, str(script),
        "--candidate", candidate,
        "--tier", "tiny",
        "--steps", "10",
        "--batch-size", "4",
    ])
    assert proc.returncode == 0, f"Native training failed:\n{proc.stderr[-2000:]}"

    # Parse the JSON summary line from stdout
    summary: dict = {}
    for line in reversed(proc.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                summary = json.loads(line)
                break
            except Exception:
                pass
    assert summary.get("ok") is True, f"Expected ok=True, got: {summary}"

    # Verify artifacts exist
    pt_path   = ROOT / summary["pt"]
    gguf_path = ROOT / summary["gguf"]
    assert pt_path.exists(),   f"Missing .pt: {pt_path}"
    assert gguf_path.exists(), f"Missing .gguf: {gguf_path}"
    assert gguf_path.stat().st_size > 0

    # Verify the GGUF is readable
    from arc_tiny.gguf_io import read_gguf
    metadata, tensors = read_gguf(gguf_path)
    assert metadata.get("general.architecture") == "arc_tiny"
    assert len(tensors) > 0

    # Verify the PyTorch checkpoint loads cleanly
    ckpt = torch.load(pt_path, map_location="cpu", weights_only=False)
    assert "state_dict" in ckpt
    assert ckpt.get("tier") == "tiny"
    assert ckpt.get("train_steps") == 10

    # Verify manifest exists and has completed status
    manifest_path = (
        ROOT / "exports" / "candidates" / candidate / "lora_train" / "artifact_manifest.json"
    )
    assert manifest_path.exists(), f"Missing manifest: {manifest_path}"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["status"] == "completed"
    assert manifest["execution_mode"] == "arc_native"
    assert "val_ppl" in manifest["training"]


def test_arc_native_training_small_smoke():
    """10-step small training: same assertions as tiny but with small tier."""
    script = ROOT / "scripts" / "training" / "train_arc_native_candidate.py"
    candidate = "pytest_arc_native_small"
    proc = _run_training_cli([
        sys.executable, str(script),
        "--candidate", candidate,
        "--tier", "small",
        "--steps", "10",
        "--batch-size", "4",
    ])
    assert proc.returncode == 0, f"Native small training failed:\n{proc.stderr[-2000:]}"
    for line in reversed(proc.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            summary = json.loads(line)
            assert summary["ok"] is True
            gguf_path = ROOT / summary["gguf"]
            assert gguf_path.exists()
            from arc_tiny.gguf_io import read_gguf
            metadata, tensors = read_gguf(gguf_path)
            assert metadata["general.architecture"] == "arc_small"
            assert len(tensors) > 0
            break


# ── 5. train_lora_candidate routing ──────────────────────────────────────────

def test_lora_candidate_routes_arc_native():
    """train_lora_candidate.py with --base-model arc_neuron_small must invoke
    the native path and produce a completed manifest."""
    script = ROOT / "scripts" / "training" / "train_lora_candidate.py"
    candidate = "pytest_lora_arc_native_routing"
    proc = _run_training_cli([
        sys.executable, str(script),
        "--candidate", candidate,
        "--base-model", "arc_neuron_small",
        "--steps", "8",
        "--batch-size", "2",
    ])
    assert proc.returncode == 0, f"Routing test failed:\n{proc.stderr[-2000:]}"
    output = json.loads(
        next(
            (l for l in reversed(proc.stdout.splitlines()) if l.strip().startswith("{")),
            "{}"
        )
    )
    assert output.get("ok") is True
    assert output.get("arc_native") is True

    manifest_path = (
        ROOT / "exports" / "candidates" / candidate / "lora_train" / "artifact_manifest.json"
    )
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["status"] == "completed"


def test_lora_candidate_scaffold_for_unknown_base():
    """Unknown/external base models must still produce a scaffold manifest without erroring."""
    script = ROOT / "scripts" / "training" / "train_lora_candidate.py"
    candidate = "pytest_lora_scaffold"
    proc = subprocess.run(
        [
            sys.executable, str(script),
            "--candidate", candidate,
            "--base-model", "qwen3_coder_480b",
            "--mode", "scaffold",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, f"Scaffold failed:\n{proc.stderr}"
    output = json.loads(
        next(
            (l for l in reversed(proc.stdout.splitlines()) if l.strip().startswith("{")),
            "{}"
        )
    )
    assert output.get("ok") is True
    manifest_path = (
        ROOT / "exports" / "candidates" / candidate / "lora_train" / "artifact_manifest.json"
    )
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["status"] == "scaffold_ready"
