/**
 * The daily grab — pure functions, no Cloudflare APIs.
 *
 * Step 2 of the dailies (how temps are verified, Gary 2026-11-15
 * ~09:54 PST): the grab that runs once a day at midnight Gary's
 * time and recognises temps. Ground truth:
 * ~/workspace/temp-verification-how-verified-spec.md and
 * ~/workspace/ARC-Neuron-LLMBuilder/cloudflare/ping-server/tempstore-prototype-RESULTS.md
 * (step 1 — the prototype's verdict: one call cannot work over
 * the store at 1B, so the grab is CHUNKED PASSES over a SHARDED
 * INDEX, not one call).
 *
 * Gary's framing, built this way: the daily pass is a pass of
 * cryptographic hashes — the check per record is a hash
 * verification, and that part is cheap. The chunking/sharding is
 * about the storage round-trips and the invocation CPU budget,
 * not the check itself. Each chunk's pass verifies hashes; each
 * shard holds its own index. (The check cost is measured, not
 * assumed: see grab-scan.mjs — checkChain alone, no I/O — and
 * the results doc.)
 *
 * Design, in one paragraph: the TempIndex is sharded by
 * ACTIVATION-TICK RANGE (not hash prefix — see shardForTick):
 * shard s holds ticks [s*width+1, (s+1)*width], so walking shards
 * in order IS global tick order, and a referrer (always an
 * earlier tick) is always in a same-or-earlier shard — the
 * referrer-dependency propagation matches the single-index scan
 * exactly. The grab runs as paginated passes with a resuming
 * cursor (GrabState DO): one chunk per invocation, each chunk
 * inside one shard, the cursor advanced after every chunk, the
 * next chunk chained by a self-fetch; the cursor is the truth,
 * the chain is an optimisation, the next hourly cron wake-up is
 * the backstop. Chunks are sized from the MEASURED per-record
 * cost with margin under the binding invocation budgets (CPU and
 * subrequests — see GRAB_CHUNK_RECORDS).
 *
 * Labelling (binding, from the plan): every number in reports
 * built on this module is MEASURED (observed, method named),
 * ESTIMATE (computed from measured inputs, labelled), or UNKNOWN
 * (stated as such, with what would measure it).
 */

import { utcDay } from './tempstore.js';

/** The daily acceptance cap (spec §1.2 step 6, plan Q2). */
export const GRAB_DAILY_CAP = 1_000_000_000;

/**
 * Q2, DECIDED here (the spec left it for the grab build): when the
 * grab has accepted GRAB_DAILY_CAP verified temps, the pass STOPS
 * and the rest QUEUE FOR THE NEXT DAY. Tick order is first
 * activated, first served, so the cap is fair; queueing discards
 * nothing (a hard reject would lose temps). The pass ends with
 * done=true, capHit=true; unprocessed ticks and still-pending
 * records wait for the next day's grab, which starts a fresh pass
 * from tick 1. (At 1M records the cap never binds — it is proved
 * by a unit test with a tiny cap, not by the 1M run.)
 */
export const GRAB_CAP_OVERFLOW = 'queue_next_day';

/**
 * Ticks per index shard. Derivation (ESTIMATE from the step-1
 * MEASURED entry sizes — record 355 B, queue entry ~62 B,
 * outcome entry ~75 B; the queue value now also carries the
 * referralId as a compact `id|referralId` string, ~107 B/entry
 * measured — see grab.test.mjs): one full shard holds
 * 31,250,000 queue entries (~3.34 GB) + 31,250,000 outcome
 * entries (~2.34 GB) = ~5.68 GB, 57% of the 10 GB per-DO limit
 * (Paid), 43% headroom. The shard count is UNBOUNDED by design
 * (shard = floor((tick-1)/width)): at 1B records that is 32
 * shards; past 1B, new shards appear instead of any last shard
 * overflowing. Free (1 GB/stub, 5 GB account) cannot hold the
 * store at 1B at all — the design targets Paid, and says so.
 */
