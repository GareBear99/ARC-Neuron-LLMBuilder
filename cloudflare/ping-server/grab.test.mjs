// Unit + driver tests for the daily grab (step 2 of the dailies).
// Pure logic in grab.js, the GrabState DO, the TempIndex sharded
// routes, and the grab driver end to end through the real Worker
// fetch handler (POST /admin/grab) with fake env bindings.
// No network, no wrangler. Run: node grab.test.mjs (Node >= 18.)
//
// What this proves: shard math (tick-range boundaries, coverage,
// per-shard bytes at 1B from measured entry sizes), the cursor
// (monotonic, never backward), the cap (Q2: queue for the next
// day), the grab-hour gate (12am America/Vancouver, DST-correct),
// the GrabState DO (start idempotent, advance monotonic, finish),
// and the driver — chunked passes over a sharded store produce
// the SAME outcomes as the sequential reference, resume from a
// mid-grab cursor, and re-running a finished grab is a no-op.

import assert from 'node:assert/strict';
import worker, { GrabState, PingRateLimiter, TempIndex, TempRecord } from './worker.js';
import {
  GRAB_BATCH_CONCURRENCY,
  GRAB_CHUNK_RECORDS,
  GRAB_DAILY_CAP,
  GRAB_QUEUE_PAGE,
  GRAB_SHARD_WIDTH,
  chunkRange,
  chunkRecordsForBudgets,
  compareCursors,
  grabDayFor,
  isGrabHour,
  newGrabCursor,
  newGrabState,
  newGrabTallies,
  shardForTick,
  shardRange,
  shardStubId,
  validateGrabCursor,
  validateGrabState,
} from './grab.js';
import {
  applyOutcome,
  checkChain,
  genesisReferrerState,
  newTempRecord,
  parseQueueValue,
  queueKey,
  queueValue,
  utcDay,
} from './tempstore.js';

const H = 3600 * 1000;
const DAY = 24 * H;
const YEAR = 365 * DAY;
// The grab moment: 12:00 AM America/Vancouver. BC is on
// permanent Pacific time (PCT, UTC-7) from 1 Nov 2026 — no
// fall-back — so 12am Gary's time is 07:00 UTC year-round
// (tzdata 2026b+; verified on this VM: tzdata 2026e).
const T0 = Date.UTC(2026, 11, 15, 7, 0, 0);

let passed = 0;
async function check(name, fn) {
  await fn();
  passed += 1;
  console.log(`ok - ${name}`);
}

// --- fake DO storage (Map-backed, same get/put/list shape as the
// real API, INCLUDING the bounded list() the grab path uses:
// list({ prefix, start, end, limit }) — start inclusive, end
// exclusive, limit caps the page; the returned Map is in
// lexicographic key order. ---
function fakeState() {
  const store = new Map();
  return {
    storage: {
      async get(key) {
        return store.has(key) ? store.get(key) : null;
      },
      async put(key, value) {
        store.set(key, value);
      },
      async list({ prefix, start, end, limit } = {}) {
        const out = new Map();
        const keys = [...store.keys()]
          .filter((k) => !prefix || k.startsWith(prefix))
          .filter((k) => start === undefined || k >= start)
          .filter((k) => end === undefined || k < end)
          .sort();
        const capped = limit === undefined ? keys : keys.slice(0, limit);
        for (const k of capped) out.set(k, store.get(k));
        return out;
      },
    },
  };
}

// Per-stub namespaced storage over one shared Map.
function namespacedState(sharedMap, namespace) {
  const prefix = `${namespace}:`;
  return {
    storage: {
      async get(key) {
        const full = prefix + key;
        return sharedMap.has(full) ? sharedMap.get(full) : null;
      },
      async put(key, value) {
        sharedMap.set(prefix + key, value);
      },
      async list({ prefix: sub, start, end, limit } = {}) {
        const out = new Map();
        const want = prefix + (sub || '');
        const keys = [...sharedMap.keys()]
          .filter((k) => k.startsWith(want))
          .filter((k) => start === undefined || k.slice(prefix.length) >= start)
          .filter((k) => end === undefined || k.slice(prefix.length) < end)
          .sort();
        const capped = limit === undefined ? keys : keys.slice(0, limit);
        for (const k of capped) out.set(k.slice(prefix.length), sharedMap.get(k));
        return out;
      },
    },
  };
}

// Fake env bindings over one shared Map: TEMP_STORE (one stub per
// temp), TEMP_INDEX (one stub per shard), GRAB_STATE (one global
// stub). The idFromName shape is the real one (a string id); the
// stub's fetch drives the real DO class.
function fakeEnv(sharedMap) {
  const binding = (Class, namespaceFor) => ({
    idFromName: (id) => id,
    get: (id) => new Class(namespacedState(sharedMap, namespaceFor(id))),
  });
  return {
    TEMP_STORE: binding(TempRecord, (id) => id),
    TEMP_INDEX: binding(TempIndex, (id) => id),
    GRAB_STATE: binding(GrabState, (id) => id),
    RATE_LIMITER: binding(PingRateLimiter, (id) => id),
    GRAB_PUBLIC_URL: 'https://lucid-ping-server.admension.workers.dev',
  };
}

