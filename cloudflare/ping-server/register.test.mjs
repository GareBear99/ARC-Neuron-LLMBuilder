// Unit tests for per-install key registration (Fix 2 — the default
// ping server works without manual key entry): POST /register mints
// one key per user id, authorizedClient() accepts it alongside the
// shared secret on the client routes only, and /admin/* stays
// shared-secret-only. The real PingRateLimiter DO class and the real
// Worker fetch, driven with fake storage and a faked env. No network,
// no wrangler. Run: node register.test.mjs   (Node >= 18, no
// dependencies.)
//
// Contract (the Lucid client ensureDefaultPingKey, deployed d8c6a54):
// POST {endpoint}/register with { userId } returns { ok: true, key }.
// Re-issue for the same userId returns the SAME key. The key is
// accepted as x-lucid-ping-key for /ping, /v1/chat/completions and
// /temp/activate. The shared secret keeps working. A per-install key
// never reaches /admin/*.

import assert from 'node:assert/strict';
import worker, {
  GrabState,
  PingRateLimiter,
  TempIndex,
  authorizedClient,
  keysEqual,
  mintInstallKey,
} from './worker.js';

let passed = 0;
async function check(name, fn) {
  await fn();
  passed += 1;
  console.log(`ok - ${name}`);
}

// --- fake DO storage (Map-backed, same get/put/list shape as the real API) ---
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

// Per-stub namespaced storage over one shared Map (grab.test.mjs
// pattern): each limiter stub owns its keys (`user:<id>:...`), so many
// stubs share one Map without colliding.
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

function fakeEnv(sharedMap, extra = {}) {
  const binding = (Class, namespaceFor) => ({
    idFromName: (id) => id,
    get: (id) => new Class(namespacedState(sharedMap, namespaceFor(id))),
  });
  return {
    RATE_LIMITER: binding(PingRateLimiter, (id) => id),
    GRAB_PUBLIC_URL: 'https://lucid-ping-server.admension.workers.dev',
    ...extra,
  };
}

