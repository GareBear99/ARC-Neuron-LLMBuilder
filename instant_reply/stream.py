"""stream.py — StreamMemory session stream (design-only as a repo).

There is NO StreamMemory repo and NO StreamMemory codebase. What exists:
  * ARC-Emulator README ecosystem fit: "StreamMemory -> visual/audio
    gameplay session memory" / "AV capture -> StreamMemory timeline ->
    ARC-native session memory".
  * ARC-Apache README: "ARC-StreamMemory — screen, sensor, frame,
    terminal, and visual memory streams".
  * ARC-Apache integration/STREAMMEMORY_BINARY_HOOK.md: StreamMemory
    should emit a stream sequence manifest instead of loose frame
    folders; each frame independently hash-addressed and restorable;
    the sequence manifest links frames into time order.

So this module is the STREAM DISCIPLINE, not a repo: a bounded SPSC
ring carrying packet refs in causal tick order, plus a stream-manifest
emitter matching ARC-Apache's stream-manifest contract. When a real
StreamMemory repo exists, it adopts this contract; it does not replace
this module, and this module never claims to BE that repo.

Discipline (same as Module 1, the ARC-SeedCatalog SPSC ring):
  * Preallocated, bounded capacity (default 256 — mirrors Lucid's
    aiChatTickRing cap 256). No allocation per tick in the hot path.
  * Single producer (pack time issues packet refs), single consumer
    (delivery drains them). FIFO — drain order IS causal tick order.
  * Full policy: BACKPRESSURE, counted, never silent. When full,
    ``offer`` returns False and ``refused`` counts it. The packet ref
    is NOT lost: the packet itself (in the ARC Apache store) is the
    durable home; the ring is the bounded transport it passed through.
    This mirrors Lucid's tick channel, where the tick is stamped on
    the message and a ring refusal never loses it.
  * Keep vs drop: the ring keeps packet refs in tick order; the
    recent window keeps the last 50 (mirrors Lucid's recentTicks
    window of 50). When the window is full the OLDEST ref falls off
    the window only — the packet stays in the store, addressable by
    its id, and can be re-fetched. Nothing is deleted from the store
    by the stream.

Honesty note: pure Python on CPython. Like SeedCatalog's ring, this
gives SPSC *structure and discipline* (fixed bound, FIFO,
backpressure), not cross-thread lock-freedom — the GIL is a lock.
The bound (len <= capacity at every instant) holds regardless.
"""

from __future__ import annotations

from collections import deque

DEFAULT_STREAM_CAPACITY = 256
DEFAULT_RECENT_WINDOW = 50


class SessionStream:
    """Bounded SPSC session stream of packet refs, in causal tick order.

    A packet ref is a small dict: {"packet_id": str, "chat_id": str,
    "tick": int, "branch": str, "manifest_sha256": str | None}.
    The stream carries refs, never packet bytes — bytes live in the
    ARC Apache store and are fetched by id only when delivered.
    """

    def __init__(
        self,
        capacity: int = DEFAULT_STREAM_CAPACITY,
        recent_window: int = DEFAULT_RECENT_WINDOW,
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        # Preallocated slots, reused in place (head/tail are monotonic).
        self._slots: list[dict | None] = [None] * capacity
        self._capacity = capacity
        self._head = 0  # consumer index (monotonic)
        self._tail = 0  # producer index (monotonic)
        self.refused = 0  # offers refused while full (backpressure, counted)
        self._recent: deque[dict] = deque(maxlen=recent_window)

    def __len__(self) -> int:
        return self._tail - self._head

    @property
    def capacity(self) -> int:
        return self._capacity

    def offer(self, ref: dict) -> bool:
        """Producer: offer a packet ref. False when full (backpressure).

        Never blocks, never grows, never silently drops: False means
        the caller must retry later or fall back — the packet itself
        is still in the store.
        """
        if self._tail - self._head >= self._capacity:
            self.refused += 1
            return False
        self._slots[self._tail % self._capacity] = ref
        self._tail += 1
        return True

    def drain(self) -> list[dict]:
        """Consumer: take all queued refs, in FIFO (causal tick) order."""
        out: list[dict] = []
        while self._head < self._tail:
            ref = self._slots[self._head % self._capacity]
            self._slots[self._head % self._capacity] = None
            self._head += 1
            if ref is not None:
                out.append(ref)
                self._recent.append(ref)
        return out

    @property
    def recent(self) -> list[dict]:
        """Last N drained refs, oldest first — a viewing window, not storage."""
        return list(self._recent)

    def stream_manifest(self, stream_id: str) -> dict:
        """Stream sequence manifest, ARC-Apache stream-manifest shape.

        Links the recent window into time (tick) order. Each ref is
        independently hash-addressed (packet_id) and restorable from
        the store. This is the manifest ARC-Apache's
        ``stream-manifest`` command produces for frames — same shape,
        packet refs instead of frames.
        """
        refs = self.recent
        return {
            "stream_id": stream_id,
            "version": 5,
            "entries": [
                {
                    "index": i,
                    "tick": r["tick"],
                    "chat_id": r["chat_id"],
                    "packet_id": r["packet_id"],
                    "branch": r["branch"],
                    "manifest_sha256": r.get("manifest_sha256"),
                }
                for i, r in enumerate(refs)
            ],
        }
