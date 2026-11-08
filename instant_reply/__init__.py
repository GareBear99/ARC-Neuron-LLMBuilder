"""instant_reply — pre-generated replies, branch-passed with zero CPU at reply time.

Placement (Gary, 2026-11-08): this package lives in ARC-Neuron-LLMBuilder.
It is the PACK / STORE side of the instant-reply path. Lucid owns only a
thin delivery-decision client (src/lib/instantReplyPackets.ts) that speaks
the same packet contract — no pack logic lives in Lucid, no new IPC, no UI.

The idea (Gary): generate a reply ONCE, up front, pack it, store it — then
at reply time there is nothing to generate. The SPSC ring passes the causal
tick, the branch passes the already-made reply through, the hash is
verified, the reply is delivered. CPU only once, at pack time, offline.

Modules in this package (each independent, each using its own repo's
contract — nothing here reimplements another repo's logic):
  packets.py      — the packet itself: canonical bytes + packet id (SHA-256).
  apache_store.py — ARC Apache v5 pack / verify / restore / receipt, called
                    ONLY through its CLI contract (subprocess). Never imports
                    arc_apache, never copies its pack/verify logic.
  stream.py       — StreamMemory session stream: a bounded SPSC ring carrying
                    packet refs in tick order. Design-only as a repo — no
                    StreamMemory repo exists; this is the stream discipline
                    (same bound/FIFO/backpressure as Module 1, the
                    ARC-SeedCatalog SPSC ring) plus a stream-manifest
                    emitter matching ARC-Apache's stream-manifest contract.
  branches.py     — branch-pass: deliver / fall back to ping / discard.
  omnibinary.py   — OmniBinary intake record: classify a binary (GGUF /
                    packet envelope / bundle) and record its SHA-256 in the
                    OBIN v2 ledger already in this repo
                    (runtime/learning_spine.py). The real Rust omnibinary
                    tooling federation is the v1.3.0 roadmap, NOT built here.
  arcrar.py       — Arc-RAR replay/save bundle: reuse
                    build_arc_rar_bundle / read_arc_rar_manifest from
                    runtime/learning_spine.py (structurally compatible with
                    Arc-RAR). Wiring the real Rust Arc-RAR CLI is the v1.3.0
                    milestone, NOT built here.

Honest limits (read before assuming this is live):
  * No trained model exists yet, no snapshot exists yet. A packet's
    ``reply_text`` today can only come from the stock model (ping) or a
    canned/operator-supplied reply — it is pre-generation of an EXISTING
    reply, not a trained reply. The trained snapshot (GGUF + SHA-256,
    on top of the cascade before ping, SPSC triple-buffer swap both
    sides) is Phase 6 of the AI chat plan, not built.
  * The built-in inference engine is design-only. Today local is
    llamafile cold-load and ping is stock Llama 3.2 1B.
  * Nothing in this package generates a reply by itself. Packing is
    the step AFTER a reply already exists. If there is no reply to
    pack, there is no packet — the delivery decision falls back to
    ping (1 SP), never invents a reply.
"""

from __future__ import annotations

from .apache_store import ApacheNotAvailable, ApacheStore
from .arcrar import bundle_delivery, verify_bundle
from .branches import BranchPass, Delivery, decide_delivery, fallback_after_ping_error
from .connection import CallReason, ConnectionPass, should_call, what_it_carries
from .omnibinary import BinaryKind, classify_binary, intake_record
from .packets import Packet, build_packet, packet_bytes, packet_id, verify_packet
from .stream import SessionStream

__all__ = [
    "Packet",
    "build_packet",
    "packet_bytes",
    "packet_id",
    "verify_packet",
    "ApacheStore",
    "ApacheNotAvailable",
    "SessionStream",
    "BranchPass",
    "Delivery",
    "decide_delivery",
    "fallback_after_ping_error",
    "CallReason",
    "ConnectionPass",
    "should_call",
    "what_it_carries",
    "BinaryKind",
    "classify_binary",
    "intake_record",
    "bundle_delivery",
    "verify_bundle",
]