async function callDo(doInstance, path, body) {
  const req = new Request(`http://limiter${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  const res = await doInstance.fetch(req);
  return { status: res.status, body: await res.json() };
}

async function callWorker(env, method, path, body, headers = {}) {
  const req = new Request(`http://worker${path}`, {
    method,
    headers: { 'content-type': 'application/json', ...headers },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const res = await worker.fetch(req, env, {});
  let parsed = null;
  try {
    parsed = await res.json();
  } catch {
    parsed = null;
  }
  return { status: res.status, body: parsed };
}

// --- mintInstallKey ---
await check('mintInstallKey: pk- prefix, 67 chars, hex after the prefix', () => {
  const key = mintInstallKey();
  assert.ok(key.startsWith('pk-'), `key starts with pk-: ${key.slice(0, 5)}`);
  assert.equal(key.length, 67, `key length is 67, got ${key.length}`);
  assert.ok(/^pk-[0-9a-f]{64}$/.test(key), 'key is pk- + 64 hex chars');
});

await check('mintInstallKey: two calls differ (random)', () => {
  assert.notEqual(mintInstallKey(), mintInstallKey());
});

// --- keysEqual ---
await check('keysEqual: identical true, different false, length false, non-string false', () => {
  assert.equal(keysEqual('pk-abc', 'pk-abc'), true);
  assert.equal(keysEqual('pk-abc', 'pk-abd'), false);
  assert.equal(keysEqual('pk-abc', 'pk-ab'), false);
  assert.equal(keysEqual('pk-abc', null), false);
  assert.equal(keysEqual(null, 'pk-abc'), false);
  assert.equal(keysEqual(undefined, undefined), false);
  assert.equal(keysEqual('', ''), true);
});

// --- PingRateLimiter /register-key + /check-key ---
await check('limiter /register-key: first call mints, second returns the SAME key', async () => {
  const limiter = new PingRateLimiter(fakeState());
  const first = await callDo(limiter, '/register-key');
  assert.equal(first.status, 200);
  assert.equal(first.body.ok, true);
  assert.ok(/^pk-[0-9a-f]{64}$/.test(first.body.key), 'minted key shape');
  const second = await callDo(limiter, '/register-key');
  assert.equal(second.status, 200);
  assert.equal(second.body.key, first.body.key, 're-issue returns the same key');
  const third = await callDo(limiter, '/register-key');
  assert.equal(third.body.key, first.body.key, 'third call still the same key');
});

await check('limiter /check-key: match true, wrong false, no key false, never mints', async () => {
  const limiter = new PingRateLimiter(fakeState());
  // No key stored yet: check must not mint.
  const empty = await callDo(limiter, '/check-key', { key: 'pk-0000000000000000000000000000000000000000000000000000000000000000' });
  assert.equal(empty.status, 200);
  assert.equal(empty.body.match, false);
  // Still no key after a failed check (the check did not mint one).
  const minted = await callDo(limiter, '/register-key');
  const key = minted.body.key;
  const good = await callDo(limiter, '/check-key', { key });
  assert.equal(good.body.match, true);
  const bad = await callDo(limiter, '/check-key', { key: 'pk-ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff' });
  assert.equal(bad.body.match, false);
  const noKey = await callDo(limiter, '/check-key', {});
  assert.equal(noKey.body.match, false);
  const nonString = await callDo(limiter, '/check-key', { key: 123 });
  assert.equal(nonString.body.match, false);
});

// --- authorizedClient ---
await check('authorizedClient: open when no secret is configured', async () => {
  const env = fakeEnv(new Map());
  const req = new Request('http://x/ping', { method: 'POST' });
  assert.equal(await authorizedClient(req, env), true);
});

await check('authorizedClient: shared secret still works, wrong key fails, no key fails', async () => {
  const env = fakeEnv(new Map(), { PING_SHARED_SECRET: 'test-shared-secret' });
  const withSecret = new Request('http://x/ping', {
    method: 'POST',
    headers: { 'x-lucid-ping-key': 'test-shared-secret', 'x-lucid-user': 'install-1' },
  });
  assert.equal(await authorizedClient(withSecret, env), true);
  const wrong = new Request('http://x/ping', {
    method: 'POST',
    headers: { 'x-lucid-ping-key': 'wrong-key', 'x-lucid-user': 'install-1' },
  });
  assert.equal(await authorizedClient(wrong, env), false);
  const none = new Request('http://x/ping', {
    method: 'POST',
    headers: { 'x-lucid-user': 'install-1' },
  });
  assert.equal(await authorizedClient(none, env), false);
});

await check('authorizedClient: per-install key works for its user, not for another user, not without a user id', async () => {
  const sharedMap = new Map();
  const env = fakeEnv(sharedMap, { PING_SHARED_SECRET: 'test-shared-secret' });
  // Mint a key for install-1 via the DO.
  const limiter = new PingRateLimiter(namespacedState(sharedMap, 'user:install-1'));
  const minted = await callDo(limiter, '/register-key');
  const key = minted.body.key;
  const good = new Request('http://x/ping', {
    method: 'POST',
    headers: { 'x-lucid-ping-key': key, 'x-lucid-user': 'install-1' },
  });
  assert.equal(await authorizedClient(good, env), true);
  const otherUser = new Request('http://x/ping', {
    method: 'POST',
    headers: { 'x-lucid-ping-key': key, 'x-lucid-user': 'install-2' },
  });
  assert.equal(await authorizedClient(otherUser, env), false, 'a key does not authenticate another user id');
  const noUser = new Request('http://x/ping', {
    method: 'POST',
    headers: { 'x-lucid-ping-key': key },
  });
  assert.equal(await authorizedClient(noUser, env), false, 'a per-install key without a user id fails');
});

await check('authorizedClient: DO error fails closed (not authorized)', async () => {
  const env = {
    PING_SHARED_SECRET: 'test-shared-secret',
    RATE_LIMITER: {
      idFromName: (id) => id,
      get: () => ({
        fetch: async () => {
          throw new Error('DO down');
        },
      }),
    },
  };
  const req = new Request('http://x/ping', {
    method: 'POST',
    headers: { 'x-lucid-ping-key': 'pk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'x-lucid-user': 'install-1' },
  });
  assert.equal(await authorizedClient(req, env), false);
});

// --- POST /register (full Worker route) ---
await check('POST /register: mints a key, re-issue returns the same key', async () => {
  const sharedMap = new Map();
  const env = fakeEnv(sharedMap);
  const first = await callWorker(env, 'POST', '/register', { userId: 'test-install-abc' });
  assert.equal(first.status, 200, `first register status ${first.status}: ${JSON.stringify(first.body)}`);
  assert.equal(first.body.ok, true);
  assert.ok(/^pk-[0-9a-f]{64}$/.test(first.body.key), 'minted key shape');
  const second = await callWorker(env, 'POST', '/register', { userId: 'test-install-abc' });
  assert.equal(second.status, 200);
  assert.equal(second.body.key, first.body.key, 're-issue returns the same key');
  // A different userId gets a different key.
  const other = await callWorker(env, 'POST', '/register', { userId: 'test-install-xyz' });
  assert.equal(other.status, 200);
  assert.notEqual(other.body.key, first.body.key, 'different userId gets a different key');
});

await check('POST /register: invalid userId rejected (400), invalid JSON rejected (400)', async () => {
  const env = fakeEnv(new Map());
  for (const bad of ['', 123, null, 'has space', 'has/slash', 'x'.repeat(129)]) {
    const res = await callWorker(env, 'POST', '/register', { userId: bad });
    assert.equal(res.status, 400, `userId ${JSON.stringify(bad)} must be 400, got ${res.status}`);
    assert.equal(res.body.ok, false);
  }
  const missing = await callWorker(env, 'POST', '/register', {});
  assert.equal(missing.status, 400);
  const req = new Request('http://worker/register', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: '{not json',
  });
  const res = await worker.fetch(req, env, {});
  assert.equal(res.status, 400);
});

await check('minted key authenticates /ping; shared secret still authenticates /ping', async () => {
  const sharedMap = new Map();
  const env = fakeEnv(sharedMap, { PING_SHARED_SECRET: 'test-shared-secret' });
  const reg = await callWorker(env, 'POST', '/register', { userId: 'test-install-ping' });
  assert.equal(reg.status, 200);
  const key = reg.body.key;
  // /ping with the minted key + its userId: 200 (and a quota block).
  const withKey = await callWorker(
    env, 'POST', '/ping', { message: 'hello' },
    { 'x-lucid-ping-key': key, 'x-lucid-user': 'test-install-ping' },
  );
  assert.equal(withKey.status, 200, `ping with minted key: ${withKey.status} ${JSON.stringify(withKey.body)}`);
  assert.equal(withKey.body.ok, true);
  assert.ok(withKey.body.quota, 'ping reports the quota for the minted-key user');
  // /ping with the shared secret (a different user): 200.
  const withSecret = await callWorker(
    env, 'POST', '/ping', { message: 'hello' },
    { 'x-lucid-ping-key': 'test-shared-secret', 'x-lucid-user': 'test-install-other' },
  );
  assert.equal(withSecret.status, 200);
  // /ping with a wrong key: 401.
  const wrong = await callWorker(
    env, 'POST', '/ping', { message: 'hello' },
    { 'x-lucid-ping-key': 'wrong-key', 'x-lucid-user': 'test-install-ping' },
  );
  assert.equal(wrong.status, 401);
});

await check('per-install key does NOT authenticate /admin/* (shared secret only)', async () => {
  const sharedMap = new Map();
  // The admin route, once past auth, reads the grab state and the
  // temp-index outcomes — give the fake env those bindings (real
  // DO classes, empty storage) so the shared-secret call runs to
  // completion instead of throwing on a missing binding.
  const binding = (Class, namespaceFor) => ({
    idFromName: (id) => id,
    get: (id) => new Class(namespacedState(sharedMap, namespaceFor(id))),
  });
  const env = {
    ...fakeEnv(sharedMap, { PING_SHARED_SECRET: 'test-shared-secret' }),
    GRAB_STATE: binding(GrabState, (id) => id),
    TEMP_INDEX: binding(TempIndex, (id) => id),
  };
  const reg = await callWorker(env, 'POST', '/register', { userId: 'test-install-admin' });
  const key = reg.body.key;
  const admin = await callWorker(
    env, 'GET', '/admin/grab-outcomes', undefined,
    { 'x-lucid-ping-key': key, 'x-lucid-user': 'test-install-admin' },
  );
  assert.equal(admin.status, 401, `admin with a per-install key must be 401, got ${admin.status}`);
  const adminSecret = await callWorker(
    env, 'GET', '/admin/grab-outcomes', undefined,
    { 'x-lucid-ping-key': 'test-shared-secret' },
  );
  // The admin route itself must accept the shared secret (200 with
  // an empty outcome log — no grab has ever started in this fake).
  assert.equal(adminSecret.status, 200, `admin with the shared secret must be 200, got ${adminSecret.status}: ${JSON.stringify(adminSecret.body)}`);
  assert.equal(adminSecret.body.ok, true);
  assert.deepEqual(adminSecret.body.outcomes, []);
});

console.log(`\n${passed} register tests passed, 0 failed.`);
