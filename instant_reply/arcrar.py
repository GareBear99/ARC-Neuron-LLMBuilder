"""arcrar.py — Arc-RAR replay/save bundle (format reuse, no Rust here).

What Arc-RAR IS (read, not guessed — GareBear99/Arc-RAR, HEAD
6b88defa05dc686fdec156236c63c1ca68238594):
  CLI-first archive manager with a native-app control surface.
  Portable, self-describing, manifest-indexed archives: a structured
  manifest readable in isolation + a SHA-256 index covering every file
  it contains. Governed extraction (extraction leaves a receipt),
  rollback as a first-class operation (restore a prior version by
  SHA-256), CLI + FFI + IPC crates, desktop apps (GTK / macOS / WinUI).
  Status, its own README: strongest as a Rust workspace starter /
  host-tool-backed archive CLI / receipts / GUI bridge; NOT yet an
  honestly complete production app suite — native frontends still
  need end-to-end implementation and validation on target systems.

What it does in THIS system:
  A delivered reply must be replayable and provable LATER. The bundle
  for one delivery is: the reply payload bytes + the tick log for its
  chat + the ARC Apache manifest + the receipts — zipped with an
  embedded manifest.json (SHA-256-indexed), restorable by hash,
  readable without extracting. That is the replay/save bundle for a
  generated reply + its ticks + receipts.

Implementation: REUSE the builder already in this repo —
``build_arc_rar_bundle`` / ``read_arc_rar_manifest`` in
runtime/learning_spine.py — which produces bundles structurally
compatible with Arc-RAR (same manifest format, same SHA-256 index,
same restore semantics; see ECOSYSTEM.md §6). Wiring the real Rust
Arc-RAR CLI to index/list/restore these bundles directly is the
v1.3.0 milestone, NOT built here, and this module never invokes it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.learning_spine import build_arc_rar_bundle, read_arc_rar_manifest  # noqa: E402


def bundle_delivery(
    *,
    bundle_path: Path,
    packet_bytes: bytes,
    packet_id: str,
    chat_id: str,
    tick: int,
    branch: str,
    manifest: dict,
    receipts: list[dict],
    tick_log: list[dict] | None = None,
) -> dict:
    """Bundle one delivery for replay. Returns the bundle record.

    Contents (all inside the zip, plus embedded manifest.json):
      reply.json        — the packet bytes (canonical packet JSON).
      tick_log.json     — the tick log for this chat (may be empty).
      apache_manifest.json — the ARC Apache v5 manifest for the packet.
      receipts.json     — the receipts for this delivery.
    The bundle manifest carries: packet_id, chat_id, tick, branch,
    the ARC Apache manifest_sha256, and the bundle's own SHA-256
    (computed by the builder over the finished zip).
    """
    bundle_path = Path(bundle_path)
    work = bundle_path.parent / f".bundle-work-{packet_id[:12]}"
    work.mkdir(parents=True, exist_ok=True)
    try:
        reply_file = work / "reply.json"
        reply_file.write_bytes(packet_bytes)
        tick_file = work / "tick_log.json"
        tick_file.write_text(
            json.dumps(tick_log or [], indent=2, sort_keys=True), encoding="utf-8"
        )
        apache_file = work / "apache_manifest.json"
        apache_file.write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        receipts_file = work / "receipts.json"
        receipts_file.write_text(
            json.dumps(receipts, indent=2, sort_keys=True), encoding="utf-8"
        )
        bundle_manifest = {
            "kind": "instant-reply-delivery",
            "packet_id": packet_id,
            "chat_id": chat_id,
            "tick": tick,
            "branch": branch,
            "apache_manifest_sha256": manifest.get("manifest_sha256"),
            "receipt_count": len(receipts),
        }
        return build_arc_rar_bundle(
            bundle_path,
            [reply_file, tick_file, apache_file, receipts_file],
            bundle_manifest,
        )
    finally:
        for p in work.iterdir():
            p.unlink(missing_ok=True)
        work.rmdir()


def verify_bundle(bundle_path: Path) -> dict:
    """Read a bundle's manifest without extracting. Returns the manifest.

    Verifying the bundle's bytes against its recorded SHA-256 is the
    caller's step (sha256_file in runtime/learning_spine.py) — this
    function only reads the manifest so the caller can ask the bundle
    what it is before deciding to restore it.
    """
    return read_arc_rar_manifest(Path(bundle_path))
