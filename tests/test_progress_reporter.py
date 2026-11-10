"""Tests for the chain progress reporter (scripts/training/progress.py)
and the trainer's event-driven progress callback (train_lora.py).

Stdlib unittest only — run with:
    python3 -m unittest tests.test_progress_reporter -v
(or pytest, which also collects unittest.TestCase).

These prove:
  * compute_percent / render_bar — the percent and the ASCII bar are
    COMPUTED ON THE TRAINING SIDE (the GPU side), not on the neuron
    side. The neuron side stores/serves them verbatim.
  * ProgressReporter — disabled without a key (silent no-op, no
    network); report() POSTs the computed percent + bar; a failed
    POST never raises (fire-and-forget).
  * _ProgressCallback — event-driven batching: the first log posts,
    later logs post only after >= 10 steps AND >= 30s since the last
    POST; on_log never raises, even if the reporter does.
"""

import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

# Import the training scripts by path (they live in scripts/training/).
TRAINING_DIR = Path(__file__).resolve().parents[1] / "scripts" / "training"
sys.path.insert(0, str(TRAINING_DIR))

import progress as progress_mod
from progress import ProgressReporter, compute_percent, render_bar, report_progress


class ComputePercentTests(unittest.TestCase):
    def test_step_over_total(self):
        self.assertEqual(compute_percent(0, 152), 0.0)
        self.assertEqual(compute_percent(76, 152), 50.0)
        self.assertEqual(compute_percent(42, 152), 27.6)
        self.assertEqual(compute_percent(152, 152), 100.0)

    def test_clamped(self):
        self.assertEqual(compute_percent(200, 152), 100.0)
        self.assertEqual(compute_percent(-5, 152), 0.0)

    def test_explicit_only_without_total(self):
        self.assertEqual(compute_percent(None, None, 75), 75.0)
        self.assertEqual(compute_percent(5, None, 250), 100.0)

    def test_none_without_basis(self):
        self.assertIsNone(compute_percent(None, None))
        self.assertIsNone(compute_percent(5, 0))
        self.assertIsNone(compute_percent(5, None))


class RenderBarTests(unittest.TestCase):
    def test_widths(self):
        self.assertEqual(render_bar(0), "[" + "░" * 20 + "] 0.0%")
        self.assertEqual(render_bar(50), "[" + "█" * 10 + "░" * 10 + "] 50.0%")
        self.assertEqual(render_bar(100), "[" + "█" * 20 + "] 100.0%")
        self.assertEqual(render_bar(27.6), "[" + "█" * 6 + "░" * 14 + "] 27.6%")

    def test_none_is_empty(self):
        self.assertEqual(render_bar(None), "")


