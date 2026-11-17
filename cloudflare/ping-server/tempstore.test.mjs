// Unit tests for the temp store (tempstore.js pure logic + worker.js
// TempRecord / TempIndex DO classes) — the real DO classes, driven
// with fake storage and a faked clock. No network, no wrangler.
// Run: node tempstore.test.mjs   (Node >= 18, no dependencies.)
//
// These prove the spec's step-1 shape end to end at the DO level:
// record validation, the §1.2 chain check (verified / pending /
// not_verified / expired / skip), apply-once stamping (a verified
// tick is never re-numbered), the index queue in tick order, and
// the outcome log as the causal record. The Worker routes that
// drive these DOs come in plan step 2 (the grab); this file tests
// the DOs directly, as serverUsage.test.mjs does for PingServerUsage.

import assert from 'node:assert/strict';
import { TempIndex, TempRecord } from './worker.js';
import {
  GENESIS_REFERRAL_ID,
  GENESIS_ROOT_TICK,
  applyOutcome,
  checkChain,
  genesisReferrerState,
  isTerminalOutcome,
  newActivationRecord,
  newTempRecord,
  outcomeKey,
  outcomeValue,
  parseOutcomeKey,
  parseOutcomeValue,
  parseQueueKey,
  parseQueueValue,
  queueKey,
  queueValue,
  utcDay,
  validateTempRecord,
} from './tempstore.js';

const H = 3600 * 1000;
const DAY = 24 * H;
const YEAR = 365 * DAY;
// The grab moment: 12:00 AM America/Vancouver. BC is on
// permanent Pacific time (PCT, UTC-7) from 1 Nov 2026 — no
// fall-back — so 12am Gary's time is 07:00 UTC year-round
// (tzdata 2026b+).
const T0 = Date.UTC(2026, 11, 15, 7, 0, 0);

let passed = 0;
async function check(name, fn) {
  await fn();
  passed += 1;
  console.log(`ok - ${name}`);
}

// --- fake DO storage (Map-backed, same get/put/list shape as the real API) ---
// list({ prefix, start, end, limit }) returns a Map of matching
// keys, sorted lexicographically — the real storage.list()
// order. start is inclusive, end exclusive, limit caps the
// page; the grab's /queue-range depends on all three.
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

// Per-stub namespaced storage over one shared Map — the same shape
// the scan harness uses: each TempRecord stub owns its keys
// (`temp:<id>:record`), so many stubs share one Map without ever
// colliding. This is what idFromName('temp:' + id).get() gives each
// stub in production: its own key space.
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

// --- fake clock ---
let nowMs = T0;
const realNow = Date.now;
Date.now = () => nowMs;
const setNow = (ms) => {
  nowMs = ms;
};