export const GRAB_SHARD_WIDTH = 31_250_000;

/** Queue entries returned per /queue-range page (keeps one DO response small). */
export const GRAB_QUEUE_PAGE = 10_000;

/** Outcomes written per /log-batch call. */
export const GRAB_LOG_BATCH = 10_000;

/**
 * Stub calls in flight per batch inside a chunk. The driver
 * processes a chunk in tick-order batches of this size
 * (Promise.all within a batch, batches sequential). A temp's
 * referrer is an earlier tick, so it is in an earlier batch or
 * an earlier chunk — except for the ~batch/chunk fraction inside
 * the same batch, which reads the referrer's pre-apply state and
 * pends one grab. MEASURED (grab-scan.mjs, 1M set): the
 * same-batch effect costs 1,630 first-grab verifications in 1M
 * (−0.45% vs the exact sequential run), all delayed by one grab
 * — pending, never lost. Larger batches would amortise RPC
 * latency further on the edge; 16 is the conservative starting
 * point, and the edge measurement (step 6) may raise it.
 */
export const GRAB_BATCH_CONCURRENCY = 16;

/**
 * Records per chunk. Sized from the MEASURED per-record cost
 * (grab-scan.mjs, 1M set, concurrency 16): the driver costs
 * 76.81 µs/record wall-clock in-process (JS execution only — a
 * lower bound; the edge adds RPC latency, see grab-RESULTS.md).
 * At 200,000 records a chunk costs ~15.4 s CPU (51% of the 30 s
 * Paid HTTP budget) and ~390,000 subrequests (39% of the
 * configured 1,000,000 limit) — both with margin. 400,000
 * records would cost ~30.7 s CPU, OVER the budget, so the chunk
 * stays at 200,000. 1B records = 5,000 chunks; total CPU
 * ~21.3 h at the measured driver cost (ESTIMATE, lower bound),
 * inside the day on CPU alone — the wall-clock fit depends on
 * edge RPC latency and is UNKNOWN until the step-6 edge
 * measurement (break-even ≈ 77 µs per stub call). The chunk
 * never spans shards (see chunkRange).
 */
export const GRAB_CHUNK_RECORDS = 200_000;

/** Subrequests the grab's chunks are allowed per invocation (wrangler [limits]; Paid max 10,000,000). */
export const GRAB_SUBREQUEST_LIMIT = 1_000_000;

/** CPU budget per chunk invocation in ms (Paid HTTP default 30 s; wrangler [limits] cpu_ms). */
export const GRAB_CPU_BUDGET_MS = 30_000;

/** The grab hour in America/Vancouver (spec §1.2 step 2, plan Q11: 12:00 AM Gary's time). */
export const GRAB_TIMEZONE = 'America/Vancouver';
export const GRAB_HOUR = 0;

/** The chain reading (tempstore.js note 1; spec §1.2 step 4): the referrer must be verified. */
export const GRAB_CHAIN_READING = 'referrer_must_be_verified';

/** Which shard holds an activation tick (0-based). Ticks start at 1. */
export function shardForTick(tick, width = GRAB_SHARD_WIDTH) {
  return Math.floor((tick - 1) / width);
}

/** The tick range a shard holds: [startTick, endTick], inclusive. */
export function shardRange(shard, width = GRAB_SHARD_WIDTH) {
  return { startTick: shard * width + 1, endTick: (shard + 1) * width };
}

/** The Durable Object id for an index shard. */
export function shardStubId(shard) {
  return `temp:index:${shard}`;
}

/** The chunk a cursor points at: one shard, at most chunkRecords ticks, never spanning shards. */
export function chunkRange(cursor, chunkRecords = GRAB_CHUNK_RECORDS, width = GRAB_SHARD_WIDTH) {
  const { endTick } = shardRange(cursor.shard, width);
  return {
    shard: cursor.shard,
    startTick: cursor.nextTick,
    endTick: Math.min(cursor.nextTick + chunkRecords - 1, endTick),
  };
}

