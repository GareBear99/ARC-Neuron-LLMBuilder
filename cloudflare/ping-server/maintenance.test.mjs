// Unit tests for the 24-hour maintenance mode (maintenance.js) —
// pure cap tracking, no network, no wrangler.
// Run: node maintenance.test.mjs   (Node >= 18, no dependencies.)
// Gary's rule (2026-11-07): if a server-side cap is ever hit
// (neurons maxed out, Workers request limit hit), the server goes
// down for 24 hours for maintenance. Every case below is
// hand-checkable; the numbers are the spec.

import assert from 'node:assert/strict';
import {
  CHARS_PER_TOKEN,
  MAINTENANCE_MS,
  MAINTENANCE_REASONS,
  NEURONS_PER_M_INPUT,
  NEURONS_PER_M_OUTPUT,
  NEURON_DAILY_CAP,
  REQUEST_DAILY_CAP,
  estimateNeurons,
  estimateTokensFromChars,
  isMaintenanceActive,
  maintenanceResponseBody,
  maintenanceView,
  migrateServerRecord,
  neuronsForRequest,
  neuronsForTokens,
  neuronsFromUsage,
  newServerState,
  recordUsage,
  rollDay,
  tripMaintenance,
  utcDay,
} from './maintenance.js';

const H = 3600 * 1000;
const T0 = Date.UTC(2026, 11, 7, 12, 0, 0); // a fixed "now" (ms)

let passed = 0;
function check(name, fn) {
  fn();
  passed += 1;
  console.log(`ok - ${name}`);
}

// --- constants: Gary's caps, unchanged ---
check('constants are Gary\'s caps: 10,000 neurons/day, 100,000 requests/day, 24h window', () => {
  assert.equal(NEURON_DAILY_CAP, 10000);
  assert.equal(REQUEST_DAILY_CAP, 100000);
  assert.equal(MAINTENANCE_MS, 24 * H);
  assert.equal(NEURONS_PER_M_INPUT, 2457);
  assert.equal(NEURONS_PER_M_OUTPUT, 18252);
  assert.equal(CHARS_PER_TOKEN, 4);
  assert.deepEqual([...MAINTENANCE_REASONS], ['neurons_exhausted', 'requests_exhausted']);
});

// --- token / neuron estimation ---
check('estimateTokensFromChars: 0 -> 0, 4 -> 1, 5 -> 2, 400 -> 100', () => {
  assert.equal(estimateTokensFromChars(0), 0);
  assert.equal(estimateTokensFromChars(1), 1);
  assert.equal(estimateTokensFromChars(4), 1);
  assert.equal(estimateTokensFromChars(5), 2);
  assert.equal(estimateTokensFromChars(400), 100);
});

check('neuronsForTokens: 1M in = 2,457; 1M out = 18,252; scales linearly', () => {
  assert.equal(neuronsForTokens(1e6, 0), 2457);
  assert.equal(neuronsForTokens(0, 1e6), 18252);
  assert.equal(neuronsForTokens(1e6, 1e6), 2457 + 18252);
  assert.equal(neuronsForTokens(20, 50), (20 / 1e6) * 2457 + (50 / 1e6) * 18252);
});

check('estimateNeurons: empty -> 0; short message is a fraction of a neuron', () => {
  assert.equal(estimateNeurons(0, 0), 0);
  // 40 input chars (10 tokens) + 200 output chars (50 tokens).
  const n = estimateNeurons(40, 200);
  assert.equal(n, (10 / 1e6) * 2457 + (50 / 1e6) * 18252);
  assert.ok(n > 0 && n < 1, `short message should cost < 1 neuron, got ${n}`);
});

check('neuronsFromUsage: valid usage is exact; missing/invalid -> null', () => {
  assert.equal(
    neuronsFromUsage({ prompt_tokens: 1000, completion_tokens: 2000 }),
    (1000 / 1e6) * 2457 + (2000 / 1e6) * 18252,
  );
  assert.equal(neuronsFromUsage(null), null);
  assert.equal(neuronsFromUsage(undefined), null);
  assert.equal(neuronsFromUsage({}), null);
  assert.equal(neuronsFromUsage({ prompt_tokens: 100 }), null);
  assert.equal(neuronsFromUsage({ prompt_tokens: 'x', completion_tokens: 5 }), null);
  assert.equal(neuronsFromUsage({ prompt_tokens: -1, completion_tokens: 5 }), null);
});

check('neuronsForRequest prefers usage counts, falls back to the char estimate', () => {
  const usage = { prompt_tokens: 1000, completion_tokens: 2000 };
  assert.equal(
    neuronsForRequest({ promptText: 'x'.repeat(40000), outputText: 'y'.repeat(80000), usage }),
    neuronsFromUsage(usage),
  );
  // No usage: 40 in-chars + 200 out-chars -> the char estimate.
  assert.equal(
    neuronsForRequest({ promptText: 'x'.repeat(40), outputText: 'y'.repeat(200) }),
    estimateNeurons(40, 200),
  );
  // outputChars counts when no outputText is given.
  assert.equal(
    neuronsForRequest({ promptText: 'x'.repeat(40), outputChars: 200 }),
    estimateNeurons(40, 200),
  );
});