async function callDo(doInstance, path, body) {
  const req = new Request(`http://do${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  const res = await doInstance.fetch(req);
  return { status: res.status, body: await res.json() };
}

async function callWorker(env, method, path, body) {
  const req = new Request(`http://grab${path}`, {
    method,
    headers: { 'content-type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  const res = await worker.fetch(req, env, {});
  return { status: res.status, body: await res.json() };
}

// --- fake clock ---
let nowMs = T0;
const realNow = Date.now;
Date.now = () => nowMs;
const setNow = (ms) => {
  nowMs = ms;
};

function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// --- pure logic: shard math ---

await check('shardForTick/shardRange: tick-range boundaries, coverage, no gaps or overlaps', async () => {
  const W = GRAB_SHARD_WIDTH;
  assert.equal(shardForTick(1), 0);
  assert.equal(shardForTick(W), 0);
  assert.equal(shardForTick(W + 1), 1);
  assert.equal(shardForTick(2 * W), 1);
  assert.equal(shardForTick(2 * W + 1), 2);
  assert.deepEqual(shardRange(0), { startTick: 1, endTick: W });
  assert.deepEqual(shardRange(1), { startTick: W + 1, endTick: 2 * W });
  // Every tick 1..1B maps to exactly one shard, and the ranges
  // tile without gaps: shard k ends where k+1 starts.
  assert.equal(shardForTick(1_000_000_000), 31);
  assert.equal(shardRange(31).endTick, 1_000_000_000);
  for (let s = 0; s < 32; s++) {
    const r = shardRange(s);
    assert.equal(r.endTick - r.startTick + 1, W);
    if (s > 0) assert.equal(r.startTick, shardRange(s - 1).endTick + 1);
  }
  assert.equal(shardStubId(0), 'temp:index:0');
  assert.equal(shardStubId(31), 'temp:index:31');
});

await check('per-shard index bytes at 1B (from measured entry sizes) stay comfortably under 10 GB', async () => {
  // Measure the real entry sizes (profile-<uuid> ids, as seeded).
  const id = 'profile-00000000-0000-4000-8000-000000000001';
  const ref = 'profile-00000000-0000-4000-8000-000000000000';
  const queueEntryBytes = queueKey(1).length + queueValue(id, ref).length;
  const outcomeEntryBytes = `o:0000000000000001:${id}`.length + 'not_verified'.length;
  const W = GRAB_SHARD_WIDTH;
  const perShard = W * (queueEntryBytes + outcomeEntryBytes);
  const at1B = 32 * perShard;
  console.log(`    measured: queue entry ${queueEntryBytes} B, outcome entry ${outcomeEntryBytes} B; one full shard ${Math.round(perShard / 1e9 * 100) / 100} GB; 1B total ${Math.round(at1B / 1e9 * 100) / 100} GB`);
  assert.ok(perShard < 6_000_000_000, `one full shard is ${perShard} B, over the 6 GB comfort bound`);
  assert.ok(perShard < 10_000_000_000, 'one full shard must fit the 10 GB per-DO limit (Paid)');
  assert.ok(at1B < 200_000_000_000, '1B total index must stay under 200 GB');
});

await check('queueValue/parseQueueValue round-trip, including null referral and bare step-1 ids', async () => {
  assert.equal(queueValue('profile-a', 'profile-b'), 'profile-a|profile-b');
  assert.equal(queueValue('profile-a', null), 'profile-a|');
  assert.deepEqual(parseQueueValue('profile-a|profile-b'), { id: 'profile-a', referralId: 'profile-b', done: null });
  assert.deepEqual(parseQueueValue('profile-a|'), { id: 'profile-a', referralId: null, done: null });
  assert.deepEqual(parseQueueValue('profile-a'), { id: 'profile-a', referralId: null, done: null });
  assert.equal(parseQueueValue(''), null);
  assert.equal(parseQueueValue(null), null);
});

await check('chunkRange never spans shards; cursor validation rejects out-of-range cursors', async () => {
  const W = GRAB_SHARD_WIDTH;
  const r = chunkRange({ shard: 0, nextTick: W - 5 }, 100);
  assert.deepEqual(r, { shard: 0, startTick: W - 5, endTick: W });
  assert.equal(validateGrabCursor({ shard: 0, nextTick: 1 }).ok, true);
  assert.equal(validateGrabCursor({ shard: 0, nextTick: 0 }).ok, false);
  assert.equal(validateGrabCursor({ shard: 0, nextTick: W + 2 }).ok, false);
  assert.equal(validateGrabCursor({ shard: 1, nextTick: 1 }).ok, false);
  // The boundary position (one past the shard end) is a valid
  // cursor: it means "this shard is done".
  assert.equal(validateGrabCursor({ shard: 0, nextTick: W + 1 }).ok, true);
  // The width is a parameter, not the production constant: a
  // cursor in shard 1 at tick 151 is valid under width 100 and
  // invalid under the production width (this exact mismatch
  // once rejected every /advance past shard 0 in the driver).
  assert.equal(validateGrabCursor({ shard: 1, nextTick: 151 }, 100).ok, true);
  assert.equal(validateGrabCursor({ shard: 1, nextTick: 151 }).ok, false);
  assert.equal(validateGrabCursor({ shard: 1, nextTick: 151 }, 100).ok, true);
  const narrow = newGrabState('2026-12-15', T0, 100);
  narrow.shard = 1;
  narrow.nextTick = 151;
  assert.equal(validateGrabState(narrow).ok, true);
  assert.equal(validateGrabState({ ...narrow, shardWidth: 0 }).ok, false);
  assert.equal(compareCursors({ shard: 0, nextTick: 5 }, { shard: 0, nextTick: 6 }), -1);
  assert.equal(compareCursors({ shard: 1, nextTick: 1 }, { shard: 0, nextTick: W }), 1);
  assert.equal(compareCursors({ shard: 2, nextTick: 3 }, { shard: 2, nextTick: 3 }), 0);
});

await check('chunkRecordsForBudgets: CPU and subrequest bounds, the tighter one binds', async () => {
  // At the step-1 proxy (78.65 µs/record), the 30 s CPU budget
  // with 50% margin binds over the 1M subrequest limit.
  const a = chunkRecordsForBudgets({ perRecordCpuUs: 78.65, cpuBudgetMs: 30000, cpuMargin: 0.5, perRecordCalls: 2, subrequestLimit: 1000000, subrequestMargin: 0.2 });
  assert.equal(a.byCpu, 190718);
  assert.equal(a.bySubrequests, 400000);
  assert.equal(a.chunkRecords, 190718);
  assert.equal(a.binding, 'cpu');
  // At the Paid default subrequest limit (10,000), subrequests
  // bind hard: ~4,000 records a chunk — the raise is required.
  const b = chunkRecordsForBudgets({ perRecordCpuUs: 38, cpuBudgetMs: 30000, cpuMargin: 0.5, perRecordCalls: 2, subrequestLimit: 10000, subrequestMargin: 0.2 });
  assert.equal(b.bySubrequests, 4000);
  assert.equal(b.binding, 'subrequests');
});

await check('isGrabHour: 12am America/Vancouver; grabDayFor is the UTC date', async () => {
  // BC permanent Pacific time (PCT, UTC-7) from 1 Nov 2026:
  // 12am Gary's time is 07:00 UTC year-round. (Under the old
  // PST rule December would have been 08:00 UTC — that rule is
  // gone; tzdata 2026b+.)
  assert.equal(isGrabHour(Date.UTC(2026, 11, 15, 7, 0, 0)), true);
  // 12am in July (PDT, also UTC-7) = 07:00 UTC — same hour.
  assert.equal(isGrabHour(Date.UTC(2026, 6, 15, 7, 0, 0)), true);
  // 1am PST-era December (08:00 UTC) is now 1am local: not the grab hour.
  assert.equal(isGrabHour(Date.UTC(2026, 11, 15, 8, 0, 0)), false);
  assert.equal(isGrabHour(Date.UTC(2026, 11, 15, 20, 0, 0)), false);
  assert.equal(isGrabHour(Date.UTC(2026, 11, 15, 6, 0, 0)), false);
  assert.equal(grabDayFor(Date.UTC(2026, 11, 15, 7, 0, 0)), '2026-12-15');
  assert.equal(utcDay(T0), '2026-12-15');
});

await check('validateGrabState accepts a fresh state and rejects bad tallies/cursors/doneReason', async () => {
  assert.equal(validateGrabState(newGrabState('2026-12-15', T0)).ok, true);
  const bad = newGrabState('2026-12-15', T0);
  bad.tallies.verified = -1;
  assert.equal(validateGrabState(bad).ok, false);
  const bad2 = newGrabState('2026-12-15', T0);
  bad2.doneReason = 'banana';
  assert.equal(validateGrabState(bad2).ok, false);
  assert.deepEqual(newGrabTallies(), { checked: 0, verified: 0, pending: 0, not_verified: 0, expired: 0, skipped: 0 });
  assert.equal(GRAB_DAILY_CAP, 1_000_000_000);
});

// --- GrabState DO ---

await check('GrabState /start is idempotent; /advance rejects a backward cursor and shrinking tallies; /finish marks done', async () => {
  setNow(T0);
  const d = new GrabState(fakeState());
  const g0 = await callDo(d, '/get');
  assert.equal(g0.body.state, null);
  const s1 = await callDo(d, '/start', { grabDay: '2026-12-15' });
  assert.equal(s1.status, 200);
  assert.equal(s1.body.resumed, false);
  assert.equal(s1.body.state.grabDay, '2026-12-15');
  assert.equal(s1.body.state.done, false);
  const s2 = await callDo(d, '/start', { grabDay: '2026-12-15' });
  assert.equal(s2.body.resumed, true);
  assert.deepEqual(s2.body.state, s1.body.state);
  // Advance forward: fine.
  const fwd = { ...s1.body.state, shard: 0, nextTick: 500, tallies: { ...s1.body.state.tallies, checked: 499 } };
  const a1 = await callDo(d, '/advance', { state: fwd });
  assert.equal(a1.status, 200);
  // Backward cursor: 409. Shrinking tallies: 409. Bad shape: 400.
  const back = { ...fwd, nextTick: 100 };
  assert.equal((await callDo(d, '/advance', { state: back })).status, 409);
  const shrink = { ...fwd, tallies: { ...fwd.tallies, checked: 10 } };
  assert.equal((await callDo(d, '/advance', { state: shrink })).status, 409);
  assert.equal((await callDo(d, '/advance', { state: { ...fwd, grabDay: 'nope' } })).status, 400);
  // Finish: done, doneReason recorded; a bad reason is a 400.
  assert.equal((await callDo(d, '/finish', { doneReason: 'banana' })).status, 400);
  const fin = await callDo(d, '/finish', { tallies: fwd.tallies, doneReason: 'exhausted' });
  assert.equal(fin.status, 200);
  assert.equal(fin.body.state.done, true);
  assert.equal(fin.body.state.doneReason, 'exhausted');
  // A start for a finished day returns the finished state.
  const s3 = await callDo(d, '/start', { grabDay: '2026-12-15' });
  assert.equal(s3.body.state.done, true);
  // A finish with no state at all is a 404.
  const empty = new GrabState(fakeState());
  assert.equal((await callDo(empty, '/finish', { doneReason: 'cap' })).status, 404);
});

// --- Driver end to end through the real Worker routes ---

function seedSmallStore(sharedMap, { n = 200, shardWidth = 100, seed = 0xc0ffee } = {}) {
  const rand = mulberry32(seed);
  const ids = new Array(n);
  const records = [];
  for (let i = 0; i < n; i++) {
    const tick = i + 1;
    const id = `profile-${String(tick).padStart(4, '0')}`;
    ids[i] = id;
    const windowStartMs = T0 - ((n - tick) / n) * YEAR;
    let rec;
    if (tick <= 3) {
      rec = newTempRecord({ id, referralId: 'ref:genesis', activationTick: tick, windowStart: new Date(windowStartMs).toISOString(), createdAt: new Date(windowStartMs).toISOString() });
      rec = { ...rec, status: 'verified', verificationState: 'verified', verifiedTick: tick, grabDay: utcDay(windowStartMs) };
    } else {
      const roll = rand();
      const referrerTick = 1 + Math.floor(rand() * (tick - 1));
      const referralId = ids[referrerTick - 1];
      if (roll < 0.85) {
        rec = newTempRecord({ id, referralId, activationTick: tick, windowStart: new Date(windowStartMs).toISOString(), createdAt: new Date(windowStartMs).toISOString() });
      } else if (roll < 0.9) {
        const start = T0 - 400 * DAY - rand() * 30 * DAY;
        rec = newTempRecord({ id, referralId, activationTick: tick, windowStart: new Date(start).toISOString(), createdAt: new Date(start).toISOString() });
      } else if (roll < 0.95) {
        rec = newTempRecord({ id, referralId, activationTick: tick, windowStart: new Date(windowStartMs).toISOString(), createdAt: new Date(windowStartMs).toISOString() });
        rec = { ...rec, discarded: true };
      } else {
        rec = newTempRecord({ id, referralId: null, activationTick: tick, windowStart: new Date(windowStartMs).toISOString(), createdAt: new Date(windowStartMs).toISOString() });
      }
    }
    records.push(rec);
    sharedMap.set(`temp:${id}:record`, rec);
    const shard = Math.floor((tick - 1) / shardWidth);
    sharedMap.set(`temp:index:${shard}:q:${String(tick).padStart(16, '0')}`, queueValue(id, rec.referralId));
  }
  // The tick counter is where /temp/activate would have left it
  // after activating n temps: the next tick is n+1. The grab's
  // rotation creation allocates from this counter — without it,
  // rotations would re-allocate ticks 1..n and overwrite the
  // seeded queue entries.
  sharedMap.set('grab:current:nextActivationTick', n + 1);
  return records;
}

// Sequential reference: the step-1 scan logic, batch-aware —
// the chunked driver processes entries in tick-order batches of
// GRAB_BATCH_CONCURRENCY with Promise.all inside a batch, so a
// referrer in the SAME batch reads the referrer's pre-batch
// state, and a referrer in an earlier batch or chunk reads its
// post-apply state. This reference reproduces exactly that: the
// state map is only updated between batches, never inside one.
// Batches RESET at chunk boundaries (a referrer in the previous
// chunk always resolves post-apply) — modelling them as
// continuous across chunks diverges by a few records on some
// seeds (caught by the miniflare smoke test, 2026-11-15: the
// driver was right, the continuous reference was wrong).
function referenceScan(records, concurrency = GRAB_BATCH_CONCURRENCY, chunkRecords = 50, nowMs = T0) {
  const byId = new Map(records.map((r) => [r.id, r]));
  const state = new Map(records.map((r) => [r.id, r.verificationState]));
  const tallies = newGrabTallies();
  const outcomes = [];
  for (let c = 0; c < records.length; c += chunkRecords) {
    const chunk = records.slice(c, c + chunkRecords);
    for (let b = 0; b < chunk.length; b += concurrency) {
      const batch = chunk.slice(b, b + concurrency);
      const snapshot = new Map(state);
      const results = batch.map((rec) => {
        let referrerState = null;
        // The genesis claim is only the root (tick 1) — a later
        // temp carrying 'ref:genesis' is genesis_not_root, exactly
        // as the driver resolves it.
        const genesis = genesisReferrerState(rec.referralId, rec.activationTick);
        if (genesis) referrerState = genesis;
        else if (rec.referralId) {
          const ref = byId.get(rec.referralId);
          referrerState = !ref ? 'missing' : snapshot.get(ref.id);
          if (referrerState !== 'verified' && referrerState !== 'missing') referrerState = 'pending';
        }
        const { outcome, reason } = checkChain(rec, nowMs, referrerState);
        return { rec, outcome, reason };
      });
      for (const { rec, outcome, reason } of results) {
        const next = applyOutcome(rec, outcome, rec.activationTick, utcDay(nowMs));
        tallies.checked += 1;
        // The outcome is 'skip'; the tally key is 'skipped'.
        tallies[outcome === 'skip' ? 'skipped' : outcome] += 1;
        state.set(rec.id, next.verificationState);
        // A skip still writes a log entry when the grab creates
        // (or reuses) a rotation for it (FixNet temp rotation):
        // the record IS verified, so /log-batch logs it as
        // 'verified' with reason 'already_verified' — the
        // crash-repair write. nextTemp is random per run, so the
        // reference omits it and the driver test strips it.
        if (outcome === 'skip') {
          outcomes.push({ tick: rec.activationTick, id: rec.id, outcome: 'verified', day: utcDay(nowMs), reason: 'already_verified' });
        } else {
          outcomes.push({ tick: rec.activationTick, id: rec.id, outcome, day: utcDay(nowMs), reason });
        }
      }
    }
  }
  return { tallies, outcomes };
}

await check('driver end to end: chunked passes over 2 shards match the sequential reference', async () => {
  setNow(T0);
  const sharedMap = new Map();
  const records = seedSmallStore(sharedMap, { n: 200, shardWidth: 100 });
  const expected = referenceScan(records);
  const env = fakeEnv(sharedMap);
  let calls = 0;
  let state = null;
  let done = false;
  while (!done) {
    const r = await callWorker(env, 'POST', '/admin/grab', { chain: false, chunkRecords: 50, shardWidth: 100 });
    assert.equal(r.status, 200, `chunk ${calls} failed: ${JSON.stringify(r.body)}`);
    assert.equal(r.body.ok, true);
    state = r.body.state;
    done = r.body.done;
    calls += 1;
    assert.ok(calls < 20, 'the grab did not finish in a reasonable number of chunks');
  }
  assert.equal(calls, 5, '200 records at 50/chunk over 2 shards = 4 data chunks + 1 probe of shard 2 (the probe returns done via the maxTick bound — the cursor is past the highest tick the grab started with — which is what proves exhaustion; a full shard says nothing about the next one)');
  assert.equal(state.done, true);
  assert.equal(state.doneReason, 'exhausted');
  assert.deepEqual(state.tallies, expected.tallies);
  // The outcome log holds exactly the reference outcomes, in tick order.
  // (nextTemp is stripped for the comparison — the reference does
  // not model rotations; the rotation linkage is asserted just below.)
  const log = [];
  for (let s = 0; s < 2; s++) {
    const idx = new TempIndex(namespacedState(sharedMap, `temp:index:${s}`));
    const o = await callDo(idx, '/outcomes');
    log.push(...o.body.entries);
  }
  log.sort((a, b) => a.tick - b.tick);
  assert.deepEqual(log.map(({ nextTemp, ...rest }) => rest), expected.outcomes);
  // Every verified outcome carries its rotation (nextTemp), every
  // other outcome carries null — and the rotation records are
  // real: referral = the old temp, owner inherited (null here),
  // rotatesFrom set, old record points back at the rotation.
  // (The log's verified entries include the skip-repairs: the 3
  // pre-verified roots log as 'verified'/'already_verified'.)
  const verifiedLog = log.filter((e) => e.outcome === 'verified');
  assert.equal(verifiedLog.length, expected.tallies.verified + expected.tallies.skipped);
  for (const e of verifiedLog) {
    assert.ok(e.nextTemp && typeof e.nextTemp.id === 'string' && e.nextTemp.id.startsWith('profile-'), `verified tick ${e.tick} must carry nextTemp`);
    assert.ok(Number.isInteger(e.nextTemp.tick) && e.nextTemp.tick > 200, `rotation tick must be past the seeded range, got ${e.nextTemp.tick}`);
    const rot = sharedMap.get(`temp:${e.nextTemp.id}:record`);
    assert.ok(rot, `rotation record ${e.nextTemp.id} must exist`);
    assert.equal(rot.referralId, e.id);
    assert.equal(rot.rotatesFrom, e.id);
    assert.equal(rot.ownerUserId, null);
    assert.equal(rot.activationTick, e.nextTemp.tick);
    assert.equal(rot.verificationState, 'pending');
    assert.equal(sharedMap.get(`temp:${e.id}:record`).rotationTempId, e.nextTemp.id);
  }
  for (const e of log.filter((e) => e.outcome !== 'verified')) {
    assert.equal(e.nextTemp, null);
  }
  // The rotations themselves are still pending — the grab's
  // maxTick bound means same-grab rotations wait for the next grab.
  const rotations = [...sharedMap.values()].filter((v) => v && typeof v === 'object' && typeof v.rotatesFrom === 'string' && v.rotatesFrom);
  assert.equal(rotations.length, expected.tallies.verified + expected.tallies.skipped);
  assert.ok(rotations.every((r) => r.verificationState === 'pending'));
  // Verified ticks are monotonic in tick order.
  const verifiedTicks = log.filter((e) => e.outcome === 'verified').map((e) => e.tick);
  for (let i = 1; i < verifiedTicks.length; i++) {
    assert.ok(verifiedTicks[i] > verifiedTicks[i - 1], 'verified ticks must be monotonic');
  }
  // A re-run after a finished grab returns done without changes.
  const again = await callWorker(env, 'POST', '/admin/grab', { chain: false, chunkRecords: 50, shardWidth: 100 });
  assert.equal(again.body.done, true);
  assert.deepEqual(again.body.state.tallies, expected.tallies);
  assert.equal(again.body.chunk, null);
});

await check('driver resumes from a mid-grab cursor and finishes with the same tallies', async () => {
  setNow(T0);
  const sharedMap = new Map();
  const records = seedSmallStore(sharedMap, { n: 200, shardWidth: 100 });
  const expected = referenceScan(records);
  const env = fakeEnv(sharedMap);
  const first = await callWorker(env, 'POST', '/admin/grab', { chain: false, chunkRecords: 50, shardWidth: 100 });
  assert.equal(first.body.done, false);
  assert.equal(first.body.state.shard, 0);
  assert.equal(first.body.state.nextTick, 51);
  // Simulate a crashed chain: the state persists, the next call resumes.
  let done = false;
  let calls = 1;
  while (!done) {
    const r = await callWorker(env, 'POST', '/admin/grab', { chain: false, chunkRecords: 50, shardWidth: 100 });
    done = r.body.done;
    calls += 1;
    assert.ok(calls < 20);
  }
  const g = await callWorker(env, 'GET', '/admin/grab');
  assert.equal(g.body.state.done, true);
  assert.deepEqual(g.body.state.tallies, expected.tallies);
});

await check('Q2 cap: the grab stops at the cap (queue for the next day) and the rest stay pending', async () => {
  setNow(T0);
  const sharedMap = new Map();
  // 10 records in a linear chain: tick 1 is the genesis root,
  // tick N refers to tick N-1. A chain works here because the
  // concurrency is 1 — one link per batch, so each batch's
  // referrer is already verified by the previous batch. (A
  // chain in one batch would NOT work: verification propagates
  // one link per batch, so a chain of 10 in one batch yields
  // only 1 verified and the cap could never bind.)
  for (let tick = 1; tick <= 10; tick++) {
    const id = `profile-${String(tick).padStart(4, '0')}`;
    const referralId = tick === 1 ? 'ref:genesis' : `profile-${String(tick - 1).padStart(4, '0')}`;
    const rec = newTempRecord({ id, referralId, activationTick: tick, windowStart: new Date(T0 - DAY).toISOString(), createdAt: new Date(T0 - DAY).toISOString() });
    sharedMap.set(`temp:${id}:record`, rec);
    sharedMap.set(`temp:index:0:q:${String(tick).padStart(16, '0')}`, queueValue(id, referralId));
  }
  // The tick counter is where /temp/activate would have left it
  // (see seedSmallStore): without it the grab's maxTick snapshot
  // is 0 and the grab ends before checking anything.
  sharedMap.set('grab:current:nextActivationTick', 11);
  const env = fakeEnv(sharedMap);
  // concurrency 1: the cap is enforced per batch, so a batch of
  // 1 stops exactly at the cap (a batch of 16 could overshoot
  // by up to 15 — negligible at 1B, documented in grab.js).
  const r = await callWorker(env, 'POST', '/admin/grab', { chain: false, chunkRecords: 100, shardWidth: 100, cap: 3, concurrency: 1 });
  assert.equal(r.status, 200);
  assert.equal(r.body.done, true);
  assert.equal(r.body.capHit, true);
  assert.equal(r.body.doneReason, 'cap');
  assert.equal(r.body.state.tallies.verified, 3);
  assert.equal(r.body.state.tallies.checked, 3);
  // The remaining 7 were never checked this grab: still pending in the store.
  const rec4 = sharedMap.get('temp:profile-0004:record');
  assert.equal(rec4.verificationState, 'pending');
  // A re-run for the same day returns the finished (cap-hit) state without work.
  const again = await callWorker(env, 'POST', '/admin/grab', { chain: false, chunkRecords: 100, shardWidth: 100, cap: 3 });
  assert.equal(again.body.done, true);
  assert.equal(again.body.state.tallies.checked, 3);
});

await check('GET /admin/grab reads the state without creating it; /admin/grab needs no secret locally', async () => {
  setNow(T0);
  const env = fakeEnv(new Map());
  const g0 = await callWorker(env, 'GET', '/admin/grab');
  assert.equal(g0.status, 200);
  assert.equal(g0.body.state, null);
  // The service card lists the grab routes and the grab block.
  const svc = await callWorker(env, 'GET', '/');
  assert.equal(svc.status, 200);
  assert.equal(svc.body.version, '0.8.1');
  assert.ok(svc.body.routes.includes('POST /admin/grab'));
  assert.ok(svc.body.routes.includes('GET /admin/grab'));
  assert.ok(svc.body.routes.includes('GET /admin/grab-outcomes'));
  assert.ok(svc.body.routes.includes('POST /admin/rotate'));
  assert.ok(svc.body.routes.includes('POST /temp/activate'));
  assert.ok(svc.body.routes.includes('POST /register'));
  assert.equal(svc.body.grab.daily_cap, GRAB_DAILY_CAP);
  assert.equal(svc.body.grab.chunk_records, GRAB_CHUNK_RECORDS);
});

// --- discard: /log-batch marks terminal queue entries done ---

await check('/log-batch marks terminal queue entries done, leaves pending unmarked; the outcome log is untouched', async () => {
  const sharedMap = new Map();
  const index = new TempIndex(namespacedState(sharedMap, 'temp:index:0'));
  for (const [tick, id, ref] of [[1, 'profile-a', 'ref:genesis'], [2, 'profile-b', 'profile-a'], [3, 'profile-c', 'profile-a'], [4, 'profile-d', null]]) {
    await callDo(index, '/enqueue', { activationTick: tick, id, referralId: ref });
  }
  const logged = await callDo(index, '/log-batch', { entries: [
    { tick: 1, id: 'profile-a', outcome: 'verified', referralId: 'ref:genesis' },
    { tick: 2, id: 'profile-b', outcome: 'pending', referralId: 'profile-a' },
    { tick: 3, id: 'profile-c', outcome: 'not_verified', referralId: 'profile-a' },
    { tick: 4, id: 'profile-d', outcome: 'expired', referralId: null },
  ] });
  assert.equal(logged.body.logged, 4);
  assert.equal(logged.body.marked, 3);
  const q = await callDo(index, '/queue-range', { startTick: 1, endTick: 4 });
  assert.deepEqual(q.body.entries.map((e) => e.done), ['verified', null, 'not_verified', 'expired']);
  // The referral survives the marking (the driver still reads it from the queue value).
  assert.equal(q.body.entries[0].referralId, 'ref:genesis');
  assert.equal(q.body.entries[3].referralId, null);
  // The outcome log holds all four outcomes — the marking never touches it.
  const o = await callDo(index, '/outcomes');
  assert.deepEqual(o.body.entries.map((e) => e.outcome), ['verified', 'pending', 'not_verified', 'expired']);
  // /status counts the discarded entries.
  const s = await callDo(index, '/status');
  assert.equal(s.body.queued, 4);
  assert.equal(s.body.done, 3);
  assert.equal(s.body.logged, 4);
  // Re-logging the same batch is idempotent (same values, same markers).
  const again = await callDo(index, '/log-batch', { entries: [
    { tick: 1, id: 'profile-a', outcome: 'verified', referralId: 'ref:genesis' },
  ] });
  assert.equal(again.body.logged, 1);
  assert.equal(again.body.marked, 1);
  const q2 = await callDo(index, '/queue-range', { startTick: 1, endTick: 4 });
  assert.deepEqual(q2.body.entries.map((e) => e.done), ['verified', null, 'not_verified', 'expired']);
  // Without a supplied referralId the marking reads the stored value (and never drops it).
  const unmarked = await callDo(index, '/log-batch', { entries: [
    { tick: 2, id: 'profile-b', outcome: 'expired' },
  ] });
  assert.equal(unmarked.body.marked, 1);
  const q3 = await callDo(index, '/queue-range', { startTick: 2, endTick: 2 });
  assert.equal(q3.body.entries[0].done, 'expired');
  assert.equal(q3.body.entries[0].referralId, 'profile-a');
});

await check('/log-batch skip entries mark done:verified without a log write', async () => {
  const sharedMap = new Map();
  const index = new TempIndex(namespacedState(sharedMap, 'temp:index:0'));
  await callDo(index, '/enqueue', { activationTick: 1, id: 'profile-a', referralId: 'ref:genesis' });
  const r = await callDo(index, '/log-batch', { entries: [{ tick: 1, id: 'profile-a', outcome: 'skip', referralId: 'ref:genesis' }] });
  assert.equal(r.body.logged, 0);
  assert.equal(r.body.marked, 1);
  const q = await callDo(index, '/queue-range', { startTick: 1, endTick: 1 });
  assert.equal(q.body.entries[0].done, 'verified');
  const o = await callDo(index, '/outcomes');
  assert.deepEqual(o.body.entries, []);
  // A skip with no referralId supplied marks via the stored value.
  await callDo(index, '/enqueue', { activationTick: 2, id: 'profile-b', referralId: 'profile-a' });
  const r2 = await callDo(index, '/log-batch', { entries: [{ tick: 2, id: 'profile-b', outcome: 'skip' }] });
  assert.equal(r2.body.marked, 1);
  const q2 = await callDo(index, '/queue-range', { startTick: 2, endTick: 2 });
  assert.equal(q2.body.entries[0].done, 'verified');
  assert.equal(q2.body.entries[0].referralId, 'profile-a');
});

// --- yield intake: GrabState /next-tick and POST /temp/activate ---

async function callWorkerHeaders(env, method, path, body, headers = {}) {
  const req = new Request(`http://grab${path}`, {
    method,
    headers: { 'content-type': 'application/json', ...headers },
    body: body ? JSON.stringify(body) : undefined,
  });
  const res = await worker.fetch(req, env, {});
  return { status: res.status, body: await res.json() };
}

/** Drive the grab to completion, one chunk per call (chain: false). */
async function runGrabToDone(env, opts = {}) {
  let calls = 0;
  let last = null;
  let done = false;
  while (!done) {
    last = await callWorker(env, 'POST', '/admin/grab', { chain: false, chunkRecords: 50, shardWidth: 100, ...opts });
    assert.equal(last.status, 200, `chunk ${calls} failed: ${JSON.stringify(last.body)}`);
    done = last.body.done;
    calls += 1;
    assert.ok(calls < 20, 'the grab did not finish in a reasonable number of chunks');
  }
  return last;
}

await check('GrabState /next-tick assigns monotonic ticks starting at 1', async () => {
  const sharedMap = new Map();
  const gs = new GrabState(namespacedState(sharedMap, 'grab:current'));
  assert.deepEqual((await callDo(gs, '/next-tick')).body, { ok: true, tick: 1 });
  assert.deepEqual((await callDo(gs, '/next-tick')).body, { ok: true, tick: 2 });
  assert.deepEqual((await callDo(gs, '/next-tick')).body, { ok: true, tick: 3 });
  // The counter lives under its own key — the grab state is untouched.
  assert.equal((await callDo(gs, '/get')).body.state, null);
});

await check('POST /temp/activate assigns tick 1, stores the record, enqueues it', async () => {
  setNow(T0);
  const sharedMap = new Map();
  const env = fakeEnv(sharedMap);
  const a = await callWorker(env, 'POST', '/temp/activate', { id: 'profile-aaa', referralId: 'ref:genesis' });
  assert.equal(a.status, 200, JSON.stringify(a.body));
  assert.equal(a.body.ok, true);
  assert.equal(a.body.resumed, false);
  assert.equal(a.body.activationTick, 1);
  assert.equal(a.body.verificationState, 'pending');
  assert.equal(a.body.windowEnd, new Date(T0 + YEAR).toISOString());
  assert.equal(a.body.referralId, 'ref:genesis');
  // The record is stored, pending, window now + 1 year.
  const rec = sharedMap.get('temp:profile-aaa:record');
  assert.equal(rec.activationTick, 1);
  assert.equal(rec.verificationState, 'pending');
  assert.equal(rec.windowStart, new Date(T0).toISOString());
  assert.equal(rec.windowEnd, new Date(T0 + YEAR).toISOString());
  // The queue entry is in shard 0, live (done null).
  const idx = new TempIndex(namespacedState(sharedMap, 'temp:index:0'));
  const q = await callDo(idx, '/queue-range', { startTick: 1, endTick: 1 });
  assert.deepEqual(q.body.entries, [{ activationTick: 1, id: 'profile-aaa', referralId: 'ref:genesis', done: null }]);
  // A second temp, no referral, gets tick 2.
  const b = await callWorker(env, 'POST', '/temp/activate', { id: 'profile-bbb' });
  assert.equal(b.status, 200);
  assert.equal(b.body.activationTick, 2);
  assert.equal(b.body.referralId, null);
});

await check('POST /temp/activate is idempotent: same id returns the same tick, never re-numbers; re-enqueue repairs a missing queue entry', async () => {
  setNow(T0);
  const sharedMap = new Map();
  const env = fakeEnv(sharedMap);
  const first = await callWorker(env, 'POST', '/temp/activate', { id: 'profile-aaa', referralId: 'ref:genesis' });
  assert.equal(first.body.activationTick, 1);
  const again = await callWorker(env, 'POST', '/temp/activate', { id: 'profile-aaa', referralId: 'ref:genesis' });
  assert.equal(again.status, 200);
  assert.equal(again.body.resumed, true);
  assert.equal(again.body.activationTick, 1);
  // A third activation still returns tick 1 — and the counter did not move.
  const third = await callWorker(env, 'POST', '/temp/activate', { id: 'profile-ccc' });
  assert.equal(third.body.activationTick, 2);
  // Simulate a crashed first activation: /put landed, /enqueue did not.
  sharedMap.delete('temp:index:0:q:0000000000000001');
  const repaired = await callWorker(env, 'POST', '/temp/activate', { id: 'profile-aaa', referralId: 'ref:genesis' });
  assert.equal(repaired.body.activationTick, 1);
  assert.equal(repaired.body.resumed, true);
  const idx = new TempIndex(namespacedState(sharedMap, 'temp:index:0'));
  const q = await callDo(idx, '/queue-range', { startTick: 1, endTick: 1 });
  assert.equal(q.body.entries.length, 1);
  assert.equal(q.body.entries[0].id, 'profile-aaa');
});

await check('POST /temp/activate rejects a bad id (400) and needs the key when a secret is set (401)', async () => {
  setNow(T0);
  const sharedMap = new Map();
  const env = fakeEnv(sharedMap);
  for (const bad of [{}, { id: '' }, { id: 'not-a-profile' }, { id: 42 }, { id: 'profile-x', referralId: '' }, { id: 'profile-x', windowStart: 'not-a-date' }]) {
    const r = await callWorker(env, 'POST', '/temp/activate', bad);
    assert.equal(r.status, 400, `expected 400 for ${JSON.stringify(bad)}, got ${r.status} ${JSON.stringify(r.body)}`);
  }
  // No record was created by any of the bad calls — the counter did not move.
  const good = await callWorker(env, 'POST', '/temp/activate', { id: 'profile-good' });
  assert.equal(good.body.activationTick, 1);
  // With a secret set, the route needs the key like /admin/*.
  const envSecret = { ...fakeEnv(new Map()), PING_SHARED_SECRET: 'test-secret' };
  const noKey = await callWorkerHeaders(envSecret, 'POST', '/temp/activate', { id: 'profile-a' });
  assert.equal(noKey.status, 401);
  const wrongKey = await callWorkerHeaders(envSecret, 'POST', '/temp/activate', { id: 'profile-a' }, { 'x-lucid-ping-key': 'wrong' });
  assert.equal(wrongKey.status, 401);
  const rightKey = await callWorkerHeaders(envSecret, 'POST', '/temp/activate', { id: 'profile-a' }, { 'x-lucid-ping-key': 'test-secret' });
  assert.equal(rightKey.status, 200);
  assert.equal(rightKey.body.activationTick, 1);
});

// --- discard, end to end: the second day's grab skips done entries ---

await check("day 2 grab skips done entries: tallies count only the still-pending records; a day-1 verified tick is never re-numbered", async () => {
  setNow(T0);
  const sharedMap = new Map();
  const records = seedSmallStore(sharedMap, { n: 200, shardWidth: 100 });
  const expected1 = referenceScan(records);
  const env = fakeEnv(sharedMap);
  let done = false;
  let calls = 0;
  while (!done) {
    const r = await callWorker(env, 'POST', '/admin/grab', { chain: false, chunkRecords: 50, shardWidth: 100 });
    done = r.body.done;
    calls += 1;
    assert.ok(calls < 20);
  }
  assert.deepEqual((await callWorker(env, 'GET', '/admin/grab')).body.state.tallies, expected1.tallies);
  // Every terminal record's queue entry is marked done — including
  // the 3 genesis roots, which the driver skipped and /log-batch
  // marked done:verified without a log write. (Only the 200
  // seeded ticks are counted here: day 1's rotations added their
  // own queue entries at ticks 201+, which are live, not done.)
  const queueValues = records.map((r) => {
    const shard = Math.floor((r.activationTick - 1) / 100);
    return parseQueueValue(sharedMap.get(`temp:index:${shard}:q:${String(r.activationTick).padStart(16, '0')}`));
  });
  assert.equal(queueValues.length, 200);
  const doneCount = queueValues.filter((q) => q.done !== null).length;
  assert.equal(doneCount, expected1.tallies.verified + expected1.tallies.not_verified + expected1.tallies.expired + expected1.tallies.skipped);
  // A day-1 verified record keeps its tick.
  const verifiedRec = [...sharedMap.values()].find((v) => v && typeof v === 'object' && v.verificationState === 'verified' && v.verifiedTick !== null);
  const tickBefore = verifiedRec.verifiedTick;
  // Day 2: fresh grab day, same store. The reference checks only
  // the live (unmarked) records, resolving referrers against ALL
  // day-1-end records (a referrer's state lives in its record
  // stub, not in the queue).
  setNow(T0 + DAY);
  const day1End = records.map((r) => sharedMap.get(`temp:${r.id}:record`));
  const live = day1End.filter((r) => {
    const shard = Math.floor((r.activationTick - 1) / 100);
    const qv = parseQueueValue(sharedMap.get(`temp:index:${shard}:q:${String(r.activationTick).padStart(16, '0')}`));
    return qv && qv.done === null;
  });
  assert.ok(live.length > 0, 'day 2 must still have pending records to check');
  assert.ok(live.length < 200, 'day 2 must skip the terminal records');
  const byId = new Map(day1End.map((r) => [r.id, r]));
  const refState = new Map(day1End.map((r) => [r.id, r.verificationState]));
  const expected2 = newGrabTallies();
  for (let c = 0; c < live.length; c += 50) {
    const chunk = live.slice(c, c + 50);
    for (let b = 0; b < chunk.length; b += GRAB_BATCH_CONCURRENCY) {
      const batch = chunk.slice(b, b + GRAB_BATCH_CONCURRENCY);
      const snapshot = new Map(refState);
      const results = batch.map((rec) => {
        let referrerState = null;
        const genesis = genesisReferrerState(rec.referralId, rec.activationTick);
        if (genesis) referrerState = genesis;
        else if (rec.referralId) {
          const ref = byId.get(rec.referralId);
          referrerState = !ref ? 'missing' : snapshot.get(ref.id);
          if (referrerState !== 'verified' && referrerState !== 'missing') referrerState = 'pending';
        }
        return { rec, outcome: checkChain(rec, T0 + DAY, referrerState).outcome };
      });
      for (const { rec, outcome } of results) {
        const next = applyOutcome(rec, outcome, rec.activationTick, utcDay(T0 + DAY));
        expected2.checked += 1;
        expected2[outcome === 'skip' ? 'skipped' : outcome] += 1;
        refState.set(rec.id, next.verificationState);
      }
    }
  }
  // Day 2 also walks day 1's rotations (ticks 201+, shard 2):
  // every one verifies — its referrer is a day-1 verified
  // original — and each yields a new rotation of its own (ticks
  // past day 2's maxTick, so they are not walked today). The
  // rotations never touch the originals' referrers, so the two
  // sets add: R1 = day-1 verified + skipped (rotations are
  // created for both outcomes).
  const rotationsDay1 = expected1.tallies.verified + expected1.tallies.skipped;
  expected2.checked += rotationsDay1;
  expected2.verified += rotationsDay1;
  assert.equal(expected2.checked, live.length + rotationsDay1);
  assert.ok(expected2.checked < expected1.tallies.checked, 'day 2 checks fewer records than day 1');
  let done2 = false;
  let calls2 = 0;
  while (!done2) {
    const r = await callWorker(env, 'POST', '/admin/grab', { chain: false, chunkRecords: 50, shardWidth: 100 });
    assert.equal(r.status, 200, `day-2 chunk ${calls2} failed: ${JSON.stringify(r.body)}`);
    done2 = r.body.done;
    calls2 += 1;
    assert.ok(calls2 < 20);
  }
  const state2 = (await callWorker(env, 'GET', '/admin/grab')).body.state;
  assert.deepEqual(state2.tallies, expected2);
  // The day-1 verified tick was never re-numbered.
  assert.equal(sharedMap.get(`temp:${verifiedRec.id}:record`).verifiedTick, tickBefore);
});

// --- genesis + outcomes + SP marking (FixNet) ---

await check('genesis end to end: tick 1 verifies, a later genesis claim is refused, a referee of the root verifies', async () => {
  setNow(T0);
  const sharedMap = new Map();
  const seed = (tick, id, referralId) => {
    const rec = newTempRecord({ id, referralId, activationTick: tick, windowStart: new Date(T0 - DAY).toISOString(), createdAt: new Date(T0 - DAY).toISOString() });
    sharedMap.set(`temp:${id}:record`, rec);
    sharedMap.set(`temp:index:0:q:${String(tick).padStart(16, '0')}`, queueValue(id, referralId));
  };
  seed(1, 'profile-root', 'ref:genesis');
  seed(2, 'profile-fake', 'ref:genesis'); // not the root tick — must NOT verify
  seed(3, 'profile-child', 'profile-root'); // refers to the root — verifies
  // The tick counter is where /temp/activate would have left it
  // (see seedSmallStore): without it the grab's maxTick snapshot
  // is 0 and the grab ends before checking anything.
  sharedMap.set('grab:current:nextActivationTick', 4);
  const env = fakeEnv(sharedMap);
  // concurrency 1: the root verifies in batch 1, so its referee
  // (tick 3) resolves against the verified record in batch 2.
  // (One batch would pend tick 3 — the documented same-batch gap.)
  const r = await runGrabToDone(env, { concurrency: 1 });
  assert.equal(r.body.done, true);
  assert.deepEqual(r.body.state.tallies, { checked: 3, verified: 2, pending: 0, not_verified: 1, expired: 0, skipped: 0 });
  const root = sharedMap.get('temp:profile-root:record');
  assert.equal(root.verificationState, 'verified');
  assert.equal(root.verifiedTick, 1);
  const fake = sharedMap.get('temp:profile-fake:record');
  assert.equal(fake.verificationState, 'not_verified');
  const child = sharedMap.get('temp:profile-child:record');
  assert.equal(child.verificationState, 'verified');
  // The outcome log carries the day and the reason for each —
  // plus next_temp on the verified entries (the rotation each
  // verified temp yields). Rotation ids are random, so they are
  // asserted against the old records' rotationTempId, not fixed.
  const o = await callWorker(env, 'GET', '/admin/grab-outcomes');
  assert.equal(o.status, 200);
  assert.deepEqual(
    o.body.outcomes.map(({ next_temp, ...rest }) => rest),
    [
      { tick: 1, id: 'profile-root', outcome: 'verified', day: '2026-12-15', reason: 'genesis_root' },
      { tick: 2, id: 'profile-fake', outcome: 'not_verified', day: '2026-12-15', reason: 'genesis_not_root' },
      { tick: 3, id: 'profile-child', outcome: 'verified', day: '2026-12-15', reason: 'chain_holds' },
    ],
  );
  assert.deepEqual(o.body.outcomes[0].next_temp, { id: root.rotationTempId, tick: 4 });
  assert.equal(o.body.outcomes[1].next_temp, null);
  assert.deepEqual(o.body.outcomes[2].next_temp, { id: child.rotationTempId, tick: 5 });
  // The rotation records are real: referral + rotatesFrom are
  // the old temp, owner inherited (null here — seeded without
  // one), pending, and enqueued at their ticks. The refused
  // fake yields no rotation.
  const rotRoot = sharedMap.get(`temp:${root.rotationTempId}:record`);
  assert.equal(rotRoot.referralId, 'profile-root');
  assert.equal(rotRoot.rotatesFrom, 'profile-root');
  assert.equal(rotRoot.ownerUserId, null);
  assert.equal(rotRoot.activationTick, 4);
  assert.equal(rotRoot.verificationState, 'pending');
  const rotChild = sharedMap.get(`temp:${child.rotationTempId}:record`);
  assert.equal(rotChild.referralId, 'profile-child');
  assert.equal(rotChild.activationTick, 5);
  assert.equal(fake.rotationTempId, null);
  const idx = new TempIndex(namespacedState(sharedMap, 'temp:index:0'));
  const q = await callDo(idx, '/queue-range', { startTick: 4, endTick: 5 });
  assert.deepEqual(q.body.entries.map((e) => e.id), [root.rotationTempId, child.rotationTempId]);
  assert.deepEqual(q.body.entries.map((e) => e.referralId), ['profile-root', 'profile-child']);
  // The day filter keeps only that day's outcomes.
  const filtered = await callWorker(env, 'GET', '/admin/grab-outcomes?day=2026-12-15');
  assert.equal(filtered.body.outcomes.length, 3);
  const none = await callWorker(env, 'GET', '/admin/grab-outcomes?day=2026-12-14');
  assert.deepEqual(none.body.outcomes, []);
  // A single shard read works.
  const shard0 = await callWorker(env, 'GET', '/admin/grab-outcomes?shard=0');
  assert.equal(shard0.body.outcomes.length, 3);
  const shard1 = await callWorker(env, 'GET', '/admin/grab-outcomes?shard=1');
  assert.deepEqual(shard1.body.outcomes, []);
});

await check("POST /admin/rotate backfills a rotation for an already-verified temp AND surfaces its next_temp in the outcome log", async () => {
  setNow(T0);
  const sharedMap = new Map();
  // One genesis-root temp, verified by an earlier grab (before
  // rotation existed): the record is verified, the outcome is
  // logged WITHOUT nextTemp, the queue entry is marked done —
  // the exact Genesis shape (verified 2026-11-17, genesis_root).
  // Without the outcome-log write in the backfill, the publish
  // (which reads ONLY the outcome log) would never learn the
  // next_temp and the temp would never rotate on sync.
  const id = 'profile-genesis';
  const rec = newTempRecord({ id, referralId: 'ref:genesis', activationTick: 1, windowStart: new Date(T0 - DAY).toISOString(), createdAt: new Date(T0 - DAY).toISOString() });
  const verified = { ...rec, status: 'verified', verificationState: 'verified', verifiedTick: 1, grabDay: '2026-12-15' };
  sharedMap.set(`temp:${id}:record`, verified);
  // Queue entry (live) + outcome logged by the verifying grab.
  sharedMap.set('temp:index:0:q:0000000000000001', queueValue(id, 'ref:genesis'));
  const idx = new TempIndex(namespacedState(sharedMap, 'temp:index:0'));
  const logged = await callDo(idx, '/log-batch', { entries: [{ tick: 1, id, outcome: 'verified', day: '2026-12-15', reason: 'genesis_root', nextTemp: null }] });
  assert.equal(logged.body.ok, true);
  // The verifying grab marked the queue entry done.
  assert.equal(parseQueueValue(sharedMap.get('temp:index:0:q:0000000000000001')).done, 'verified');
  // Next tick for the rotation record.
  sharedMap.set('grab:current:nextActivationTick', 2);
  const env = fakeEnv(sharedMap);
  // Before: the outcome log has no next_temp for Genesis.
  const before = await callWorker(env, 'GET', '/admin/grab-outcomes?day=2026-12-15');
  assert.equal(before.body.outcomes.length, 1);
  assert.equal(before.body.outcomes[0].next_temp, null);
  // The backfill creates the rotation...
  const r = await callWorker(env, 'POST', '/admin/rotate', { id });
  assert.equal(r.status, 200, JSON.stringify(r.body));
  assert.equal(r.body.ok, true);
  assert.equal(r.body.created, true);
  assert.ok(r.body.next_temp && typeof r.body.next_temp.id === 'string' && r.body.next_temp.id.startsWith('profile-'));
  assert.equal(r.body.next_temp.tick, 2);
  // ...and the outcome log now carries it, with day/reason preserved.
  const after = await callWorker(env, 'GET', '/admin/grab-outcomes?day=2026-12-15');
  assert.equal(after.body.outcomes.length, 1);
  assert.deepEqual(after.body.outcomes[0].next_temp, r.body.next_temp);
  assert.equal(after.body.outcomes[0].day, '2026-12-15');
  assert.equal(after.body.outcomes[0].reason, 'genesis_root');
  assert.equal(after.body.outcomes[0].outcome, 'verified');
  // The rotation record is real: referral + rotatesFrom are the old temp, pending.
  const rot = sharedMap.get(`temp:${r.body.next_temp.id}:record`);
  assert.ok(rot);
  assert.equal(rot.referralId, id);
  assert.equal(rot.rotatesFrom, id);
  assert.equal(rot.ownerUserId, null);
  assert.equal(rot.activationTick, 2);
  assert.equal(rot.verificationState, 'pending');
  assert.equal(sharedMap.get(`temp:${id}:record`).rotationTempId, r.body.next_temp.id);
  // The queue entry is still done:verified (the backfill did not disturb it).
  assert.equal(parseQueueValue(sharedMap.get('temp:index:0:q:0000000000000001')).done, 'verified');
  // Idempotent: a repeat returns the same rotation, created:false,
  // and the outcome log is unchanged.
  const again = await callWorker(env, 'POST', '/admin/rotate', { id });
  assert.equal(again.status, 200);
  assert.equal(again.body.created, false);
  assert.deepEqual(again.body.next_temp, r.body.next_temp);
  const after2 = await callWorker(env, 'GET', '/admin/grab-outcomes?day=2026-12-15');
  assert.deepEqual(after2.body.outcomes, after.body.outcomes);
  // Errors: unknown id 404, unverified temp 400.
  const missing = await callWorker(env, 'POST', '/admin/rotate', { id: 'profile-nope' });
  assert.equal(missing.status, 404);
  const pendingId = 'profile-pending';
  const pending = newTempRecord({ id: pendingId, referralId: id, activationTick: 3, windowStart: new Date(T0 - DAY).toISOString(), createdAt: new Date(T0 - DAY).toISOString() });
  sharedMap.set(`temp:${pendingId}:record`, pending);
  const notVerified = await callWorker(env, 'POST', '/admin/rotate', { id: pendingId });
  assert.equal(notVerified.status, 400);
});

await check("POST /admin/rotate with no logged outcome still surfaces the next_temp (grab day + already_verified)", async () => {
  setNow(T0);
  const sharedMap = new Map();
  // A verified temp whose verifying grab crashed before its
  // /log-batch: record verified, NO outcome entry, NO queue entry.
  const id = 'profile-unlogged';
  const rec = newTempRecord({ id, referralId: 'ref:genesis', activationTick: 1, windowStart: new Date(T0 - DAY).toISOString(), createdAt: new Date(T0 - DAY).toISOString() });
  const verified = { ...rec, status: 'verified', verificationState: 'verified', verifiedTick: 1, grabDay: '2026-12-15' };
  sharedMap.set(`temp:${id}:record`, verified);
  sharedMap.set('grab:current:nextActivationTick', 2);
  // A grab state for today, so the fallback day is the grab day.
  sharedMap.set('grab:current:grab', newGrabState('2026-12-15', T0));
  const env = fakeEnv(sharedMap);
  const r = await callWorker(env, 'POST', '/admin/rotate', { id });
  assert.equal(r.status, 200, JSON.stringify(r.body));
  assert.equal(r.body.created, true);
  // The outcome log now has the entry, attributed to the grab day.
  const after = await callWorker(env, 'GET', '/admin/grab-outcomes?day=2026-12-15');
  assert.equal(after.body.outcomes.length, 1);
  assert.deepEqual(after.body.outcomes[0].next_temp, r.body.next_temp);
  assert.equal(after.body.outcomes[0].outcome, 'verified');
  assert.equal(after.body.outcomes[0].day, '2026-12-15');
  assert.equal(after.body.outcomes[0].reason, 'already_verified');
});

await check('activate binds the owner and the grab marks their SP bucket verified', async () => {
  setNow(T0);
  const sharedMap = new Map();
  const env = fakeEnv(sharedMap);
  // Activate the genesis root as user-abc.
  const a = await callWorkerHeaders(env, 'POST', '/temp/activate', { id: 'profile-root', referralId: 'ref:genesis' }, { 'x-lucid-user': 'user-abc' });
  assert.equal(a.status, 200);
  assert.equal(a.body.activationTick, 1);
  const stored = sharedMap.get('temp:profile-root:record');
  assert.equal(stored.ownerUserId, 'user-abc');
  // Activate a second temp with no user header: no owner binds.
  const b = await callWorker(env, 'POST', '/temp/activate', { id: 'profile-orphan', referralId: 'profile-root' });
  assert.equal(b.status, 200);
  assert.equal(sharedMap.get('temp:profile-orphan:record').ownerUserId, null);
  // Run the grab (concurrency 1, so the orphan resolves against the
  // verified root): the root verifies, the orphan verifies behind it.
  const r = await runGrabToDone(env, { concurrency: 1 });
  assert.equal(r.body.state.tallies.verified, 2);
  // user-abc's bucket is marked verified — the 1,000 SP/day grant.
  const quota = sharedMap.get('user:user-abc:quota');
  assert.equal(quota.verified, true);
  // A peek now sees the verified grant: 100 + 1000, limit is the balance.
  const limiter = new PingRateLimiter(namespacedState(sharedMap, 'user:user-abc'));
  const peek = await limiter.fetch(new Request('http://limiter/peek', { method: 'POST' }));
  const peekBody = await peek.json();
  assert.equal(peekBody.remaining, 1100);
  assert.equal(peekBody.limit, 1100);
  // The orphan has no owner, so no bucket was marked for anyone else.
  assert.equal(sharedMap.get('user:user-orphan:quota'), undefined);
});

await check('/temp/activate resumed path re-marks an already-verified owner', async () => {
  setNow(T0);
  const sharedMap = new Map();
  const env = fakeEnv(sharedMap);
  await callWorkerHeaders(env, 'POST', '/temp/activate', { id: 'profile-root', referralId: 'ref:genesis' }, { 'x-lucid-user': 'user-abc' });
  await runGrabToDone(env);
  assert.equal(sharedMap.get('user:user-abc:quota').verified, true);
  // Wipe the marking (simulate a grab that verified but crashed
  // before marking), then re-activate: the resumed path re-marks.
  sharedMap.delete('user:user-abc:quota');
  const again = await callWorkerHeaders(env, 'POST', '/temp/activate', { id: 'profile-root', referralId: 'ref:genesis' }, { 'x-lucid-user': 'user-abc' });
  assert.equal(again.status, 200);
  assert.equal(again.body.resumed, true);
  assert.equal(again.body.verificationState, 'verified');
  assert.equal(sharedMap.get('user:user-abc:quota').verified, true);
});

// --- FixNet temp rotation (design D1–D9) ---

await check('GrabState /start snapshots maxTick from the tick counter; a resumed start keeps it', async () => {
  const sharedMap = new Map();
  const d = new GrabState(namespacedState(sharedMap, 'grab:current'));
  await callDo(d, '/next-tick'); // 1
  await callDo(d, '/next-tick'); // 2
  await callDo(d, '/next-tick'); // 3
  const s = await callDo(d, '/start', { grabDay: '2026-12-15' });
  assert.equal(s.body.state.maxTick, 3);
  // A later tick does not move the snapshot — it belongs to the next grab.
  await callDo(d, '/next-tick'); // 4
  const s2 = await callDo(d, '/start', { grabDay: '2026-12-15' });
  assert.equal(s2.body.resumed, true);
  assert.equal(s2.body.state.maxTick, 3);
  // No counter at all: maxTick 0 (an empty store — the grab ends at once).
  const empty = new GrabState(fakeState());
  const e = await callDo(empty, '/start', { grabDay: '2026-12-15' });
  assert.equal(e.body.state.maxTick, 0);
  // validateGrabState accepts maxTick, rejects a negative one.
  assert.equal(validateGrabState({ ...newGrabState('2026-12-15', T0), maxTick: 7 }).ok, true);
  assert.equal(validateGrabState({ ...newGrabState('2026-12-15', T0), maxTick: -1 }).ok, false);
  assert.equal(validateGrabState({ ...newGrabState('2026-12-15', T0), maxTick: 1.5 }).ok, false);
});

await check('rotation: the cycle — a verified temp yields its rotation, which verifies on the NEXT grab via chain_holds and yields the next one', async () => {
  setNow(T0);
  const sharedMap = new Map();
  const seed = (tick, id, referralId, ownerUserId = null) => {
    const rec = newTempRecord({ id, referralId, activationTick: tick, windowStart: new Date(T0 - DAY).toISOString(), createdAt: new Date(T0 - DAY).toISOString(), ownerUserId });
    sharedMap.set(`temp:${id}:record`, rec);
    sharedMap.set(`temp:index:0:q:${String(tick).padStart(16, '0')}`, queueValue(id, referralId));
  };
  seed(1, 'profile-root', 'ref:genesis', 'user-abc');
  sharedMap.set('grab:current:nextActivationTick', 2);
  const env = fakeEnv(sharedMap);
  // Day 1: the root verifies and yields T2 (tick 2). T2 is still
  // pending — the maxTick bound keeps same-grab rotations out of
  // the walk, so the grab ends instead of looping forever.
  const day1 = await runGrabToDone(env, { concurrency: 1 });
  assert.equal(day1.body.state.tallies.verified, 1);
  const root = sharedMap.get('temp:profile-root:record');
  const t2id = root.rotationTempId;
  assert.ok(t2id && t2id.startsWith('profile-') && t2id !== 'profile-root');
  const t2 = sharedMap.get(`temp:${t2id}:record`);
  assert.equal(t2.referralId, 'profile-root');
  assert.equal(t2.rotatesFrom, 'profile-root');
  assert.equal(t2.ownerUserId, 'user-abc');
  assert.equal(t2.activationTick, 2);
  assert.equal(t2.verificationState, 'pending');
  const o1 = await callWorker(env, 'GET', '/admin/grab-outcomes');
  assert.deepEqual(o1.body.outcomes[0].next_temp, { id: t2id, tick: 2 });
  // Day 2: T2's referrer (the root) is verified, so T2 verifies
  // with reason chain_holds — NOT genesis — and yields T3.
  setNow(T0 + DAY);
  const day2 = await runGrabToDone(env, { concurrency: 1 });
  assert.deepEqual(day2.body.state.tallies, { checked: 1, verified: 1, pending: 0, not_verified: 0, expired: 0, skipped: 0 });
  assert.equal(sharedMap.get(`temp:${t2id}:record`).verificationState, 'verified');
  assert.equal(sharedMap.get(`temp:${t2id}:record`).verifiedTick, 2);
  const t3id = sharedMap.get(`temp:${t2id}:record`).rotationTempId;
  const t3 = sharedMap.get(`temp:${t3id}:record`);
  assert.equal(t3.referralId, t2id);
  assert.equal(t3.rotatesFrom, t2id);
  assert.equal(t3.ownerUserId, 'user-abc');
  assert.equal(t3.activationTick, 3);
  const o2 = await callWorker(env, 'GET', '/admin/grab-outcomes?day=2026-12-16');
  assert.equal(o2.body.outcomes.length, 1);
  assert.equal(o2.body.outcomes[0].id, t2id);
  assert.equal(o2.body.outcomes[0].outcome, 'verified');
  assert.equal(o2.body.outcomes[0].reason, 'chain_holds');
  assert.deepEqual(o2.body.outcomes[0].next_temp, { id: t3id, tick: 3 });
  // The root's day-1 entry still carries ITS next_temp (T2).
  const o1again = await callWorker(env, 'GET', '/admin/grab-outcomes?day=2026-12-15');
  assert.deepEqual(o1again.body.outcomes[0].next_temp, { id: t2id, tick: 2 });
});

await check('rotation: a crashed chunk re-run reuses the rotation (no duplicate) and repairs the outcome log', async () => {
  setNow(T0);
  const sharedMap = new Map();
  const rec = newTempRecord({ id: 'profile-root', referralId: 'ref:genesis', activationTick: 1, windowStart: new Date(T0 - DAY).toISOString(), createdAt: new Date(T0 - DAY).toISOString() });
  sharedMap.set('temp:profile-root:record', rec);
  sharedMap.set('temp:index:0:q:0000000000000001', queueValue('profile-root', 'ref:genesis'));
  sharedMap.set('grab:current:nextActivationTick', 2);
  const env = fakeEnv(sharedMap);
  const day1 = await runGrabToDone(env, { concurrency: 1 });
  assert.equal(day1.body.state.tallies.verified, 1);
  const t2id = sharedMap.get('temp:profile-root:record').rotationTempId;
  assert.ok(t2id);
  // Simulate the crash: the chunk verified the root and created
  // the rotation, then died before its /log-batch — so the
  // outcome log has no entry, the queue entry is unmarked, and
  // the grab state is gone (the next trigger retries the chunk
  // from the start of the day).
  sharedMap.delete('grab:current:grab');
  sharedMap.delete('temp:index:0:o:0000000000000001:profile-root');
  sharedMap.set('temp:index:0:q:0000000000000001', queueValue('profile-root', 'ref:genesis'));
  // The re-run: /apply skips (already verified), the existing
  // rotation is REUSED — no second rotation record appears —
  // and the skip+nextTemp repairs the outcome log. (T2 is walked
  // too — it existed at the re-run's start — and verifies, which
  // is the re-run completing the work, not a duplicate.)
  const rerun = await runGrabToDone(env, { concurrency: 1 });
  assert.equal(rerun.body.done, true);
  assert.deepEqual(rerun.body.state.tallies, { checked: 2, verified: 1, pending: 0, not_verified: 0, expired: 0, skipped: 1 });
  assert.equal(sharedMap.get('temp:profile-root:record').rotationTempId, t2id);
  const rotations = [...sharedMap.values()].filter((v) => v && typeof v === 'object' && v.rotatesFrom === 'profile-root');
  assert.equal(rotations.length, 1);
  assert.equal(rotations[0].id, t2id);
  const o = await callWorker(env, 'GET', '/admin/grab-outcomes');
  assert.equal(o.body.outcomes.length, 2);
  assert.deepEqual(
    o.body.outcomes.map(({ next_temp, ...rest }) => rest),
    [
      { tick: 1, id: 'profile-root', outcome: 'verified', day: '2026-12-15', reason: 'already_verified' },
      { tick: 2, id: t2id, outcome: 'verified', day: '2026-12-15', reason: 'chain_holds' },
    ],
  );
  assert.deepEqual(o.body.outcomes[0].next_temp, { id: t2id, tick: 2 });
  assert.equal(o.body.outcomes[1].next_temp.id, sharedMap.get(`temp:${t2id}:record`).rotationTempId);
  // The root's queue entry is marked done:verified now.
  const idx = new TempIndex(namespacedState(sharedMap, 'temp:index:0'));
  const q = await callDo(idx, '/queue-range', { startTick: 1, endTick: 1 });
  assert.equal(q.body.entries[0].done, 'verified');
});

await check('POST /admin/rotate backfills a verified temp; idempotent; 400 when not verified; 404 when missing', async () => {
  setNow(T0);
  const sharedMap = new Map();
  // Genesis as it stands before rotation existed: verified, no
  // rotation, queue entry done (never re-enters the walk).
  const genesis = newTempRecord({ id: 'profile-genesis', referralId: 'ref:genesis', activationTick: 1, windowStart: new Date(T0 - DAY).toISOString(), createdAt: new Date(T0 - DAY).toISOString(), ownerUserId: 'user-abc' });
  const verified = { ...genesis, status: 'verified', verificationState: 'verified', verifiedTick: 1, grabDay: '2026-12-15' };
  sharedMap.set('temp:profile-genesis:record', verified);
  sharedMap.set('temp:index:0:q:0000000000000001', queueValue('profile-genesis', 'ref:genesis', 'verified'));
  const pending = newTempRecord({ id: 'profile-pending', referralId: 'profile-genesis', activationTick: 2, windowStart: new Date(T0 - DAY).toISOString(), createdAt: new Date(T0 - DAY).toISOString() });
  sharedMap.set('temp:profile-pending:record', pending);
  sharedMap.set('temp:index:0:q:0000000000000002', queueValue('profile-pending', 'profile-genesis'));
  sharedMap.set('grab:current:nextActivationTick', 3);
  const env = fakeEnv(sharedMap);
  // 404: no such temp. 400: pending, and bad bodies.
  assert.equal((await callWorker(env, 'POST', '/admin/rotate', { id: 'profile-nope' })).status, 404);
  assert.equal((await callWorker(env, 'POST', '/admin/rotate', { id: 'profile-pending' })).status, 400);
  assert.equal((await callWorker(env, 'POST', '/admin/rotate', {})).status, 400);
  assert.equal((await callWorker(env, 'POST', '/admin/rotate', { id: '' })).status, 400);
  // Backfill: creates the rotation, stores the pointer, enqueues it.
  const first = await callWorker(env, 'POST', '/admin/rotate', { id: 'profile-genesis', shardWidth: 100 });
  assert.equal(first.status, 200, JSON.stringify(first.body));
  assert.equal(first.body.ok, true);
  assert.equal(first.body.id, 'profile-genesis');
  assert.equal(first.body.created, true);
  assert.ok(first.body.next_temp.id.startsWith('profile-'));
  assert.equal(first.body.next_temp.tick, 3);
  const rot = sharedMap.get(`temp:${first.body.next_temp.id}:record`);
  assert.equal(rot.referralId, 'profile-genesis');
  assert.equal(rot.rotatesFrom, 'profile-genesis');
  assert.equal(rot.ownerUserId, 'user-abc');
  assert.equal(rot.verificationState, 'pending');
  assert.equal(sharedMap.get('temp:profile-genesis:record').rotationTempId, first.body.next_temp.id);
  const idx = new TempIndex(namespacedState(sharedMap, 'temp:index:0'));
  const q = await callDo(idx, '/queue-range', { startTick: 3, endTick: 3 });
  assert.equal(q.body.entries.length, 1);
  assert.equal(q.body.entries[0].id, first.body.next_temp.id);
  // Idempotent: the second call returns the same rotation, created false.
  const second = await callWorker(env, 'POST', '/admin/rotate', { id: 'profile-genesis', shardWidth: 100 });
  assert.equal(second.status, 200);
  assert.equal(second.body.created, false);
  assert.deepEqual(second.body.next_temp, first.body.next_temp);
  assert.equal(sharedMap.get('grab:current:nextActivationTick'), 4, 'no second tick consumed');
  // Admin key required when a secret is set.
  const envSecret = { ...fakeEnv(new Map()), PING_SHARED_SECRET: 'test-secret' };
  assert.equal((await callWorkerHeaders(envSecret, 'POST', '/admin/rotate', { id: 'profile-genesis' })).status, 401);
});

await check('/log-batch skip with nextTemp writes a verified log entry; skip without nextTemp writes nothing; bad nextTemp is a 400', async () => {
  const sharedMap = new Map();
  const index = new TempIndex(namespacedState(sharedMap, 'temp:index:0'));
  await callDo(index, '/enqueue', { activationTick: 1, id: 'profile-a', referralId: 'ref:genesis' });
  await callDo(index, '/enqueue', { activationTick: 2, id: 'profile-b', referralId: 'profile-a' });
  // A skip carrying nextTemp repairs the log as 'verified';
  // a skip without nextTemp writes nothing, as before.
  const r = await callDo(index, '/log-batch', { entries: [
    { tick: 1, id: 'profile-a', outcome: 'skip', referralId: 'ref:genesis', day: '2026-12-15', reason: 'already_verified', nextTemp: { id: 'profile-next', tick: 9 } },
    { tick: 2, id: 'profile-b', outcome: 'skip', referralId: 'profile-a' },
  ] });
  assert.equal(r.status, 200);
  assert.equal(r.body.logged, 1);
  assert.equal(r.body.marked, 2);
  const o = await callDo(index, '/outcomes');
  assert.deepEqual(o.body.entries, [
    { tick: 1, id: 'profile-a', outcome: 'verified', day: '2026-12-15', reason: 'already_verified', nextTemp: { id: 'profile-next', tick: 9 } },
  ]);
  // A bad nextTemp rejects the whole batch, nothing written.
  for (const badNext of [{ id: 'profile-d', tick: -1 }, { id: '', tick: 3 }, { id: 'profile-d', tick: 1.5 }, 'profile-d', { tick: 3 }]) {
    const bad = await callDo(index, '/log-batch', { entries: [
      { tick: 3, id: 'profile-c', outcome: 'verified', nextTemp: badNext },
    ] });
    assert.equal(bad.status, 400, `expected 400 for nextTemp ${JSON.stringify(badNext)}`);
  }
  // A verified entry WITH nextTemp stores it; without, null.
  const ok = await callDo(index, '/log-batch', { entries: [
    { tick: 3, id: 'profile-c', outcome: 'verified', day: '2026-12-15', reason: 'chain_holds', nextTemp: { id: 'profile-d', tick: 4 } },
    { tick: 4, id: 'profile-e', outcome: 'pending' },
  ] });
  assert.equal(ok.body.logged, 2);
  const o2 = await callDo(index, '/outcomes');
  assert.deepEqual(o2.body.entries[1], { tick: 3, id: 'profile-c', outcome: 'verified', day: '2026-12-15', reason: 'chain_holds', nextTemp: { id: 'profile-d', tick: 4 } });
  assert.equal(o2.body.entries[2].nextTemp, null);
});

Date.now = realNow;

console.log(`\n${passed} grab tests passed, 0 failed.`);
