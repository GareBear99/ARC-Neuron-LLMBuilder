// Unit tests for chain progress reporting — the pure functions in
// progress.js, the PingProgress Durable Object in worker.js, and the
// Worker /admin/progress routes end to end (fake env + fake DO
// binding, no network, no wrangler, no AI).
// Run: node progress.test.mjs   (Node >= 18, no dependencies.)
//
// These prove:
//   * sanitizeProgressUpdate — validation, normalization, clamping.
//     PASS-THROUGH: percent/bar/ETA are stored VERBATIM as the
//     training side reported them. The neuron side NEVER derives a
//     percent from step/total, NEVER forces 100% on completed, and
//     NEVER renders a bar — that computation lives on the GPU side
//     (scripts/training/progress.py).
//   * progressView — the public shape (stored bar + age), null when empty.
//   * The PingProgress DO — /update stores, /status reads, bad bodies
//     are 400, unknown routes are 404.
//   * The Worker routes — POST /admin/progress then GET
//     /admin/progress round-trips the record; wrong/missing key is
//     401; the endpoints never touch Workers AI and never touch the
//     SP bucket (0 neurons, 0 SP — the fake env has neither binding
//     and the routes still work).
//
// Event-driven (Gary, 2026-11-10): nothing here polls. Updates are
// pushed only when a chain step reports an event; the admin GET is a
// single on-demand pull. The neuron side is only a pass: it stores
// and serves pre-computed progress, it never computes progress.

import assert from 'node:assert/strict';
import {
  BAR_MAX_LEN,
  PROGRESS_STAGES,
  PROGRESS_STATUSES,
  progressView,
  sanitizeProgressUpdate,
} from './progress.js';
import worker, { PingProgress } from './worker.js';

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

