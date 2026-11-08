"""Tests for instant_reply — pre-generated replies, branch-passed.

Stdlib unittest (no pytest on this VM):
  python3 -m unittest discover -s tests -p "test_instant_reply.py" -v
from the ARC-Neuron-LLMBuilder repo root.

The ARC Apache tests use the REAL CLI (subprocess, tmp store) — the
contract test, not a mock. Everything else is pure / tmp-dir only.
No trained model, no snapshot, no network: packet replies here are
canned stock replies, which is exactly what "proven now" means.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from instant_reply import (  # noqa: E402
    ApacheStore,
    BranchPass,
    CallReason,
    Delivery,
    SessionStream,
    build_packet,
    bundle_delivery,
    classify_binary,
    decide_delivery,
    fallback_after_ping_error,
    intake_record,
    packet_bytes,
    packet_id,
    should_call,
    verify_bundle,
    verify_packet,
    what_it_carries,
)
from instant_reply.omnibinary import BinaryKind  # noqa: E402
from runtime.learning_spine import sha256_file  # noqa: E402

CANNED = "Lucid's AI chat answers from the snapshot when it matches."


def _packet(**kw):
    base = dict(
        prompt="What is Lucid?",
        reply_text=CANNED,
        model_id="stock-llama-3.2-1b",
        chat_id="chat-1",
        tick=7,
        branch="track-a-v1",
    )
    base.update(kw)
    return build_packet(base.pop("prompt"), base.pop("reply_text"), **base)


class TestPackets(unittest.TestCase):
    def test_id_is_sha256_of_canonical_bytes(self):
        p = _packet()
        self.assertEqual(packet_id(p), hashlib.sha256(packet_bytes(p)).hexdigest())
        self.assertEqual(len(packet_id(p)), 64)

    def test_same_inputs_same_id_different_tick_different_id(self):
        self.assertEqual(packet_id(_packet()), packet_id(_packet()))
        self.assertNotEqual(packet_id(_packet()), packet_id(_packet(tick=8)))

    def test_verify_ok_and_mismatch(self):
        p = _packet()
        self.assertTrue(verify_packet(p, packet_id(p)))
        self.assertFalse(verify_packet(p, "0" * 64))
        self.assertFalse(verify_packet(_packet(reply_text=CANNED + "x"), packet_id(p)))

    def test_empty_reply_and_negative_tick_rejected(self):
        with self.assertRaises(ValueError):
            _packet(reply_text="")
        with self.assertRaises(ValueError):
            _packet(tick=-1)


class TestStream(unittest.TestCase):
    def test_fifo_and_bound(self):
        s = SessionStream(capacity=3, recent_window=2)
        self.assertTrue(s.offer({"packet_id": "a", "chat_id": "c", "tick": 1, "branch": "b"}))
        self.assertTrue(s.offer({"packet_id": "b", "chat_id": "c", "tick": 2, "branch": "b"}))
        self.assertTrue(s.offer({"packet_id": "c", "chat_id": "c", "tick": 3, "branch": "b"}))
        self.assertEqual(len(s), 3)
        # Full: backpressure, counted, never silent, never grows.
        self.assertFalse(s.offer({"packet_id": "d", "chat_id": "c", "tick": 4, "branch": "b"}))
        self.assertEqual(s.refused, 1)
        self.assertEqual(len(s), 3)
        out = s.drain()
        self.assertEqual([r["packet_id"] for r in out], ["a", "b", "c"])
        self.assertEqual(len(s), 0)
        # Recent window keeps only the last 2 — window, not storage.
        self.assertEqual([r["packet_id"] for r in s.recent], ["b", "c"])

    def test_stream_manifest_links_in_tick_order(self):
        s = SessionStream(capacity=10, recent_window=10)
        s.offer({"packet_id": "p1", "chat_id": "c", "tick": 5, "branch": "b", "manifest_sha256": "m1"})
        s.offer({"packet_id": "p2", "chat_id": "c", "tick": 6, "branch": "b", "manifest_sha256": "m2"})
        s.drain()
        m = s.stream_manifest("chat-1-stream")
        self.assertEqual(m["stream_id"], "chat-1-stream")
        self.assertEqual([e["tick"] for e in m["entries"]], [5, 6])
        self.assertEqual(m["entries"][0]["packet_id"], "p1")


class TestBranches(unittest.TestCase):
    def test_deliver(self):
        r = decide_delivery(packet_present=True, hash_verified=True, branch_matches=True, reply_text=CANNED, packet_id="abc")
        self.assertEqual(r.decision, Delivery.DELIVER)
        self.assertEqual(r.reply_text, CANNED)

    def test_no_packet_falls_back_never_invents(self):
        r = decide_delivery(packet_present=False, hash_verified=False, branch_matches=False, reply_text=None)
        self.assertEqual(r.decision, Delivery.FALLBACK_PING)
        self.assertIsNone(r.reply_text)

    def test_corrupt_discards_never_serves_bad_packet(self):
        r = decide_delivery(packet_present=True, hash_verified=False, branch_matches=True, reply_text=CANNED)
        self.assertEqual(r.decision, Delivery.DISCARD)
        self.assertIsNone(r.reply_text)

    def test_wrong_branch_falls_back(self):
        r = decide_delivery(packet_present=True, hash_verified=True, branch_matches=False, reply_text=CANNED)
        self.assertEqual(r.decision, Delivery.FALLBACK_PING)
        self.assertIsNone(r.reply_text)


class TestSecondFallback(unittest.TestCase):
    """Second fallback after the ping route itself errors (Gary, 2026-11-08).

    Packet-first order: packet -> ping -> OpenAI (key only, server-side)
    -> honest error. Local is NEVER the fallback in this flow (user-side
    CPU must be NONE); rate-limit (429) is terminal (the SP gate is
    never bypassed); a partial ping reply already streamed is terminal
    (no Franken-reply from two models).
    """

    def test_clean_ping_error_with_key_falls_back_to_openai(self):
        self.assertEqual(
            fallback_after_ping_error(is_rate_limited=False, has_api_key=True, partial_reply_streamed=False),
            "openai",
        )

    def test_clean_ping_error_without_key_is_honest_error(self):
        self.assertEqual(
            fallback_after_ping_error(is_rate_limited=False, has_api_key=False, partial_reply_streamed=False),
            "none",
        )

    def test_rate_limit_is_terminal_even_with_key(self):
        # 429 = SP spent. Falling through would spend Gary's paid API
        # key to bypass a quota the user has exhausted. Never.
        self.assertEqual(
            fallback_after_ping_error(is_rate_limited=True, has_api_key=True, partial_reply_streamed=False),
            "none",
        )

    def test_partial_stream_is_terminal_even_with_key(self):
        self.assertEqual(
            fallback_after_ping_error(is_rate_limited=False, has_api_key=True, partial_reply_streamed=True),
            "none",
        )


class TestConnection(unittest.TestCase):
    def test_snapshot_needed_beats_token_check(self):
        self.assertEqual(
            should_call(snapshot_present=False, snapshot_hash_matches=False, snapshot_corrupt=False, token_check_needed=True),
            CallReason.SNAPSHOT_NEEDED,
        )
        self.assertEqual(
            should_call(snapshot_present=True, snapshot_hash_matches=False, snapshot_corrupt=False, token_check_needed=False),
            CallReason.SNAPSHOT_NEEDED,
        )
        self.assertEqual(
            should_call(snapshot_present=True, snapshot_hash_matches=True, snapshot_corrupt=True, token_check_needed=False),
            CallReason.SNAPSHOT_NEEDED,
        )

    def test_token_check_only_when_snapshot_fine(self):
        self.assertEqual(
            should_call(snapshot_present=True, snapshot_hash_matches=True, snapshot_corrupt=False, token_check_needed=True),
            CallReason.TOKENS_CURRENT,
        )

    def test_not_called_when_local_is_fine(self):
        self.assertEqual(
            should_call(snapshot_present=True, snapshot_hash_matches=True, snapshot_corrupt=False, token_check_needed=False),
            CallReason.NOT_CALLED,
        )
        self.assertEqual(what_it_carries(CallReason.NOT_CALLED), [])
        self.assertIn("manifest", what_it_carries(CallReason.SNAPSHOT_NEEDED)[0])
        self.assertIn("token check", what_it_carries(CallReason.TOKENS_CURRENT)[0])


class TestApacheStore(unittest.TestCase):
    """Real CLI contract test: pack -> verify -> restore byte-identical."""

    def test_pack_verify_restore_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / ".arc_apache"
            apache = ApacheStore()
            apache.init_store(store)
            p = _packet()
            manifest = apache.pack_packet(p, store)
            self.assertEqual(manifest["version"], 5)
            self.assertEqual(manifest["content_class"], "instant_reply")
            self.assertEqual(len(manifest["manifest_sha256"]), 64)
            self.assertEqual(len(manifest["merkle_root"]), 64)
            ok, errors = apache.verify_manifest(manifest, store)
            self.assertTrue(ok, errors)
            out = Path(td) / "restored.json"
            apache.restore_packet(manifest, store, out)
            self.assertEqual(out.read_bytes(), packet_bytes(p))
            receipt = apache.receipt_for(manifest, store)
            self.assertIn("receipt_sha256", receipt)

    def test_missing_cli_fails_loudly(self):
        with self.assertRaises(RuntimeError):
            ApacheStore(apache_root="/nonexistent-arc-apache")


class TestOmnibinaryAndArcRar(unittest.TestCase):
    def test_intake_record_and_classify(self):
        with tempfile.TemporaryDirectory() as td:
            gguf = Path(td) / "model.gguf"
            gguf.write_bytes(b"GGUF" + b"\x00" * 100)
            self.assertEqual(classify_binary(gguf), BinaryKind.GGUF)
            rec = intake_record(gguf, Path(td) / "ledger.obin")
            self.assertEqual(rec["sha256"], sha256_file(gguf))
            self.assertEqual(rec["kind"], "gguf")
            with self.assertRaises(FileNotFoundError):
                intake_record(Path(td) / "missing.gguf", Path(td) / "ledger.obin")

    def test_bundle_delivery_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            p = _packet()
            manifest = {"manifest_sha256": "a" * 64, "merkle_root": "b" * 64}
            bundle = bundle_delivery(
                bundle_path=td / "delivery.arcrar.zip",
                packet_bytes=packet_bytes(p),
                packet_id=packet_id(p),
                chat_id="chat-1",
                tick=7,
                branch="track-a-v1",
                manifest=manifest,
                receipts=[{"receipt_sha256": "c" * 64}],
                tick_log=[{"tick": 7, "packet_id": packet_id(p)}],
            )
            self.assertEqual(bundle["sha256"], sha256_file(td / "delivery.arcrar.zip"))
            back = verify_bundle(td / "delivery.arcrar.zip")
            self.assertEqual(back["packet_id"], packet_id(p))
            self.assertEqual(back["apache_manifest_sha256"], "a" * 64)


if __name__ == "__main__":
    unittest.main()
