"""connection.py — the Connection module: the pass.

CORRECTION (Gary's "find out" check, 2026-11-08): the ARC items in
this package (SeedCatalog ring, ARC Apache, StreamMemory, OmniBinary,
Arc-RAR) are ARC ecosystem modules / links — NOT Lucid segments.
Lucid segments are a closed list (src/lib/segmentCategories.ts):
about, computer-control, ai-chat, google-drive, telegram, stripe,
starship, forge-persona-plex. Starship modules would only show up AS
segments when a starship is detected, which hasn't happened.

The Connection is the exception: it is the bridge TO the AI Chat
segment — "a place other things can connect to" (segment info text).
It connects the snapshot to the AI chat; it is not itself a segment,
and it does not add a segment.

What the Connection IS (Gary's own words, 2026-11-08):
  "the only pass is the github io cloudflare reciever and transmitter
   when called for snapshot or current for mainline tokens"

  * GitHub IO holds the manifest / record: version, SHA-256 hash,
    download URL, what changed. That is the record the client checks.
    (The GGUF binary itself lives in R2, free egress — the manifest
    on GitHub IO points at it. The repo holds the record; R2 holds
    the bytes. See the AI chat plan §2b.)
  * Cloudflare is the receiver / transmitter: the ping-server Worker
    receives a request and transmits the answer — the snapshot
    download check and the current-token (SP) check. It is called,
    it answers, it goes quiet. There is no always-on connection.

When it is called (ONLY these two cases — otherwise local stays local):
  1. SNAPSHOT NEEDED — no snapshot on disk, local hash != manifest
     hash (stale), or the local file is corrupt. The pass carries the
     manifest check + the snapshot download. While the download runs
     in the background, the reply falls back to ping (1 SP).
  2. CURRENT MAINLINE TOKENS — the SP balance check via ping
     (POST /ping is free, never 429s; 1 SP per chat request on the
     ping route). The pass carries the token check and nothing else.

What it carries: manifest (version + SHA-256 + URL), snapshot
download (GGUF bytes, hash-verified before use), token check
(SP balance). What it does NOT do: generate (no generation on the
pass, ever), no CPU at reply time, no background polling, no
always-on stream. Local replies never touch it.

What is NOT decided (do NOT invent it):
  The Connections mechanism itself is still owed (AI chat plan §6,
  decision 2): what a Connection is, whether the snapshot IS one,
  how the starship appears in the AI chat dropdown when detected.
  This module is the pass as Gary described it — the transport the
  snapshot drops into in the AI chat cascade (snapshot first, then
  ping). It does not define Connections.

Open question (not forced): if Gary meant a different connection —
a Drive / Telegram / Stripe segment connection — that is a different
module, not this one. This module is the snapshot/token pass only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CallReason(str, Enum):
    SNAPSHOT_NEEDED = "snapshot_needed"
    TOKENS_CURRENT = "tokens_current"
    NOT_CALLED = "not_called"


@dataclass(frozen=True)
class ConnectionPass:
    """The pass: where the record lives, who transmits, when it is called.

    manifest_url: GitHub IO URL of the snapshot manifest (version +
        SHA-256 + download URL). The record lives here, free.
    worker_url: Cloudflare Worker URL (ping server) — the receiver /
        transmitter. Called only for the two reasons below.
    snapshot_download_url: R2 URL from the manifest — where the GGUF
        bytes come from. None until a manifest has been read.
    """

    manifest_url: str
    worker_url: str
    snapshot_download_url: str | None = None


def should_call(
    *,
    snapshot_present: bool,
    snapshot_hash_matches: bool,
    snapshot_corrupt: bool,
    token_check_needed: bool,
) -> CallReason:
    """Decide whether the pass is called, and why. Pure function.

    Order is deliberate: a snapshot need beats a token check (the
    token check rides along with the ping fallback anyway).
      * No snapshot / stale hash / corrupt -> SNAPSHOT_NEEDED.
      * Otherwise, token check needed -> TOKENS_CURRENT.
      * Otherwise -> NOT_CALLED. Local stays local.
    """
    if (not snapshot_present) or (not snapshot_hash_matches) or snapshot_corrupt:
        return CallReason.SNAPSHOT_NEEDED
    if token_check_needed:
        return CallReason.TOKENS_CURRENT
    return CallReason.NOT_CALLED


def what_it_carries(reason: CallReason) -> list[str]:
    """What the pass carries for a given call reason. Nothing else."""
    if reason is CallReason.SNAPSHOT_NEEDED:
        return ["manifest (version + SHA-256 + download URL)", "snapshot download (GGUF bytes)"]
    if reason is CallReason.TOKENS_CURRENT:
        return ["token check (SP balance via ping)"]
    return []
