# instant_reply — pre-generated replies, branch-passed, zero CPU at reply time

**Status:** design + thin module, local only, NOT pushed. No trained model
exists yet, no snapshot exists yet — see "Honest limits" below.

**Gary's goal (2026-11-08):** generate a reply ONCE, up front, pack it,
store it — then at reply time there is nothing to generate. The SPSC ring
passes the causal tick, the branch passes the already-made reply through,
the hash is verified, the reply is delivered. CPU only once, at pack time,
offline. At the moment you need the reply: zero CPU.

## Correction: these are ARC ecosystem modules / links, NOT Lucid segments

Lucid segments are a closed list (`src/lib/segmentCategories.ts`): about,
computer-control, ai-chat, google-drive, telegram, stripe, starship,
forge-persona-plex. The items in this package — SeedCatalog ring (Module 1),
ARC Apache, StreamMemory, OmniBinary, Arc-RAR — are ARC ecosystem modules /
links (ARC-Emulator README "ARC ecosystem fit", ARC-Core ECOSYSTEM.md).
Starship modules would only show up AS segments when a starship is
detected, which hasn't happened. The one exception is the **Connection**,
which is the bridge TO the AI Chat segment — a place other things can
connect to — not a segment itself.

## Placement

- **Pack / store side — this package, in ARC-Neuron-LLMBuilder.**
  Python, stdlib-only. It owns packing, storing, streaming, branch-pass,
  intake records, and replay bundles.
- **Delivery-decision side — Lucid, thin only.**
  `src/lib/instantReplyPackets.ts` (branch-pass decision table) and
  `src/lib/instantReplyConnection.ts` (the pass: when it is called).
  Pure functions, no pack logic, no new IPC, no UI, no prompt changes.
  The b82010d prompt (blood drop + gold arrow + `~` + bubble) is untouched.
- **Each sibling repo stays independent, not overtaken.** This package
  USES their contracts; it never modifies their code, never imports
  ARC Apache, never folds them into another repo.

## The flow, in order