async function call(doInstance, path, body) {
  const req = new Request(`http://temp${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  const res = await doInstance.fetch(req);
  return { status: res.status, body: await res.json() };
}

function baseRecord(overrides = {}) {
  return newTempRecord({
    id: 'profile-00000000-0000-4000-8000-000000000001',
    referralId: 'profile-00000000-0000-4000-8000-000000000000',
    activationTick: 1,
    windowStart: new Date(T0 - 30 * DAY).toISOString(),
    createdAt: new Date(T0 - 30 * DAY).toISOString(),
    ...overrides,
  });
}

// --- pure logic: record shape ---

await check('newTempRecord builds the spec §3.2 shape with a 1-year window', async () => {
  const r = baseRecord();
  assert.equal(r.id, 'profile-00000000-0000-4000-8000-000000000001');
  assert.equal(r.status, 'temp');
  assert.equal(r.verificationState, 'pending');
  assert.equal(r.verifiedTick, null);
  assert.equal(r.grabDay, null);
  assert.equal(r.discarded, false);
  assert.equal(r.windowEnd, new Date(T0 - 30 * DAY + YEAR).toISOString());
  assert.equal(validateTempRecord(r).ok, true);
});

await check('validateTempRecord rejects a bad id, status, tick, window, and verified-without-stamp', async () => {
  assert.equal(validateTempRecord({ ...baseRecord(), id: '' }).ok, false);
  assert.equal(validateTempRecord({ ...baseRecord(), status: 'banana' }).ok, false);
  assert.equal(validateTempRecord({ ...baseRecord(), activationTick: -1 }).ok, false);
  assert.equal(validateTempRecord({ ...baseRecord(), activationTick: 1.5 }).ok, false);
  assert.equal(
    validateTempRecord({ ...baseRecord(), windowEnd: baseRecord().windowStart }).ok,
    false,
  );
  assert.equal(
    validateTempRecord({ ...baseRecord(), verificationState: 'verified', verifiedTick: null }).ok,
    false,
  );
  assert.equal(
    validateTempRecord({ ...baseRecord(), verificationState: 'pending', verifiedTick: 7 }).ok,
    false,
  );
  // Unknown extra fields are dropped, the shape survives.
  const v = validateTempRecord({ ...baseRecord(), surprise: 'x' });
  assert.equal(v.ok, true);
  assert.equal('surprise' in v.record, false);
});

// --- pure logic: the chain check (spec §1.2) ---

await check('checkChain verifies when the chain holds (referrer verified)', async () => {
  assert.deepEqual(checkChain(baseRecord(), T0, 'verified'), {
    outcome: 'verified',
    reason: 'chain_holds',
  });
});

await check('checkChain skips an already-verified record (never re-verify, never re-number)', async () => {
  const r = { ...baseRecord(), verificationState: 'verified', verifiedTick: 5, grabDay: '2026-12-14' };
  assert.deepEqual(checkChain(r, T0, 'verified'), { outcome: 'skip', reason: 'already_verified' });
});

await check('checkChain expires a discarded temp and a temp past its window', async () => {
  assert.deepEqual(checkChain({ ...baseRecord(), discarded: true }, T0, 'verified'), {
    outcome: 'expired',
    reason: 'discarded',
  });
  assert.deepEqual(checkChain(baseRecord(), Date.parse(baseRecord().windowEnd) + 1, 'verified'), {
    outcome: 'expired',
    reason: 'window_expired',
  });
  // Exactly at windowEnd is still inside the window (now <= windowEnd).
  assert.equal(checkChain(baseRecord(), Date.parse(baseRecord().windowEnd), 'verified').outcome, 'verified');
});

await check('checkChain rejects a missing referral and a broken referral link', async () => {
  assert.deepEqual(checkChain({ ...baseRecord(), referralId: null }, T0, null), {
    outcome: 'not_verified',
    reason: 'no_referral',
  });
  assert.deepEqual(checkChain(baseRecord(), T0, 'missing'), {
    outcome: 'not_verified',
    reason: 'referral_broken',
  });
});

await check('checkChain pends a temp whose referrer is not yet verified', async () => {
  assert.deepEqual(checkChain(baseRecord(), T0, 'pending'), {
    outcome: 'pending',
    reason: 'referrer_pending',
  });
  assert.deepEqual(checkChain(baseRecord(), T0, 'not_verified'), {
    outcome: 'pending',
    reason: 'referrer_pending',
  });
});

// --- pure logic: applying outcomes ---

await check('applyOutcome stamps verifiedTick/grabDay once and never re-numbers', async () => {
  const r = baseRecord();
  const v = applyOutcome(r, 'verified', 42, utcDay(T0));
  assert.equal(v.verificationState, 'verified');
  assert.equal(v.verifiedTick, 42);
  assert.equal(v.grabDay, '2026-12-15');
  assert.equal(v.status, 'verified');
  // A second apply (e.g. a re-run) leaves the stamp untouched.
  const v2 = applyOutcome(v, 'verified', 99, utcDay(T0 + DAY));
  assert.equal(v2.verifiedTick, 42);
  assert.equal(v2.grabDay, '2026-12-15');
  // The input is untouched (pure function).
  assert.equal(r.verificationState, 'pending');
  assert.equal(r.verifiedTick, null);
});

await check('applyOutcome maps expired to the not_verified lookup state (spec §2 has three states)', async () => {
  const e = applyOutcome(baseRecord(), 'expired', 42, utcDay(T0));
  assert.equal(e.verificationState, 'not_verified');
  assert.equal(e.verifiedTick, null);
  const p = applyOutcome(baseRecord(), 'pending', 42, utcDay(T0));
  assert.equal(p.verificationState, 'pending');
  assert.equal(p.verifiedTick, null);
  const s = applyOutcome(baseRecord(), 'skip', 42, utcDay(T0));
  assert.deepEqual(s, baseRecord());
});

// --- pure logic: index keys ---

await check('queueKey zero-pads so lexicographic order IS tick order', async () => {
  assert.equal(queueKey(1), 'q:0000000000000001');
  assert.equal(queueKey(1000000), 'q:0000000001000000');
  assert.equal(parseQueueKey('q:0000000000000001'), 1);
  assert.equal(parseQueueKey('q:1'), null);
  const keys = [queueKey(10), queueKey(2), queueKey(1000000), queueKey(1)].sort();
  assert.deepEqual(keys.map(parseQueueKey), [1, 2, 10, 1000000]);
  assert.deepEqual(parseOutcomeKey(outcomeKey(42, 'profile-x')), { tick: 42, id: 'profile-x' });
});

// --- TempRecord DO ---

await check('TempRecord /get on a fresh DO returns null and creates no state', async () => {
  const d = new TempRecord(fakeState());
  const r = await call(d, '/get');
  assert.equal(r.status, 200);
  assert.equal(r.body.record, null);
});

await check('TempRecord /put then /get round-trips the record; bad record is a 400', async () => {
  const state = fakeState();
  const d = new TempRecord(state);
  const bad = await call(d, '/put', { record: { ...baseRecord(), status: 'banana' } });
  assert.equal(bad.status, 400);
  assert.equal(bad.body.ok, false);
  const put = await call(d, '/put', { record: baseRecord() });
  assert.equal(put.status, 200);
  assert.equal(put.body.record.id, baseRecord().id);
  // A new DO instance over the same storage sees the persisted record.
  const d2 = new TempRecord(state);
  const got = await call(d2, '/get');
  assert.equal(got.body.record.verificationState, 'pending');
});

await check('TempRecord /apply checks and persists; a second apply skips, stamp unchanged', async () => {
  setNow(T0);
  const d = new TempRecord(fakeState());
  await call(d, '/put', { record: baseRecord() });
  const a1 = await call(d, '/apply', {
    nowMs: T0,
    referrerState: 'verified',
    tick: 42,
    grabDay: utcDay(T0),
  });
  assert.equal(a1.status, 200);
  assert.equal(a1.body.outcome, 'verified');
  assert.equal(a1.body.record.verifiedTick, 42);
  const a2 = await call(d, '/apply', {
    nowMs: T0,
    referrerState: 'verified',
    tick: 99,
    grabDay: utcDay(T0),
  });
  assert.equal(a2.body.outcome, 'skip');
  assert.equal(a2.body.record.verifiedTick, 42);
});

await check('TempRecord /apply on an empty DO is a 404; unknown route is a 404', async () => {
  const d = new TempRecord(fakeState());
  const r = await call(d, '/apply', { nowMs: T0, referrerState: 'verified', tick: 1, grabDay: '2026-12-15' });
  assert.equal(r.status, 404);
  const u = await call(d, '/nope');
  assert.equal(u.status, 404);
});

// --- TempIndex DO ---

await check('TempIndex /queue returns entries in tick order even when enqueued out of order', async () => {
  const d = new TempIndex(fakeState());
  await call(d, '/enqueue', { activationTick: 10, id: 'profile-c', referralId: 'profile-b' });
  await call(d, '/enqueue', { activationTick: 2, id: 'profile-a' });
  await call(d, '/enqueue', { activationTick: 1000000, id: 'profile-d', referralId: null });
  await call(d, '/enqueue', { activationTick: 3, id: 'profile-b', referralId: 'profile-a' });
  const q = await call(d, '/queue');
  assert.equal(q.status, 200);
  assert.deepEqual(q.body.entries, [
    { activationTick: 2, id: 'profile-a', referralId: null, done: null },
    { activationTick: 3, id: 'profile-b', referralId: 'profile-a', done: null },
    { activationTick: 10, id: 'profile-c', referralId: 'profile-b', done: null },
    { activationTick: 1000000, id: 'profile-d', referralId: null, done: null },
  ]);
  const bad = await call(d, '/enqueue', { activationTick: -1, id: 'x' });
  assert.equal(bad.status, 400);
});

await check('TempIndex /queue-range pages in tick order; /log-batch writes idempotently', async () => {
  const d = new TempIndex(fakeState());
  for (let tick = 1; tick <= 25; tick++) {
    await call(d, '/enqueue', { activationTick: tick, id: `profile-${tick}`, referralId: tick > 1 ? `profile-${tick - 1}` : 'ref:genesis' });
  }
  const p1 = await call(d, '/queue-range', { startTick: 1, endTick: 25, limit: 10 });
  assert.equal(p1.status, 200);
  assert.equal(p1.body.entries.length, 10);
  assert.deepEqual(p1.body.entries.map((e) => e.activationTick), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  assert.equal(p1.body.entries[1].referralId, 'profile-1');
  const p2 = await call(d, '/queue-range', { startTick: 11, endTick: 25, limit: 10 });
  assert.deepEqual(p2.body.entries.map((e) => e.activationTick), [11, 12, 13, 14, 15, 16, 17, 18, 19, 20]);
  const p3 = await call(d, '/queue-range', { startTick: 21, endTick: 25, limit: 10 });
  assert.equal(p3.body.entries.length, 5);
  // A range past the end is empty, not an error.
  const p4 = await call(d, '/queue-range', { startTick: 100, endTick: 200, limit: 10 });
  assert.deepEqual(p4.body.entries, []);
  // limit is capped at GRAB_QUEUE_PAGE; bad ranges are 400s.
  const badLimit = await call(d, '/queue-range', { startTick: 1, endTick: 25, limit: 10001 });
  assert.equal(badLimit.status, 400);
  const badRange = await call(d, '/queue-range', { startTick: 10, endTick: 5, limit: 10 });
  assert.equal(badRange.status, 400);
  // /log-batch: one call for many outcomes; a bad entry rejects
  // the whole batch; a re-log overwrites the same keys (idempotent).
  const batch = await call(d, '/log-batch', {
    entries: [
      { tick: 1, id: 'profile-1', outcome: 'verified' },
      { tick: 2, id: 'profile-2', outcome: 'pending' },
    ],
  });
  assert.equal(batch.status, 200);
  assert.equal(batch.body.logged, 2);
  // 'skip' is now ACCEPTED by /log-batch (marking-only): a skipped
  // record was already verified, so its queue entry is marked
  // done:verified and nothing is written to the outcome log.
  const skipBatch = await call(d, '/log-batch', {
    entries: [{ tick: 3, id: 'profile-3', outcome: 'skip' }],
  });
  assert.equal(skipBatch.status, 200);
  assert.equal(skipBatch.body.logged, 0);
  assert.equal(skipBatch.body.marked, 1);
  const badBatch = await call(d, '/log-batch', {
    entries: [{ tick: 4, id: 'profile-4', outcome: 'bogus' }],
  });
  assert.equal(badBatch.status, 400);
  const relog = await call(d, '/log-batch', {
    entries: [{ tick: 1, id: 'profile-1', outcome: 'verified' }],
  });
  assert.equal(relog.status, 200);
  const s = await call(d, '/status');
  assert.equal(s.body.queued, 25);
  assert.equal(s.body.logged, 2);
  // Done markers: tick 1 (verified, from the re-log) + tick 3 (skip).
  assert.equal(s.body.done, 2);
});

await check('TempIndex /log + /outcomes keep the causal record in tick order; skip is rejected', async () => {
  const d = new TempIndex(fakeState());
  await call(d, '/log', { tick: 42, id: 'profile-a', outcome: 'verified' });
  await call(d, '/log', { tick: 42, id: 'profile-b', outcome: 'pending' });
  await call(d, '/log', { tick: 43, id: 'profile-c', outcome: 'expired' });
  const bad = await call(d, '/log', { tick: 43, id: 'profile-d', outcome: 'skip' });
  assert.equal(bad.status, 400);
  const o = await call(d, '/outcomes');
  // Entries logged without day/reason read back null for both
  // (the legacy plain-outcome shape).
  assert.deepEqual(o.body.entries, [
    { tick: 42, id: 'profile-a', outcome: 'verified', day: null, reason: null },
    { tick: 42, id: 'profile-b', outcome: 'pending', day: null, reason: null },
    { tick: 43, id: 'profile-c', outcome: 'expired', day: null, reason: null },
  ]);
  // Day + reason ride the log when supplied.
  await call(d, '/log', { tick: 44, id: 'profile-e', outcome: 'verified', day: '2026-11-15', reason: 'genesis_root' });
  const o2 = await call(d, '/outcomes');
  assert.deepEqual(o2.body.entries[3], { tick: 44, id: 'profile-e', outcome: 'verified', day: '2026-11-15', reason: 'genesis_root' });
  const s = await call(d, '/status');
  assert.equal(s.body.queued, 0);
  assert.equal(s.body.logged, 4); // 3 plain + the day/reason entry above
});

// --- end to end: queue order in, recognition order out ---

await check('tick order end to end: queue in, outcomes out, verified ticks monotonic', async () => {
  setNow(T0);
  const sharedMap = new Map();
  const recordStub = (id) => new TempRecord(namespacedState(sharedMap, `temp:${id}`));
  const index = new TempIndex(namespacedState(sharedMap, 'temp:index'));
  const ids = ['profile-1', 'profile-2', 'profile-3'];
  // Enqueue out of order; records reference the previous temp as referrer.
  for (const [tick, id, ref] of [
    [3, 'profile-3', 'profile-2'],
    [1, 'profile-1', 'ref:genesis'],
    [2, 'profile-2', 'profile-1'],
  ]) {
    const rec = recordStub(id);
    await call(rec, '/put', {
      record: baseRecord({ id, referralId: ref, activationTick: tick }),
    });
    await call(index, '/enqueue', { activationTick: tick, id, referralId: ref });
  }
  // Walk the queue in tick order; the referrer of each is the
  // previous temp, verified in this same pass (genesis counts
  // as verified by definition).
  const verified = new Set(['ref:genesis']);
  const q = await call(index, '/queue');
  for (const { activationTick, id } of q.body.entries) {
    const rec = recordStub(id);
    const got = await call(rec, '/get');
    assert.equal(got.body.record.id, id);
    const refState = verified.has(got.body.record.referralId) ? 'verified' : 'pending';
    const applied = await call(rec, '/apply', {
      nowMs: T0,
      referrerState: refState,
      tick: activationTick,
      grabDay: utcDay(T0),
    });
    assert.equal(applied.body.outcome, 'verified');
    await call(index, '/log', { tick: activationTick, id, outcome: applied.body.outcome });
    verified.add(id);
  }
  const o = await call(index, '/outcomes');
  assert.deepEqual(
    o.body.entries.map((e) => e.tick),
    [1, 2, 3],
  );
  assert.deepEqual(
    o.body.entries.map((e) => e.outcome),
    ['verified', 'verified', 'verified'],
  );
});

// --- discard: the done marker on queue values ---

await check('isTerminalOutcome: verified/not_verified/expired terminal, pending and skip are not', async () => {
  assert.equal(isTerminalOutcome('verified'), true);
  assert.equal(isTerminalOutcome('not_verified'), true);
  assert.equal(isTerminalOutcome('expired'), true);
  assert.equal(isTerminalOutcome('pending'), false);
  assert.equal(isTerminalOutcome('skip'), false);
  assert.equal(isTerminalOutcome('bogus'), false);
});

await check('queueValue/parseQueueValue: done marker round-trips for every terminal outcome', async () => {
  for (const outcome of ['verified', 'not_verified', 'expired']) {
    assert.equal(queueValue('profile-a', 'profile-b', outcome), `profile-a|profile-b|done:${outcome}`);
    assert.deepEqual(parseQueueValue(`profile-a|profile-b|done:${outcome}`), { id: 'profile-a', referralId: 'profile-b', done: outcome });
    // Null referral keeps its empty slot under the marker.
    assert.equal(queueValue('profile-a', null, outcome), `profile-a||done:${outcome}`);
    assert.deepEqual(parseQueueValue(`profile-a||done:${outcome}`), { id: 'profile-a', referralId: null, done: outcome });
  }
  // No marker = live entry, done null.
  assert.equal(queueValue('profile-a', 'profile-b'), 'profile-a|profile-b');
  assert.deepEqual(parseQueueValue('profile-a|profile-b'), { id: 'profile-a', referralId: 'profile-b', done: null });
  // A done marker for a non-terminal outcome is malformed.
  assert.equal(parseQueueValue('profile-a|profile-b|done:pending'), null);
  assert.equal(parseQueueValue('profile-a|profile-b|done:skip'), null);
  assert.equal(parseQueueValue('profile-a|profile-b|done:bogus'), null);
  assert.equal(parseQueueValue('profile-a|profile-b|done:verified|extra'), null);
});

// --- yield intake: the activation record builder ---

await check('newActivationRecord: server-side shape — pending, window now + 1 year, no stamp', async () => {
  const rec = newActivationRecord({ id: 'profile-x', referralId: 'profile-y', activationTick: 7, nowMs: T0 });
  assert.equal(rec.id, 'profile-x');
  assert.equal(rec.referralId, 'profile-y');
  assert.equal(rec.status, 'temp');
  assert.equal(rec.activationTick, 7);
  assert.equal(rec.windowStart, new Date(T0).toISOString());
  assert.equal(rec.windowEnd, new Date(T0 + YEAR).toISOString());
  assert.equal(rec.verificationState, 'pending');
  assert.equal(rec.verifiedTick, null);
  assert.equal(rec.grabDay, null);
  assert.equal(rec.discarded, false);
  assert.equal(rec.createdAt, new Date(T0).toISOString());
  assert.equal(validateTempRecord(rec).ok, true);
  // No referral is fine — the grab will mark it not_verified.
  const noRef = newActivationRecord({ id: 'profile-x', activationTick: 8, nowMs: T0 });
  assert.equal(noRef.referralId, null);
  assert.equal(validateTempRecord(noRef).ok, true);
  // An explicit windowStart wins over nowMs.
  const dated = newActivationRecord({ id: 'profile-x', activationTick: 9, windowStart: '2026-01-01T00:00:00.000Z', nowMs: T0 });
  assert.equal(dated.windowStart, '2026-01-01T00:00:00.000Z');
  assert.equal(dated.windowEnd, '2027-01-01T00:00:00.000Z');
});

// --- genesis (the first verification) ---
await check('genesis: the referral id and root tick constants are the deployed values', () => {
  assert.equal(GENESIS_REFERRAL_ID, 'ref:genesis');
  assert.equal(GENESIS_ROOT_TICK, 1);
});
await check('genesisReferrerState: genesis + tick 1 is the root; any later tick is not', () => {
  assert.equal(genesisReferrerState('ref:genesis', 1), 'genesis');
  assert.equal(genesisReferrerState('ref:genesis', 2), 'genesis_not_root');
  assert.equal(genesisReferrerState('ref:genesis', 0), 'genesis_not_root');
  assert.equal(genesisReferrerState('profile-abc', 1), null);
  assert.equal(genesisReferrerState(null, 1), null);
});
await check('checkChain: the genesis root verifies (reason genesis_root); a later genesis claim does not', () => {
  const root = newTempRecord({ id: 'profile-root', referralId: 'ref:genesis', activationTick: 1, windowStart: new Date(T0).toISOString() });
  assert.deepEqual(checkChain(root, T0 + 1000, 'genesis'), { outcome: 'verified', reason: 'genesis_root' });
  const fake = newTempRecord({ id: 'profile-fake', referralId: 'ref:genesis', activationTick: 2, windowStart: new Date(T0).toISOString() });
  assert.deepEqual(checkChain(fake, T0 + 1000, 'genesis_not_root'), { outcome: 'not_verified', reason: 'genesis_not_root' });
  // A referral-less temp still never verifies silently.
  const lone = newTempRecord({ id: 'profile-lone', referralId: null, activationTick: 3, windowStart: new Date(T0).toISOString() });
  assert.deepEqual(checkChain(lone, T0 + 1000, null), { outcome: 'not_verified', reason: 'no_referral' });
});
await check('owner binding: newTempRecord carries ownerUserId; validateTempRecord accepts it and rejects a non-string', () => {
  const owned = newTempRecord({ id: 'profile-x', referralId: 'profile-y', activationTick: 5, windowStart: new Date(T0).toISOString(), ownerUserId: 'user-abc' });
  assert.equal(owned.ownerUserId, 'user-abc');
  assert.equal(validateTempRecord(owned).ok, true);
  const unowned = newTempRecord({ id: 'profile-x', referralId: 'profile-y', activationTick: 5, windowStart: new Date(T0).toISOString() });
  assert.equal(unowned.ownerUserId, null);
  assert.equal(validateTempRecord(unowned).ok, true);
  const bad = { ...owned, ownerUserId: 42 };
  assert.equal(validateTempRecord(bad).ok, false);
  const activated = newActivationRecord({ id: 'profile-x', activationTick: 6, nowMs: T0, ownerUserId: 'user-abc' });
  assert.equal(activated.ownerUserId, 'user-abc');
  assert.equal(validateTempRecord(activated).ok, true);
});
await check('outcomeValue/parseOutcomeValue: JSON round-trips day + reason; legacy plain strings still read', () => {
  const v = outcomeValue('verified', '2026-11-16', 'genesis_root');
  assert.deepEqual(parseOutcomeValue(v), { outcome: 'verified', day: '2026-11-16', reason: 'genesis_root' });
  assert.deepEqual(parseOutcomeValue(outcomeValue('pending', null, null)), { outcome: 'pending', day: null, reason: null });
  // Legacy plain-outcome values (written by 0.6.0) read as outcome-only.
  assert.deepEqual(parseOutcomeValue('verified'), { outcome: 'verified', day: null, reason: null });
  assert.deepEqual(parseOutcomeValue('not_verified'), { outcome: 'not_verified', day: null, reason: null });
  // Garbage is never an outcome.
  assert.deepEqual(parseOutcomeValue('bogus'), { outcome: null, day: null, reason: null });
  assert.deepEqual(parseOutcomeValue('{"o":"bogus","d":"2026-11-16","r":"x"}'), { outcome: null, day: '2026-11-16', reason: 'x' });
  assert.deepEqual(parseOutcomeValue(null), { outcome: null, day: null, reason: null });
});

Date.now = realNow;

console.log(`\n${passed} temp-store tests passed, 0 failed.`);
