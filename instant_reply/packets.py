"""packets.py — the pre-generated reply packet.

A packet is ONE reply, already generated, frozen as canonical bytes.
Nothing in this module generates a reply: it only freezes a reply that
already exists (from the stock model, or operator-supplied) so it can be
packed, stored, verified, and delivered later with zero CPU at reply time.

Packet identity is cryptographic and nothing else: the packet id is the
SHA-256 of the canonical bytes. Same bytes -> same id. One byte changed
-> a different id, and verification fails. The id is how the branch-pass
knows exactly which reply it is delivering, and how the client knows the
bytes it received are the bytes that were packed.

Canonical form: JSON, keys sorted, UTF-8, no whitespace. The reply text
itself is stored verbatim — packing never edits, truncates, or rewords it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Packet:
    """One pre-generated reply.

    prompt: the exact user prompt this reply answers (verbatim).
    reply_text: the already-generated reply (verbatim, never edited).
    model_id: which model generated it, e.g. "stock-llama-3.2-1b"
        (no trained model exists yet — see package docstring).
    chat_id: the chat this reply belongs to (ticks are per-chat).
    tick: the causal ritual tick this reply answers (per-chat, monotonic).
    branch: the branch (snapshot/packet-set version) this packet belongs to.
    """

    prompt: str
    reply_text: str
    model_id: str
    chat_id: str
    tick: int
    branch: str


def packet_bytes(packet: Packet) -> bytes:
    """Canonical bytes of a packet: JSON, sorted keys, UTF-8, no whitespace."""
    return json.dumps(
        asdict(packet), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def packet_id(packet: Packet) -> str:
    """The packet id: SHA-256 of the canonical bytes (hex, 64 chars)."""
    return hashlib.sha256(packet_bytes(packet)).hexdigest()


def build_packet(
    prompt: str,
    reply_text: str,
    *,
    model_id: str,
    chat_id: str,
    tick: int,
    branch: str,
) -> Packet:
    """Freeze an already-generated reply into a packet.

    Raises ValueError on an empty reply or a negative tick — an empty
    reply is not a reply, and ticks are never negative. The caller must
    have generated (or been given) reply_text already; this function
    never generates anything.
    """
    if not reply_text:
        raise ValueError("build_packet needs a non-empty reply_text — it never invents one")
    if tick < 0:
        raise ValueError("tick must be >= 0 (causal ticks are monotonic, per chat)")
    return Packet(
        prompt=prompt,
        reply_text=reply_text,
        model_id=model_id,
        chat_id=chat_id,
        tick=tick,
        branch=branch,
    )


def verify_packet(packet: Packet, expected_id: str) -> bool:
    """True iff this packet's bytes hash to the expected id.

    Any difference — text, prompt, tick, branch, model — changes the id
    and fails verification. A failed packet is discarded by the
    branch-pass, never served.
    """
    return packet_id(packet) == expected_id