```
1. PACK (CPU once, offline, at pack time)
   A reply already exists (stock model, or operator-supplied).
   build_packet(prompt, reply_text, model_id, chat_id, tick, branch)
   -> canonical JSON bytes; packet_id = SHA-256 of those bytes.

2. STORE — ARC Apache (packet store)
   ApacheStore.pack_packet() calls ARC-Apache's CLI (subprocess):
   pack -> v5 manifest (manifest_sha256, envelope_sha256, merkle_root,
   per-chunk SHA-256) + receipt. Verify + restore are the same CLI.
   The CLI contract was verified live (pack -> verify ok -> restore
   byte-identical -> receipt). Nothing here reimplements pack/verify.

3. STREAM — StreamMemory (session stream)
   SessionStream.offer(ref) — bounded SPSC ring, cap 256, FIFO, full =
   backpressure counted (refused), never silent. The packet itself is
   the durable home; the ring carries refs only. Recent window: last 50.
   stream_manifest() emits the ARC-Apache stream-manifest shape.
   NOTE: no StreamMemory repo exists — this is the stream discipline,
   not a repo. When a real StreamMemory repo exists it adopts this
   contract.

4. TICK — SPSC causal tick
   The chat tick arrives (Lucid aiChatTickRing, cap 256, separate from
   the event log). The tick + packet ref travel together; the tick is
   stamped on the message, so a ring refusal never loses it.

5. BRANCH-PASS — deliver, or fall back
   decide_delivery(packet_present, hash_verified, branch_matches, ...):
     DELIVER        packet + hash ok + branch ok -> reply verbatim.
     FALLBACK_PING  no packet / wrong branch -> ping (1 SP, ~0.5 neurons).
     DISCARD        hash failed -> discard packet, fall back to ping.
   Never invent a reply. Never serve a bad packet.
   PACKET-FIRST ORDER (Gary, 2026-11-08 — the CPU-none rule): the
   full flow is packet -> ping -> OpenAI (key only, server-side) ->
   honest error. If the ping route itself errors, the second fallback
   is fallback_after_ping_error() / resolveInstantReplyFallbackAfter-
   PingError(): OpenAI iff a key is configured AND the error was not
   a 429 (SP spent — the gate is terminal) AND no partial ping reply
   was already streamed (no Franken-reply). The local route is NEVER
   a fallback in this flow (user-side CPU = NONE); it stays a leg of
   the general cascade outside this flow, gated out here.

6. DELIVER — zero CPU at reply time
   Reply text is handed to the chat bubble in tick order. No generation,
   no re-encode. The only CPU at this point is the hash check that
   already happened at verify time.

7. RECORD + BUNDLE (after delivery)
   OmniBinary intake_record(): classify the binary (GGUF / packet
   envelope / bundle), record its SHA-256 in the OBIN v2 ledger
   (runtime/learning_spine.py). Real Rust tooling federation is the
   v1.3.0 roadmap, NOT built here.
   Arc-RAR bundle_delivery(): reply bytes + tick log + ARC Apache
   manifest + receipts -> .arcrar.zip with embedded manifest.json
   (reuses build_arc_rar_bundle). Wiring the real Rust Arc-RAR CLI
   is the v1.3.0 milestone, NOT built here. The bundle is the
   replay/save proof: the delivered reply can be replayed later.

8. THE PASS — Connection (when the snapshot / tokens are needed)
   connection.should_call(...): called ONLY when the snapshot is needed
   (missing / stale hash / corrupt) or a current-token check is needed.
   GitHub IO holds the manifest/record; Cloudflare (ping Worker) is the
   receiver/transmitter; R2 holds the GGUF bytes. Otherwise NOT_CALLED
   — local stays local. No generation on the pass, no background polling.
   The Connections mechanism itself (what a Connection is, whether the
   snapshot IS one, how the starship appears in the dropdown) is still
   owed — this module does not invent it.

## Module map (each independent)

| Module | What it is | Where it lives | Status |
|---|---|---|---|
| ARC Apache | Packet store: v5 pack/verify/restore/receipt/bundle-plan | GareBear99/ARC-Apache, 0.5.1, HEAD f9dedda (1 ahead, unpushed) | Real, used via CLI contract |
| StreamMemory | Session stream: bounded SPSC ring + stream manifest | Design-only, no repo — discipline in `stream.py` | Discipline built, repo does not exist |
| OmniBinary | Binary intake + runtime ledger (receipts-first) | GareBear99/omnibinary-runtime, HEAD 61d0ee3 (scaffold: intake/reporting strong, true runtime core missing) | Intake record via OBIN v2 in-repo; Rust federation v1.3.0, not built |
| Arc-RAR | Replay/save bundles, manifest-indexed, rollback | GareBear99/Arc-RAR, HEAD 6b88def (CLI/core strongest, native apps incomplete) | Bundle via in-repo builder (structurally compatible); Rust CLI wiring v1.3.0, not built |
| Connection | The pass: GitHub IO record + Cloudflare receiver/transmitter | This package (`connection.py`) + Lucid `instantReplyConnection.ts` | Pass decision built; Connections mechanism still owed |

## Interfaces

Python (`instant_reply/`):
- `build_packet(prompt, reply_text, *, model_id, chat_id, tick, branch) -> Packet`
- `packet_bytes(packet) -> bytes`, `packet_id(packet) -> str`, `verify_packet(packet, expected_id) -> bool`
- `ApacheStore(apache_root=None)` — `.pack_packet(packet, store) -> manifest`,
  `.verify_manifest(manifest, store) -> (ok, errors)`,
  `.restore_packet(manifest, store, output) -> Path`,
  `.receipt_for(manifest, store) -> receipt`, `.bundle_plan(...) -> plan`
- `SessionStream(capacity=256, recent_window=50)` — `.offer(ref) -> bool`,
  `.drain() -> list`, `.recent`, `.stream_manifest(stream_id) -> dict`
- `decide_delivery(*, packet_present, hash_verified, branch_matches, reply_text, packet_id=None) -> BranchPass`
- `classify_binary(path) -> BinaryKind`, `intake_record(path, ledger_path, *, kind=None, parents=None) -> dict`
- `bundle_delivery(*, bundle_path, packet_bytes, packet_id, chat_id, tick, branch, manifest, receipts, tick_log=None) -> dict`,
  `verify_bundle(bundle_path) -> manifest`
- `should_call(*, snapshot_present, snapshot_hash_matches, snapshot_corrupt, token_check_needed) -> CallReason`,
  `what_it_carries(reason) -> list[str]`

TypeScript (Lucid, pure, no I/O):
- `src/lib/instantReplyPackets.ts` — `decideInstantReplyDelivery(...)`, `DeliveryDecision`
- `src/lib/instantReplyConnection.ts` — `shouldCallConnection(...)`, `ConnectionCallReason`

## Honest limits: proven now vs waiting on training / snapshot

Proven NOW (tests in this run, with stock / canned replies):
- Packet canonical bytes + id are deterministic; any byte change fails verification.
- ARC Apache pack -> verify -> restore is byte-identical (verified live against the real CLI).
- Stream ring is bounded + FIFO; full offers are refused and counted, never silently dropped.
- Branch-pass: deliver / fallback / discard table, including wrong-branch and corrupt cases.
- Arc-RAR bundle builds and its manifest reads back without extracting.
- OBIN v2 intake record appends and verifies.
- Connection pass is called only for snapshot-needed / token-check, otherwise not called.

Waiting on training + snapshot (NOT claimed):
- No trained model, no snapshot, no GGUF. A packet's reply today can only be
  stock (ping) or canned/operator-supplied — pre-generation of an existing
  reply, not a trained reply.
- Built-in inference engine is design-only; today local is llamafile
  cold-load, ping is stock Llama 3.2 1B.
- The snapshot (GGUF + SHA-256, on top of the cascade before ping, SPSC
  triple-buffer swap both sides) is Phase 6 of the AI chat plan.
- Connections mechanism decision owed; starship detection is Gary's call.

## What would push

This package's commit in ARC-Neuron-LLMBuilder (local only in this run),
plus the two Lucid TS files + tests in lucid-terminal (local only in this
run). Nothing here pushes ARC-Apache, omnibinary-runtime, or Arc-RAR —
those repos are untouched. If ARC-Apache needs a fix as its own separate
job, it is listed separately, not bundled in: none needed for this module
(the CLI contract worked as-is).
```

## Tests

Python: `python3 -m unittest discover -s tests -p "test_instant_reply.py" -v`
(Uses stdlib unittest — no pytest on this VM.)
TypeScript: `npm test -- tests/instantReplyPackets.test.ts tests/aiChatRoute.test.ts`
(The Connection tests live in tests/instantReplyPackets.test.ts — there
is no separate tests/instantReplyConnection.test.ts file.)