// --- fresh state / migration ---
check('new server state: today, zero counters, no maintenance', () => {
  assert.deepEqual(newServerState(T0), {
    day: utcDay(T0),
    requests: 0,
    neurons: 0,
    maintenance: null,
  });
  assert.equal(utcDay(T0), '2026-12-07');
});

check('migrateServerRecord: no record starts fresh; good record passes through', () => {
  assert.deepEqual(migrateServerRecord(null, T0), newServerState(T0));
  assert.deepEqual(migrateServerRecord(undefined, T0), newServerState(T0));
  assert.deepEqual(migrateServerRecord({}, T0), newServerState(T0));
  const kept = migrateServerRecord(
    { day: '2026-12-07', requests: 42, neurons: 123.5, maintenance: null },
    T0,
  );
  assert.deepEqual(kept, { day: '2026-12-07', requests: 42, neurons: 123.5, maintenance: null });
  // Negative counters clamp to 0; a malformed maintenance window drops.
  const clamped = migrateServerRecord(
    { day: '2026-12-07', requests: -3, neurons: -1, maintenance: { reason: 'nope' } },
    T0,
  );
  assert.deepEqual(clamped, { day: '2026-12-07', requests: 0, neurons: 0, maintenance: null });
});

// --- recording usage, no trip below the caps ---
check('recordUsage: +1 request, +neurons, no trip below the caps', () => {
  const r = recordUsage(newServerState(T0), 1.5, T0);
  assert.equal(r.tripped, false);
  assert.equal(r.reason, null);
  assert.equal(r.state.requests, 1);
  assert.equal(r.state.neurons, 1.5);
  assert.equal(r.state.maintenance, null);
});

check('recordUsage: mock / zero-neuron requests still count as requests', () => {
  const r = recordUsage(newServerState(T0), 0, T0);
  assert.equal(r.state.requests, 1);
  assert.equal(r.state.neurons, 0);
  assert.equal(r.tripped, false);
});

// --- neuron cap trip ---
check('recordUsage trips maintenance at exactly 10,000 estimated neurons', () => {
  const almost = { day: utcDay(T0), requests: 5000, neurons: 9999, maintenance: null };
  const r = recordUsage(almost, 1, T0);
  assert.equal(r.tripped, true);
  assert.equal(r.reason, 'neurons_exhausted');
  assert.equal(r.state.requests, 5001);
  assert.equal(r.state.neurons, 10000);
  assert.equal(r.state.maintenance.reason, 'neurons_exhausted');
  assert.equal(r.state.maintenance.startedAtMs, T0);
  assert.equal(r.state.maintenance.endsAtMs, T0 + MAINTENANCE_MS);
});

check('recordUsage does NOT trip at 9,999.9 neurons', () => {
  const r = recordUsage(
    { day: utcDay(T0), requests: 1, neurons: 9999, maintenance: null },
    0.9,
    T0,
  );
  assert.equal(r.tripped, false);
  assert.equal(r.state.maintenance, null);
});

// --- request cap trip ---
check('recordUsage trips maintenance at exactly 100,000 requests', () => {
  const almost = { day: utcDay(T0), requests: 99999, neurons: 10, maintenance: null };
  const r = recordUsage(almost, 0, T0);
  assert.equal(r.tripped, true);
  assert.equal(r.reason, 'requests_exhausted');
  assert.equal(r.state.requests, 100000);
  assert.equal(r.state.maintenance.reason, 'requests_exhausted');
  assert.equal(r.state.maintenance.endsAtMs, T0 + MAINTENANCE_MS);
});

check('neuron cap wins when both caps are crossed at once', () => {
  const r = recordUsage(
    { day: utcDay(T0), requests: 99999, neurons: 9999, maintenance: null },
    5,
    T0,
  );
  assert.equal(r.tripped, true);
  assert.equal(r.reason, 'neurons_exhausted');
});

// --- maintenance window: active inside 24h, dead at/after 24h ---
check('maintenance is active inside 24h, inactive at exactly 24h and after', () => {
  const state = tripMaintenance(newServerState(T0), 'neurons_exhausted', 'test detail', T0);
  const m = state.maintenance;
  assert.equal(isMaintenanceActive(m, T0), true);
  assert.equal(isMaintenanceActive(m, T0 + 24 * H - 1), true);
  assert.equal(isMaintenanceActive(m, T0 + 24 * H), false);
  assert.equal(isMaintenanceActive(m, T0 + 25 * H), false);
  assert.equal(isMaintenanceActive(null, T0), false);
});

check('tripMaintenance: a second trip while active does NOT reset the clock', () => {
  const first = tripMaintenance(newServerState(T0), 'neurons_exhausted', 'first', T0);
  const second = tripMaintenance(first, 'requests_exhausted', 'second', T0 + 2 * H);
  assert.equal(second.maintenance.startedAtMs, T0);
  assert.equal(second.maintenance.endsAtMs, T0 + MAINTENANCE_MS);
  assert.equal(second.maintenance.reason, 'neurons_exhausted');
  assert.equal(second.maintenance.detail, 'first');
});