/** A fresh grab cursor: shard 0, tick 1. */
export function newGrabCursor() {
  return { shard: 0, nextTick: 1 };
}

/** Validate a grab cursor against a shard width (default: the production width). */
export function validateGrabCursor(cursor, width = GRAB_SHARD_WIDTH) {
  if (!cursor || typeof cursor !== 'object' || Array.isArray(cursor)) {
    return { ok: false, error: 'cursor must be an object' };
  }
  if (
    typeof cursor.shard !== 'number' ||
    !Number.isInteger(cursor.shard) ||
    cursor.shard < 0
  ) {
    return { ok: false, error: 'cursor.shard must be a non-negative integer' };
  }
  if (
    typeof cursor.nextTick !== 'number' ||
    !Number.isInteger(cursor.nextTick) ||
    cursor.nextTick < 1
  ) {
    return { ok: false, error: 'cursor.nextTick must be a positive integer' };
  }
  const { startTick, endTick } = shardRange(cursor.shard, width);
  if (cursor.nextTick < startTick || cursor.nextTick > endTick + 1) {
    return { ok: false, error: 'cursor.nextTick is outside its shard range' };
  }
  return { ok: true, cursor: { shard: cursor.shard, nextTick: cursor.nextTick }, error: null };
}

/** Compare two cursors: -1 / 0 / 1 by (shard, nextTick). */
export function compareCursors(a, b) {
  if (a.shard !== b.shard) return a.shard < b.shard ? -1 : 1;
  if (a.nextTick !== b.nextTick) return a.nextTick < b.nextTick ? -1 : 1;
  return 0;
}

/** Empty tallies for a grab pass. */
export function newGrabTallies() {
  return { checked: 0, verified: 0, pending: 0, not_verified: 0, expired: 0, skipped: 0 };
}

/** A fresh grab state for a grab day. The shard width is part of
 * the grab's configuration and is stored on the state, so the
 * cursor validation in /advance uses the same width the driver
 * used — a state validated against the production width while
 * the driver ran a narrower one would reject every cursor past
 * shard 0. The width is fixed per grab; changing it mid-grab
 * is unsupported. */
export function newGrabState(grabDay, nowMs = Date.now(), shardWidth = GRAB_SHARD_WIDTH) {
  return {
    grabDay,
    shard: 0,
    nextTick: 1,
    shardWidth,
    tallies: newGrabTallies(),
    startedAtMs: nowMs,
    updatedAtMs: nowMs,
    done: false,
    capHit: false,
    doneReason: null,
  };
}

/** Validate a grab state (as stored by the GrabState DO). */
export function validateGrabState(state) {
  if (!state || typeof state !== 'object' || Array.isArray(state)) {
    return { ok: false, error: 'grab state must be an object' };
  }
  if (typeof state.grabDay !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(state.grabDay)) {
    return { ok: false, error: 'grabDay must be a UTC date string' };
  }
  const cursor = validateGrabCursor(
    { shard: state.shard, nextTick: state.nextTick },
    typeof state.shardWidth === 'number' ? state.shardWidth : GRAB_SHARD_WIDTH,
  );
  if (!cursor.ok) return { ok: false, error: cursor.error };
  if (
    state.shardWidth !== undefined &&
    (typeof state.shardWidth !== 'number' ||
      !Number.isInteger(state.shardWidth) ||
      state.shardWidth < 1)
  ) {
    return { ok: false, error: 'shardWidth must be a positive integer' };
  }
  if (!state.tallies || typeof state.tallies !== 'object') {
    return { ok: false, error: 'tallies must be an object' };
  }
  for (const k of ['checked', 'verified', 'pending', 'not_verified', 'expired', 'skipped']) {
    if (typeof state.tallies[k] !== 'number' || !Number.isInteger(state.tallies[k]) || state.tallies[k] < 0) {
      return { ok: false, error: `tallies.${k} must be a non-negative integer` };
    }
  }
  if (typeof state.startedAtMs !== 'number' || typeof state.updatedAtMs !== 'number') {
    return { ok: false, error: 'startedAtMs/updatedAtMs must be numbers' };
  }
  if (typeof state.done !== 'boolean' || typeof state.capHit !== 'boolean') {
    return { ok: false, error: 'done/capHit must be booleans' };
  }
  if (state.doneReason !== null && state.doneReason !== 'exhausted' && state.doneReason !== 'cap') {
    return { ok: false, error: "doneReason must be null, 'exhausted' or 'cap'" };
  }
  return {
    ok: true,
    state: {
      grabDay: state.grabDay,
      shard: state.shard,
      nextTick: state.nextTick,
      shardWidth:
        typeof state.shardWidth === 'number' ? state.shardWidth : GRAB_SHARD_WIDTH,
      tallies: { ...state.tallies },
      startedAtMs: state.startedAtMs,
      updatedAtMs: state.updatedAtMs,
      done: state.done,
      capHit: state.capHit,
      doneReason: state.doneReason ?? null,
    },
    error: null,
  };
}

