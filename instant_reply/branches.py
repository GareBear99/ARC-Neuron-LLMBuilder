"""branches.py — branch-pass: deliver the already-made reply, or fall back.

A branch is a named snapshot/packet-set version (e.g. "track-a-v1"):
one branch, one manifest hash, one set of packets. The branch-pass is
what happens when a chat tick arrives carrying a packet ref:

  DELIVER       — packet present, hash verified, branch matches:
                  deliver the reply text verbatim. Zero CPU at reply
                  time: no generation, no re-encode — the reply was
                  generated once, at pack time, offline.
  FALLBACK_PING — no packet for this tick, or the branch has no packet
                  set: fall back to ping (1 SP, ~0.5 neurons), exactly
                  today's ping route. Never invent a reply.
  DISCARD       — packet present but hash verification failed (bytes
                  changed, wrong manifest, corrupt store): discard the
                  packet, fall back to ping. A bad packet is NEVER
                  served. The discard is recorded (returned in the
                  outcome) so it can be receipted, not silently hidden.

The decision is pure: it takes verification results, it does not do
verification itself. Hash verification happens where the bytes are
(packets.verify_packet / ARC-Apache verify); this module only decides
from the results. The Lucid client (src/lib/instantReplyPackets.ts)
mirrors this exact table.

PACKET-FIRST ORDER (Gary, 2026-11-08 — the CPU-none rule, which
overrides the AI chat plan's local-inference default): the instant-reply
flow is packet -> ping -> OpenAI (key only, server-side) -> honest
error. The local route (llamafile cold-load, a model running on the
user's machine) is NEVER a fallback in this flow — user-side CPU must
be NONE. Generation CPU is allowed only once, at pack time, server-side
/ offline. See fallback_after_ping_error() below: it is the second
fallback, after the ping route itself errors.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Delivery(str, Enum):
    DELIVER = "deliver"
    FALLBACK_PING = "fallback_ping"
    DISCARD = "discard"


@dataclass(frozen=True)
class BranchPass:
    """The outcome of one branch-pass attempt for one tick."""

    decision: Delivery
    reply_text: str | None = None
    reason: str = ""
    packet_id: str | None = None


def decide_delivery(
    *,
    packet_present: bool,
    hash_verified: bool,
    branch_matches: bool,
    reply_text: str | None,
    packet_id: str | None = None,
) -> BranchPass:
    """Decide what happens for one tick's packet ref.

    Order matters and is deliberate:
      1. No packet -> ping. (Nothing to deliver; never invent.)
      2. Packet but hash failed -> DISCARD + ping. (Never serve bad bytes.)
      3. Packet but wrong branch -> ping. (A packet from another branch
         is not this branch's reply; serving it would be a wrong answer.)
      4. Packet + hash ok + branch ok -> DELIVER the reply verbatim.
    """
    if not packet_present:
        return BranchPass(
            decision=Delivery.FALLBACK_PING,
            reason="no packet for this tick — fall back to ping (1 SP)",
            packet_id=packet_id,
        )
    if not hash_verified:
        return BranchPass(
            decision=Delivery.DISCARD,
            reason="hash verification failed — packet discarded, fall back to ping (1 SP)",
            packet_id=packet_id,
        )
    if not branch_matches:
        return BranchPass(
            decision=Delivery.FALLBACK_PING,
            reason="packet belongs to another branch — fall back to ping (1 SP)",
            packet_id=packet_id,
        )
    return BranchPass(
        decision=Delivery.DELIVER,
        reply_text=reply_text,
        reason="packet verified, branch matches — deliver verbatim, zero CPU at reply time",
        packet_id=packet_id,
    )


def fallback_after_ping_error(
    *,
    is_rate_limited: bool,
    has_api_key: bool,
    partial_reply_streamed: bool,
) -> str:
    """Second fallback after the ping route itself errors.

    Returns "openai" or "none". This is the ONLY second fallback in the
    instant-reply flow, and it is deliberately narrow (Gary, 2026-11-08):

      * Rate-limited (SP spent, 429) -> "none", always. The SP gate is
        terminal: falling through to OpenAI would spend Gary's paid
        API key to bypass a quota the user has exhausted. Never.
      * Part of the ping reply already streamed to the user ->
        "none". Appending a second model's text after partial ping
        text would serve a Franken-reply made of two models.
      * Otherwise -> "openai" iff an OpenAI key is configured, else
        "none" (honest error, no fake reply).

    The local route is NOT a fallback here, ever: running a model on
    the user's machine is user-side CPU, and Gary's rule is user-side
    CPU = NONE. The local route stays a leg of the general cascade
    outside this flow; inside this flow it is gated out. The Lucid
    handler (electron/ipc/ai.ts) and the Lucid decision client
    (src/lib/instantReplyPackets.ts) mirror this exact rule.
    """
    if is_rate_limited:
        return "none"
    if partial_reply_streamed:
        return "none"
    return "openai" if has_api_key else "none"
