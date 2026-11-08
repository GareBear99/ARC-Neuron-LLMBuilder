"""omnibinary.py — OmniBinary intake record (ledger only, no Rust here).

What OmniBinary IS (read, not guessed — GareBear99/omnibinary-runtime,
HEAD 61d0ee30908fc56e0b931d0985ca84cef292761c):
  Native-first binary intake, classification, and execution fabric.
  Intake native binaries (executables, libraries, GGUF model weights)
  into a classified, signed, deterministic store; runtime ledger —
  an indexed, SHA-256-verifiable mirror of every binary state change;
  federated execution lanes (managed / native / DBT); receipts-first
  (every binary operation produces a receipt before a result).
  Status, its own README: strong on intake, reporting, planning,
  cache/receipt discipline; NOT yet complete as a universal translated
  execution runtime — the true runtime core (guest ISA decoder,
  Cranelift/LLVM translated blocks, syscall mediation, sandbox plane)
  is still missing. It does NOT generate replies and is NOT a model.

What it does in THIS system (narrow, honest):
  When a binary enters the pre-generation flow — a GGUF snapshot file,
  a packed reply envelope, an Arc-RAR bundle — its identity must not
  drop out of the governed system the moment it is converted,
  quantized, or repackaged. This module classifies the binary and
  records its SHA-256 + kind + parents in the OBIN v2 ledger that
  ALREADY lives in this repo (runtime/learning_spine.py,
  OmnibinaryStore) — the simplified event-log substrate that maps
  onto OmniBinary's runtime-ledger direction. The v1.3.0 federation
  roadmap (LLMBuilder .obin files subscribable by OmniBinary so GGUF
  exports and Arc-RAR bundles appear in the binary-side event graph)
  is NOT built here, and this module never invokes the Rust binary.
"""

from __future__ import annotations

import sys
import time
from enum import Enum
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.learning_spine import LearningEvent, OmnibinaryStore, sha256_file  # noqa: E402


class BinaryKind(str, Enum):
    GGUF = "gguf"  # a model snapshot file (GGUF weights)
    PACKET_ENVELOPE = "packet_envelope"  # an ARC Apache envelope of a packet
    BUNDLE = "bundle"  # an Arc-RAR replay/save bundle
    OTHER = "other"


def classify_binary(path: Path) -> BinaryKind:
    """Classify a binary by name/shape only — intake, not execution.

    .gguf -> GGUF; .arcrar.zip / .zip with an Arc-RAR manifest ->
    BUNDLE (checked by suffix here; the bundle reader verifies the
    manifest, this function does not); anything else -> OTHER.
    Classification never executes the file.
    """
    name = path.name.lower()
    if name.endswith(".gguf"):
        return BinaryKind.GGUF
    if name.endswith(".arcrar.zip") or name.endswith(".arcrar"):
        return BinaryKind.BUNDLE
    return BinaryKind.OTHER


def intake_record(
    path: Path,
    ledger_path: Path,
    *,
    kind: BinaryKind | None = None,
    parents: list[str] | None = None,
) -> dict:
    """Record a binary's intake in the OBIN v2 ledger. Returns the record.

    The record is: kind, SHA-256 of the file bytes, path, parents.
    The ledger is append-only; the event id is the record's address.
    A missing file raises FileNotFoundError — intake never records
    a binary it has not seen.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"intake_record: no such binary: {path}")
    kind = kind or classify_binary(path)
    digest = sha256_file(path)
    store = OmnibinaryStore(Path(ledger_path))
    event = LearningEvent(
        ts_utc=int(time.time()),
        source="instant-reply-omnibinary",
        event_type="binary.intake",
        payload={
            "kind": kind.value,
            "sha256": digest,
            "path": str(path),
            "parents": list(parents or []),
        },
    )
    event_id = store.append(event)
    store.flush()
    return {"event_id": event_id, "kind": kind.value, "sha256": digest, "path": str(path)}