/**
 * Is it the grab hour in America/Vancouver? The hourly cron
 * wake-up calls this; only the 00:00 hour starts/resumes a grab.
 * Intl with timeZone is available in Workers and Node — no
 * hand-rolled DST table, so the PST/PDT shift is correct by
 * construction (12am Gary's time is 08:00 UTC in PST, 07:00 UTC
 * in PDT; a fixed UTC cron would be wrong half the year).
 *
 * NOTE (2026-11-15): that parenthetical is now STALE. British
 * Columbia adopted permanent daylight saving time in 2026 — from
 * 1 Nov 2026 most of BC (including Williams Lake) is on Pacific
 * time (PCT), fixed at UTC-7 year-round, no fall-back (tzdata
 * 2026b+; verified on this VM: tzdata 2026e, `zdump` shows
 * America/Vancouver going to MST -0700 on 2026-11-01 and staying
 * there). So 12am Gary's time is 07:00 UTC year-round from Nov
 * 2026. The code stays correct because it follows the runtime's
 * tz database rather than a hardcoded offset — but a deployment
 * runtime with STALE tzdata would fire the grab at 08:00 UTC
 * (1am local) instead; benign (same UTC day, one hour late),
 * and worth a step-6 edge check on the deployed Worker.
 */
export function isGrabHour(nowMs = Date.now()) {
  const hour = Number(
    new Intl.DateTimeFormat('en-US', {
      timeZone: GRAB_TIMEZONE,
      hour: 'numeric',
      hourCycle: 'h23',
    }).format(new Date(nowMs)),
  );
  return hour === GRAB_HOUR;
}

/** The grab day for a moment: the UTC date (== the America/Vancouver date at the grab hour). */
export function grabDayFor(nowMs = Date.now()) {
  return utcDay(nowMs);
}

/**
 * Chunk sizing from a measured per-record CPU cost.
 * Returns the largest record count whose CPU fits the budget
 * after the margin, and the subrequest count it implies.
 * perRecordCalls is stub calls per record (~2 for the grab
 * driver: one referrer /get for records with a referral, one
 * /apply per record, plus amortised queue/log pages).
 */
export function chunkRecordsForBudgets({ perRecordCpuUs, cpuBudgetMs, cpuMargin = 0.5, perRecordCalls = 2, subrequestLimit, subrequestMargin = 0.2 }) {
  const byCpu = Math.floor(((cpuBudgetMs * 1000) / perRecordCpuUs) * (1 - cpuMargin));
  const bySubrequests = Math.floor((subrequestLimit / perRecordCalls) * (1 - subrequestMargin));
  return {
    byCpu,
    bySubrequests,
    chunkRecords: Math.min(byCpu, bySubrequests),
    binding: byCpu <= bySubrequests ? 'cpu' : 'subrequests',
  };
}