async function callDO(doInstance, path, body) {
  const req = new Request(`http://progress${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  const res = await doInstance.fetch(req);
  return { status: res.status, body: await res.json() };
}

// --- pure functions (pass-through: no progress computation here) ---

await check('sanitizeProgressUpdate: a full train update is stored verbatim', async () => {
  const r = sanitizeProgressUpdate(
    {
      stage: 'train',
      status: 'running',
      step: 42,
      total: 152,
      percent: 27.6,
      bar: '[██████░░░░░░░░░░░░░░] 27.6%',
      loss: 1.234,
      eta_seconds: 540,
      run_id: 'lora-1b-20261110',
      message: 'Training step 42/152',
      extra_junk: 'dropped',
    },
    T0,
  );
  assert.equal(r.ok, true);
  assert.equal(r.record.stage, 'train');
  assert.equal(r.record.status, 'running');
  assert.equal(r.record.step, 42);
  assert.equal(r.record.total, 152);
  assert.equal(r.record.percent, 27.6);
  assert.equal(r.record.bar, '[██████░░░░░░░░░░░░░░] 27.6%');
  assert.equal(r.record.loss, 1.234);
  assert.equal(r.record.eta_seconds, 540);
  assert.equal(r.record.run_id, 'lora-1b-20261110');
  assert.equal(r.record.message, 'Training step 42/152');
  assert.equal(r.record.updated_at_ms, T0);
  assert.equal('extra_junk' in r.record, false);
});

await check('sanitizeProgressUpdate: neuron side NEVER derives percent or forces 100%', async () => {
  // step/total WITHOUT a percent: percent stays null (not derived).
  const noPercent = sanitizeProgressUpdate({ stage: 'merge', step: 1, total: 3 }, T0);
  assert.equal(noPercent.ok, true);
  assert.equal(noPercent.record.percent, null);
  assert.equal(noPercent.record.bar, '');
  // completed WITHOUT a percent: percent stays null (not forced to 100).
  // The training side sends percent: 100 when it completes; the
  // server never invents it.
  const doneNoPercent = sanitizeProgressUpdate({ stage: 'merge', step: 1, total: 3, status: 'completed' }, T0);
  assert.equal(doneNoPercent.record.percent, null);
  // A percent that IS sent is clamped, not recomputed.
  const clamped = sanitizeProgressUpdate({ stage: 'gate', percent: 250 }, T0);
  assert.equal(clamped.record.percent, 100);
  const negative = sanitizeProgressUpdate({ stage: 'gate', percent: -5 }, T0);
  assert.equal(negative.record.percent, 0);
  // A bar that is sent is stored verbatim (bounded only).
  const longBar = sanitizeProgressUpdate({ stage: 'gate', percent: 50, bar: 'x'.repeat(200) }, T0);
  assert.equal(longBar.record.bar.length, BAR_MAX_LEN);
});

await check('sanitizeProgressUpdate: missing stage is 400, bad status falls back to running', async () => {
  const missing = sanitizeProgressUpdate({ step: 1 }, T0);
  assert.equal(missing.ok, false);
  assert.match(missing.error, /stage is required/);
  const notObject = sanitizeProgressUpdate('nope', T0);
  assert.equal(notObject.ok, false);
  const badStatus = sanitizeProgressUpdate({ stage: 'train', status: 'exploding' }, T0);
  assert.equal(badStatus.ok, true);
  assert.equal(badStatus.record.status, 'running');
  assert.equal(badStatus.record.step, 0);
  assert.equal(badStatus.record.total, null);
  assert.equal(badStatus.record.percent, null);
});

await check('progressView: public shape with stored bar + age, null when empty', async () => {
  assert.equal(progressView(null, T0), null);
  assert.equal(progressView(undefined, T0), null);
  const r = sanitizeProgressUpdate(
    { stage: 'train', step: 42, total: 152, percent: 27.6, bar: '[██████░░░░░░░░░░░░░░] 27.6%', loss: 1.5 },
    T0,
  ).record;
  setNow(T0 + 90 * 1000);
  const v = progressView(r, nowMs);
  assert.equal(v.stage, 'train');
  assert.equal(v.percent, 27.6);
  assert.equal(v.bar, '[██████░░░░░░░░░░░░░░] 27.6%');
  assert.equal(v.loss, 1.5);
  assert.equal(v.updated_at, new Date(T0).toISOString());
  assert.equal(v.age_seconds, 90);
  // The known stage/status lists are the contract.
  assert.ok(PROGRESS_STAGES.includes('train'));
  assert.ok(PROGRESS_STAGES.includes('gguf'));
  assert.ok(PROGRESS_STAGES.includes('gate'));
  assert.ok(PROGRESS_STATUSES.includes('completed'));
  assert.ok(PROGRESS_STATUSES.includes('failed'));
});

// --- the PingProgress Durable Object ---

await check('DO: status on a fresh DO reports null progress (no state created)', async () => {
  setNow(T0);
  const d = new PingProgress(fakeState());
  const r = await callDO(d, '/status');
  assert.equal(r.status, 200);
  assert.equal(r.body.ok, true);
  assert.equal(r.body.progress, null);
});

await check('DO: update stores and status reads it back (same storage, new instance)', async () => {
  setNow(T0);
  const state = fakeState();
  const d1 = new PingProgress(state);
  const r1 = await callDO(d1, '/update', {
    stage: 'train', step: 42, total: 152, percent: 27.6,
    bar: '[██████░░░░░░░░░░░░░░] 27.6%', loss: 1.2,
  });
  assert.equal(r1.status, 200);
  assert.equal(r1.body.ok, true);
  assert.equal(r1.body.progress.percent, 27.6);
  assert.equal(r1.body.progress.bar, '[██████░░░░░░░░░░░░░░] 27.6%');
  // A new DO instance over the same storage sees the persisted record.
  const d2 = new PingProgress(state);
  const r2 = await callDO(d2, '/status');
  assert.equal(r2.body.progress.stage, 'train');
  assert.equal(r2.body.progress.step, 42);
  // A later update overwrites (latest wins, no history).
  setNow(T0 + 60 * 1000);
  const r3 = await callDO(d2, '/update', {
    stage: 'train', step: 152, total: 152, percent: 100,
    bar: '[████████████████████] 100.0%', status: 'completed',
  });
  assert.equal(r3.body.progress.percent, 100);
  assert.equal(r3.body.progress.status, 'completed');
  const r4 = await callDO(d2, '/status');
  assert.equal(r4.body.progress.age_seconds, 0);
});

await check('DO: update with a bad body is 400 and stores nothing', async () => {
  setNow(T0);
  const d = new PingProgress(fakeState());
  const r = await callDO(d, '/update', { step: 1 });
  assert.equal(r.status, 400);
  assert.equal(r.body.ok, false);
  const s = await callDO(d, '/status');
  assert.equal(s.body.progress, null);
});

await check('DO: unknown progress route is a 404', async () => {
  setNow(T0);
  const d = new PingProgress(fakeState());
  const r = await callDO(d, '/nope');
  assert.equal(r.status, 404);
  assert.equal(r.body.ok, false);
});

// --- the Worker /admin/progress routes (fake env, fake DO binding) ---

const TEST_SECRET = 'progress-test-secret';

// One shared fake DO storage, so a POST then a GET see the same record.
function fakeProgressBinding() {
  const state = fakeState();
  return {
    idFromName: (name) => name,
    get: () => ({
      fetch: (req) => new PingProgress(state).fetch(req),
    }),
  };
}

function fakeEnv(secret) {
  const env = { PROGRESS: fakeProgressBinding() };
  if (secret !== undefined) env.PING_SHARED_SECRET = secret;
  // Deliberately NO env.AI and NO env.RATE_LIMITER: the progress
  // endpoints must work without them (0 neurons, 0 SP).
  return env;
}

async function callWorker(env, method, path, body, key) {
  const headers = { 'content-type': 'application/json' };
  if (key !== undefined) headers['x-lucid-ping-key'] = key;
  const req = new Request(`http://worker${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  const res = await worker.fetch(req, env, {});
  return { status: res.status, body: await res.json() };
}

await check('Worker: POST then GET /admin/progress round-trips (0 neurons, 0 SP)', async () => {
  setNow(T0);
  const env = fakeEnv(TEST_SECRET);
  const post = await callWorker(env, 'POST', '/admin/progress',
    {
      stage: 'train', step: 42, total: 152, percent: 27.6,
      bar: '[██████░░░░░░░░░░░░░░] 27.6%', loss: 1.2, run_id: 'lora-1b-x',
    }, TEST_SECRET);
  assert.equal(post.status, 200);
  assert.equal(post.body.ok, true);
  assert.equal(post.body.progress.stage, 'train');
  assert.equal(post.body.progress.percent, 27.6);
  const get = await callWorker(env, 'GET', '/admin/progress', null, TEST_SECRET);
  assert.equal(get.status, 200);
  assert.equal(get.body.ok, true);
  assert.equal(get.body.progress.step, 42);
  assert.equal(get.body.progress.loss, 1.2);
  assert.equal(get.body.progress.run_id, 'lora-1b-x');
  assert.ok(get.body.progress.bar.includes('27.6%'));
});

await check('Worker: GET /admin/progress with no record yet returns progress null', async () => {
  setNow(T0);
  const env = fakeEnv(TEST_SECRET);
  const get = await callWorker(env, 'GET', '/admin/progress', null, TEST_SECRET);
  assert.equal(get.status, 200);
  assert.equal(get.body.ok, true);
  assert.equal(get.body.progress, null);
});

await check('Worker: /admin/progress requires the key (wrong key 401, no key 401)', async () => {
  setNow(T0);
  const env = fakeEnv(TEST_SECRET);
  const wrong = await callWorker(env, 'GET', '/admin/progress', null, 'wrong-key');
  assert.equal(wrong.status, 401);
  assert.equal(wrong.body.ok, false);
  const missing = await callWorker(env, 'GET', '/admin/progress', null, undefined);
  assert.equal(missing.status, 401);
  const wrongPost = await callWorker(env, 'POST', '/admin/progress',
    { stage: 'train', step: 1 }, 'wrong-key');
  assert.equal(wrongPost.status, 401);
});

await check('Worker: POST /admin/progress with a bad body is 400', async () => {
  setNow(T0);
  const env = fakeEnv(TEST_SECRET);
  const r = await callWorker(env, 'POST', '/admin/progress', { step: 1 }, TEST_SECRET);
  assert.equal(r.status, 400);
  assert.equal(r.body.ok, false);
});

Date.now = realNow;

console.log(`\n${passed} progress tests passed, 0 failed.`);