class ProgressReporterTests(unittest.TestCase):
    def test_disabled_without_key_is_a_silent_noop(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            r = ProgressReporter(url="http://127.0.0.1:9", key="")
            self.assertFalse(r.enabled)
            # No network attempt at all: returns False, never raises.
            with mock.patch.object(progress_mod.urllib.request, "urlopen") as urlopen:
                self.assertFalse(r.report(stage="train", step=1, total=10))
                urlopen.assert_not_called()

    def test_report_posts_computed_percent_and_bar(self):
        captured = {}

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return json.dumps({"ok": True}).encode()

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["headers"] = dict(req.headers)
            captured["body"] = json.loads(req.data.decode())
            captured["timeout"] = timeout
            return FakeResponse()

        with mock.patch.object(progress_mod.urllib.request, "urlopen", fake_urlopen):
            r = ProgressReporter(url="http://127.0.0.1:8787", key="test-key", run_id="run-1")
            self.assertTrue(r.report(stage="train", step=42, total=152, loss=1.2,
                                     eta_seconds=540, message="Training step 42/152"))
        self.assertEqual(captured["url"], "http://127.0.0.1:8787/admin/progress")
        self.assertEqual(captured["headers"].get("X-lucid-ping-key"), "test-key")
        body = captured["body"]
        self.assertEqual(body["stage"], "train")
        self.assertEqual(body["step"], 42)
        self.assertEqual(body["total"], 152)
        # Percent + bar were COMPUTED HERE (training side), not server-side.
        self.assertEqual(body["percent"], 27.6)
        self.assertEqual(body["bar"], "[" + "█" * 6 + "░" * 14 + "] 27.6%")
        self.assertEqual(body["loss"], 1.2)
        self.assertEqual(body["eta_seconds"], 540)
        self.assertEqual(body["run_id"], "run-1")
        self.assertLessEqual(captured["timeout"], 5)

    def test_completed_forces_100_percent(self):
        captured = {}

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return json.dumps({"ok": True}).encode()

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode())
            return FakeResponse()

        with mock.patch.object(progress_mod.urllib.request, "urlopen", fake_urlopen):
            r = ProgressReporter(url="http://127.0.0.1:8787", key="k")
            self.assertTrue(r.report(stage="train", status="completed", step=100, total=152))
        self.assertEqual(captured["body"]["percent"], 100.0)
        self.assertEqual(captured["body"]["bar"], "[" + "█" * 20 + "] 100.0%")

    def test_failed_post_never_raises(self):
        def boom(req, timeout=None):
            raise ConnectionError("server down")

        with mock.patch.object(progress_mod.urllib.request, "urlopen", boom):
            r = ProgressReporter(url="http://127.0.0.1:8787", key="k")
            self.assertFalse(r.report(stage="train", step=1, total=10))

    def test_report_progress_convenience_uses_env(self):
        with mock.patch.dict(os.environ, {"LUCID_PING_URL": "http://127.0.0.1:8787",
                                          "LUCID_PING_KEY": "env-key"}):
            with mock.patch.object(progress_mod.urllib.request, "urlopen") as urlopen:
                resp = mock.MagicMock()
                resp.status = 200
                resp.read.return_value = json.dumps({"ok": True}).encode()
                resp.__enter__.return_value = resp
                urlopen.return_value = resp
                self.assertTrue(report_progress(stage="merge", step=1, total=3,
                                               status="completed"))
                req = urlopen.call_args[0][0]
                self.assertEqual(req.headers.get("X-lucid-ping-key"), "env-key")


class ProgressCallbackTests(unittest.TestCase):
    """The trainer's _ProgressCallback (event-driven, batched)."""

    def setUp(self):
        import train_lora
        self.train_lora = train_lora

    def _fake_state(self, step, total):
        state = SimpleNamespace(global_step=step, max_steps=total)
        return state

    def test_first_log_posts_then_batches(self):
        calls = []

        class FakeReporter:
            def report(self, **kwargs):
                calls.append(kwargs)
                return True

        cb = self.train_lora._ProgressCallback(FakeReporter(), "run-1")
        # First log (step 10): posts.
        cb.on_log(None, self._fake_state(10, 152), None, logs={"loss": 2.0})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["step"], 10)
        self.assertEqual(calls[0]["loss"], 2.0)
        # Step 15 (< 10 steps since last post): suppressed.
        cb.on_log(None, self._fake_state(15, 152), None, logs={"loss": 1.9})
        self.assertEqual(len(calls), 1)
        # Step 20 (>= 10 steps) but < 30s since last post: suppressed.
        cb.on_log(None, self._fake_state(20, 152), None, logs={"loss": 1.8})
        self.assertEqual(len(calls), 1)
        # Step 20 after 31s: posts.
        cb.last_post_at -= 31.0
        cb.on_log(None, self._fake_state(20, 152), None, logs={"loss": 1.8})
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1]["step"], 20)

    def test_on_log_never_raises(self):
        class BoomReporter:
            def report(self, **kwargs):
                raise RuntimeError("boom")

        cb = self.train_lora._ProgressCallback(BoomReporter(), "run-1")
        # Must not raise, even when the reporter explodes.
        cb.on_log(None, self._fake_state(10, 152), None, logs={"loss": 2.0})
        cb.on_log(None, None, None, logs=None)

    def test_make_reporter_returns_none_without_key(self):
        args = SimpleNamespace(progress_url=None, progress_key=None)
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(self.train_lora._make_progress_reporter(args, "run-1"))


if __name__ == "__main__":
    unittest.main()