check('tripMaintenance: after expiry a new trip starts a fresh 24h window', () => {
  const first = tripMaintenance(newServerState(T0), 'neurons_exhausted', 'first', T0);
  const second = tripMaintenance(first, 'requests_exhausted', 'second', T0 + 25 * H);
  assert.equal(second.maintenance.startedAtMs, T0 + 25 * H);
  assert.equal(second.maintenance.endsAtMs, T0 + 25 * H + MAINTENANCE_MS);
  assert.equal(second.maintenance.reason, 'requests_exhausted');
});

check('tripMaintenance: unknown reason falls back to neurons_exhausted', () => {
  const s = tripMaintenance(newServerState(T0), 'something-else', '', T0);
  assert.equal(s.maintenance.reason, 'neurons_exhausted');
  assert.ok(s.maintenance.detail.length > 0);
});

// --- maintenance view + response body ---
check('maintenanceView: null when inactive; full view when active, counting down', () => {
  assert.equal(maintenanceView(null, T0), null);
  const expired = tripMaintenance(newServerState(T0), 'neurons_exhausted', 'd', T0);
  assert.equal(maintenanceView(expired.maintenance, T0 + 25 * H), null);
  const active = tripMaintenance(newServerState(T0), 'neurons_exhausted', 'test detail', T0);
  const v = maintenanceView(active.maintenance, T0 + H);
  assert.equal(v.active, true);
  assert.equal(v.reason, 'neurons_exhausted');
  assert.equal(v.reason_detail, 'test detail');
  assert.equal(v.started_at, new Date(T0).toISOString());
  assert.equal(v.back_at, new Date(T0 + 24 * H).toISOString());
  assert.equal(v.back_in_seconds, 23 * 3600);
});

check('maintenanceResponseBody: ok false, names the reason + back time, retry_after matches', () => {
  const active = tripMaintenance(newServerState(T0), 'requests_exhausted', 'test detail', T0);
  const view = maintenanceView(active.maintenance, T0 + 2 * H);
  const body = maintenanceResponseBody(view);
  assert.equal(body.ok, false);
  assert.equal(body.retry_after, 22 * 3600);
  assert.equal(body.maintenance, view);
  assert.match(body.error, /maintenance/);
  assert.match(body.error, /test detail/);
  assert.match(body.error, new RegExp(view.back_at.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
});

// --- UTC-day rollover ---
check('rollDay: same day is a no-op; new day resets counters', () => {
  const s = { day: utcDay(T0), requests: 42, neurons: 100, maintenance: null };
  assert.deepEqual(rollDay(s, T0 + H), s);
  const rolled = rollDay(s, T0 + 25 * H);
  assert.equal(rolled.day, utcDay(T0 + 25 * H));
  assert.equal(rolled.requests, 0);
  assert.equal(rolled.neurons, 0);
  assert.equal(rolled.maintenance, null);
});

check('rollDay: an ACTIVE maintenance window survives the day rollover', () => {
  const tripped = tripMaintenance(newServerState(T0), 'neurons_exhausted', 'd', T0);
  // 13h later the day has rolled (T0 is 12:00 UTC, +13h = 01:00 next day)
  // but the window still has 11h left.
  const rolled = rollDay(tripped, T0 + 13 * H);
  assert.equal(rolled.requests, 0);
  assert.equal(rolled.neurons, 0);
  assert.equal(rolled.maintenance.reason, 'neurons_exhausted');
  assert.equal(rolled.maintenance.endsAtMs, T0 + 24 * H);
  assert.equal(isMaintenanceActive(rolled.maintenance, T0 + 13 * H), true);
});

check('rollDay: an EXPIRED maintenance window is dropped on rollover', () => {
  const tripped = tripMaintenance(newServerState(T0), 'neurons_exhausted', 'd', T0);
  const rolled = rollDay(tripped, T0 + 25 * H);
  assert.equal(rolled.maintenance, null);
});

check('recordUsage after rollover starts fresh counters on the new day', () => {
  const s = { day: utcDay(T0), requests: 99999, neurons: 9999, maintenance: null };
  const r = recordUsage(s, 0.5, T0 + 25 * H);
  assert.equal(r.state.day, utcDay(T0 + 25 * H));
  assert.equal(r.state.requests, 1);
  assert.equal(r.state.neurons, 0.5);
  assert.equal(r.tripped, false);
});

check('recordUsage while already in maintenance still counts, never extends the window', () => {
  const tripped = tripMaintenance(newServerState(T0), 'neurons_exhausted', 'd', T0);
  const r = recordUsage(tripped, 500, T0 + H);
  assert.equal(r.tripped, false);
  assert.equal(r.state.requests, 1);
  assert.equal(r.state.neurons, 500);
  assert.equal(r.state.maintenance.endsAtMs, T0 + 24 * H);
});

console.log(`\n${passed} maintenance tests passed, 0 failed.`);
