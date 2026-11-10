// Unit tests for the server-usage Durable Object (worker.js
// PingServerUsage) — the real DO class, driven with fake storage
// and a faked clock. No network, no wrangler.
// Run: node serverUsage.test.mjs   (Node >= 18, no dependencies.)
//
// These prove the maintenance mode end to end at the DO level:
// record -> trip at a cap -> status reports maintenance -> expiry
// after 24h -> day rollover keeps an active window but resets the
// counters. The Worker routes (/status, /record, /trip) are the
// only entry points; the pure math is pinned in
// maintenance.test.mjs.

import assert from 'node:assert/strict';
import { PingServerUsage } from './worker.js';

const H = 3600 * 1000;
const T0 = Date.UTC(2026, 11, 7, 12, 0, 0); // a fixed "now" (ms)

let passed = 0;
function check(name, fn) {
  return (async () => {
    await fn();
    passed += 1;
    console.log(`ok - ${name}`);
  })();
}

// --- fake DO storage (Map-backed, same get/put shape) ---
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
    },
  };
}

// --- fake clock: Date.now() returns the controllable value ---
let nowMs = T0;
const realNow = Date.now;
Date.now = () => nowMs;
const setNow = (ms) => {
  nowMs = ms;
};

async function call(doInstance, path, body) {
  const req = new Request(`http://usage${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  const res = await doInstance.fetch(req);
  return { status: res.status, body: await res.json() };
}

await check('status on a fresh DO: no maintenance, zero counters, no state created', async () => {
  setNow(T0);
  const d = new PingServerUsage(fakeState());
  const r = await call(d, '/status');
  assert.equal(r.status, 200);
  assert.equal(r.body.ok, true);
  assert.equal(r.body.maintenance, null);
  assert.equal(r.body.requests, 0);
  assert.equal(r.body.neurons, 0);
  assert.equal(r.body.day, '2026-12-07');
});

await check('record increments and persists across DO instances (same storage)', async () => {
  setNow(T0);
  const state = fakeState();
  const d1 = new PingServerUsage(state);
  const r1 = await call(d1, '/record', { neurons: 2.5 });
  assert.equal(r1.body.tripped, false);
  assert.equal(r1.body.requests, 1);
  assert.equal(r1.body.neurons, 2.5);
  // A new DO instance over the same storage sees the persisted counters.
  const d2 = new PingServerUsage(state);
  const r2 = await call(d2, '/status');
  assert.equal(r2.body.requests, 1);
  assert.equal(r2.body.neurons, 2.5);
  const r3 = await call(d2, '/record', { neurons: 0 });
  assert.equal(r3.body.requests, 2);
});

await check('record trips maintenance at the neuron cap; status reports the 24h window', async () => {
  setNow(T0);
  const d = new PingServerUsage(fakeState());
  await call(d, '/record', { neurons: 9999 });
  const r = await call(d, '/record', { neurons: 1 });
  assert.equal(r.status, 200);
  assert.equal(r.body.tripped, true);
  assert.equal(r.body.reason, 'neurons_exhausted');
  assert.equal(r.body.maintenance.active, true);
  assert.equal(r.body.maintenance.reason, 'neurons_exhausted');
  assert.equal(r.body.maintenance.started_at, new Date(T0).toISOString());
  assert.equal(r.body.maintenance.back_at, new Date(T0 + 24 * H).toISOString());
  assert.equal(r.body.maintenance.back_in_seconds, 24 * 3600);
  // Status agrees.
  const s = await call(d, '/status');
  assert.equal(s.body.maintenance.active, true);
  assert.equal(s.body.maintenance.back_in_seconds, 24 * 3600);
});

await check('record trips maintenance at the request cap', async () => {
  setNow(T0);
  const d = new PingServerUsage(fakeState());
  // Seed 99,999 requests just under the cap, then one more.
  const state = fakeState();
  const d2 = new PingServerUsage(state);
  // Directly seed the stored record (same shape the DO persists).
  await state.storage.put('usage', {
    day: '2026-12-07',
    requests: 99999,
    neurons: 5,
    maintenance: null,
  });
  const r = await call(d2, '/record', { neurons: 0 });
  assert.equal(r.body.tripped, true);
  assert.equal(r.body.reason, 'requests_exhausted');
  assert.equal(r.body.requests, 100000);
});

await check('trip sets maintenance immediately; a second trip keeps the original window', async () => {
  setNow(T0);
  const d = new PingServerUsage(fakeState());
  const r1 = await call(d, '/trip', { reason: 'neurons_exhausted', detail: 'platform said so' });
  assert.equal(r1.status, 200);
  assert.equal(r1.body.maintenance.active, true);
  assert.equal(r1.body.maintenance.reason_detail, 'platform said so');
  assert.equal(r1.body.maintenance.started_at, new Date(T0).toISOString());
  setNow(T0 + 2 * H);
  const r2 = await call(d, '/trip', { reason: 'requests_exhausted', detail: 'second' });
  assert.equal(r2.body.maintenance.started_at, new Date(T0).toISOString());
  assert.equal(r2.body.maintenance.reason, 'neurons_exhausted');
  assert.equal(r2.body.maintenance.back_in_seconds, 22 * 3600);
});

await check('status after 24h shows maintenance inactive (expiry is time-derived)', async () => {
  setNow(T0);
  const d = new PingServerUsage(fakeState());
  await call(d, '/trip', { reason: 'neurons_exhausted', detail: 'x' });
  setNow(T0 + 23 * H + 59 * 60 * 1000);
  const still = await call(d, '/status');
  assert.equal(still.body.maintenance.active, true);
  assert.equal(still.body.maintenance.back_in_seconds, 60);
  setNow(T0 + 24 * H);
  const gone = await call(d, '/status');
  assert.equal(gone.body.maintenance, null);
});

await check('day rollover resets counters but an active window survives it', async () => {
  setNow(T0); // 12:00 UTC
  const d = new PingServerUsage(fakeState());
  await call(d, '/record', { neurons: 500 });
  await call(d, '/trip', { reason: 'neurons_exhausted', detail: 'x' });
  setNow(T0 + 13 * H); // 01:00 next UTC day, window has 11h left
  const s = await call(d, '/status');
  assert.equal(s.body.day, '2026-12-08');
  assert.equal(s.body.requests, 0);
  assert.equal(s.body.neurons, 0);
  assert.equal(s.body.maintenance.active, true);
  assert.equal(s.body.maintenance.back_in_seconds, 11 * 3600);
});

await check('record with bad/missing neurons counts the request as 0 neurons, never crashes', async () => {
  setNow(T0);
  const d = new PingServerUsage(fakeState());
  for (const body of [undefined, {}, { neurons: 'x' }, { neurons: -5 }, { neurons: null }]) {
    const r = await call(d, '/record', body);
    assert.equal(r.status, 200);
    assert.equal(r.body.tripped, false);
  }
  const s = await call(d, '/status');
  assert.equal(s.body.requests, 5);
  assert.equal(s.body.neurons, 0);
});

await check('unknown usage route is a 404', async () => {
  setNow(T0);
  const d = new PingServerUsage(fakeState());
  const r = await call(d, '/nope');
  assert.equal(r.status, 404);
  assert.equal(r.body.ok, false);
});

Date.now = realNow;

console.log(`\n${passed} server-usage DO tests passed, 0 failed.`);
