// Unit tests for the token bucket (bucket.js) — pure refill math.
// Run: node bucket.test.mjs   (Node >= 18, no dependencies, no network.)
// Every case is hand-checkable; the numbers below are the spec.

import assert from 'node:assert/strict';
import {
  SP_INITIAL,
  STAGE_1,
  STAGE_2,
  applyRefill,
  migrateRecord,
  newUserState,
  peekBucket,
  quotaView,
  spendBucket,
  stageFor,
  todayUTC,
} from './bucket.js';

const H = 3600 * 1000;
const T0 = Date.UTC(2026, 10, 6, 12, 0, 0); // a fixed "now" (ms)

let passed = 0;
function check(name, fn) {
  fn();
  passed += 1;
  console.log(`ok - ${name}`);
}

// --- stages ---
check('stage 1 below 200, stage 2 at/above 200', () => {
  assert.equal(stageFor(0), STAGE_1);
  assert.equal(stageFor(199), STAGE_1);
  assert.equal(stageFor(200), STAGE_2);
  assert.equal(stageFor(250), STAGE_2);
});

// --- new user ---
check('new user starts at 100 SP, no refill before 4h', () => {
  const s = newUserState(T0);
  assert.deepEqual(s, { balance: 100, lastRefill: T0 });
  assert.deepEqual(applyRefill(s, T0 + 3 * H + 59 * 60 * 1000), { balance: 100, lastRefill: T0 });
  const v = quotaView(s, T0);
  assert.equal(v.limit, 200);
  assert.equal(v.remaining, 100);
  assert.equal(v.reset, Math.floor((T0 + 4 * H) / 1000));
  assert.equal(v.reset_in_seconds, 4 * 3600);
});

// --- stage 1 refill boundaries ---
check('exactly 4h: one refill (+25)', () => {
  const s = applyRefill({ balance: 100, lastRefill: T0 }, T0 + 4 * H);
  assert.deepEqual(s, { balance: 125, lastRefill: T0 + 4 * H });
});
check('exactly 8h: two refills (+50)', () => {
  const s = applyRefill({ balance: 100, lastRefill: T0 }, T0 + 8 * H);
  assert.deepEqual(s, { balance: 150, lastRefill: T0 + 8 * H });
});
check('partial periods: 7h59m refills once only, remainder banked (no drift)', () => {
  const s = applyRefill({ balance: 100, lastRefill: T0 }, T0 + 7 * H + 59 * 60 * 1000);
  assert.deepEqual(s, { balance: 125, lastRefill: T0 + 4 * H });
  // 3h59m after the consumed boundary: nothing yet.
  const s2 = applyRefill(s, T0 + 7 * H + 59 * 60 * 1000);
  assert.deepEqual(s2, { balance: 125, lastRefill: T0 + 4 * H });
  // 4h after the consumed boundary (8h total): the banked remainder
  // completes the next period — refill again.
  const s3 = applyRefill(s, T0 + 8 * H);
  assert.deepEqual(s3, { balance: 150, lastRefill: T0 + 8 * H });
  // 8h after the consumed boundary (12h total): two periods.
  const s4 = applyRefill(s, T0 + 12 * H);
  assert.deepEqual(s4, { balance: 175, lastRefill: T0 + 12 * H });
});
check('stage 1 cap: 190 + 12h clamps at 200', () => {
  const s = applyRefill({ balance: 190, lastRefill: T0 }, T0 + 12 * H);
  assert.deepEqual(s, { balance: 200, lastRefill: T0 + 12 * H });
});

// --- stage 2 ---
check('stage 2: 200 + 12h -> 220, +24h -> 240, +36h -> 250 (cap)', () => {
  assert.deepEqual(applyRefill({ balance: 200, lastRefill: T0 }, T0 + 12 * H), {
    balance: 220,
    lastRefill: T0 + 12 * H,
  });
  assert.deepEqual(applyRefill({ balance: 200, lastRefill: T0 }, T0 + 24 * H), {
    balance: 240,
    lastRefill: T0 + 24 * H,
  });
  assert.deepEqual(applyRefill({ balance: 200, lastRefill: T0 }, T0 + 36 * H), {
    balance: 250,
    lastRefill: T0 + 36 * H,
  });
});
check('stage 2 cap: 245 + 24h clamps at 250', () => {
  assert.deepEqual(applyRefill({ balance: 245, lastRefill: T0 }, T0 + 24 * H), {
    balance: 250,
    lastRefill: T0 + 24 * H,
  });
});
check('stage 2 cadence is 12h, not 4h: 200 + 11h refills nothing', () => {
  assert.deepEqual(applyRefill({ balance: 200, lastRefill: T0 }, T0 + 11 * H), {
    balance: 200,
    lastRefill: T0,
  });
});

// --- stage boundary crossing ---
check('crossing 200: 190 + 8h refills under stage 1 and stops at the 200 cap', () => {
  const s = applyRefill({ balance: 190, lastRefill: T0 }, T0 + 8 * H);
  assert.deepEqual(s, { balance: 200, lastRefill: T0 + 8 * H });
  // The next refill now runs under stage 2 (12h cadence, +20).
  const s2 = applyRefill(s, T0 + 8 * H + 12 * H);
  assert.deepEqual(s2, { balance: 220, lastRefill: T0 + 8 * H + 12 * H });
});
check('dropping below 200: 199 refills under stage 1 again (+25/4h, cap 200)', () => {
  // 12h at 199 is three stage-1 periods, capped at 200 — NOT 199+20.
  assert.deepEqual(applyRefill({ balance: 199, lastRefill: T0 }, T0 + 12 * H), {
    balance: 200,
    lastRefill: T0 + 12 * H,
  });
  // And a single 4h period gives +25, capped at 200.
  assert.deepEqual(applyRefill({ balance: 180, lastRefill: T0 }, T0 + 4 * H), {
    balance: 200,
    lastRefill: T0 + 4 * H,
  });
});
check('spend across the boundary: 200 -> 199 switches the next refill to stage 1', () => {
  const spent = spendBucket({ balance: 200, lastRefill: T0 }, T0);
  assert.equal(spent.allowed, true);
  assert.equal(spent.state.balance, 199);
  assert.equal(spent.view.limit, 200); // cap for the stage the user is now in
  assert.equal(spent.view.reset, Math.floor((T0 + 4 * H) / 1000)); // 4h cadence
});

// --- quota view / headers ---
check('quota view in stage 2: limit 250, reset is the 12h boundary', () => {
  const v = quotaView({ balance: 220, lastRefill: T0 }, T0);
  assert.equal(v.limit, 250);
  assert.equal(v.remaining, 220);
  assert.equal(v.reset, Math.floor((T0 + 12 * H) / 1000));
  assert.equal(v.reset_in_seconds, 12 * 3600);
});

// --- empty bucket / 429 ---
check('empty bucket: no refill before 4h, reset is the next 4h boundary', () => {
  const s = applyRefill({ balance: 0, lastRefill: T0 }, T0 + 2 * H);
  assert.deepEqual(s, { balance: 0, lastRefill: T0 });
  const spent = spendBucket({ balance: 0, lastRefill: T0 }, T0 + 2 * H);
  assert.equal(spent.allowed, false);
  assert.equal(spent.state.balance, 0);
  assert.equal(spent.view.limit, 200);
  assert.equal(spent.view.remaining, 0);
  assert.equal(spent.view.reset, Math.floor((T0 + 4 * H) / 1000));
  assert.equal(spent.view.reset_in_seconds, 2 * 3600); // Retry-After
});
check('empty bucket refills after exactly 4h (+25, spendable again)', () => {
  const spent = spendBucket({ balance: 0, lastRefill: T0 }, T0 + 4 * H);
  assert.equal(spent.allowed, true);
  assert.equal(spent.state.balance, 24); // +25 refilled, 1 spent
  assert.equal(spent.view.remaining, 24);
});
check('a 429 can only happen in stage 1 (balance 0 < 200); stage 2 never 429s', () => {
  // Any balance >= 200 always has >= 1 SP to spend.
  for (const b of [200, 201, 220, 250]) {
    assert.equal(spendBucket({ balance: b, lastRefill: T0 }, T0).allowed, true);
  }
});

// --- spend / peek ---
check('spend deducts exactly 1 SP and reports the post-spend balance', () => {
  const r = spendBucket(null, T0); // new user
  assert.equal(r.allowed, true);
  assert.equal(r.state.balance, 99);
  assert.equal(r.view.remaining, 99);
  assert.equal(r.view.limit, 200);
});
check('/ping never deducts: peek twice, then spend, balance drops by exactly 1', () => {
  const record = { balance: 100, lastRefill: T0 };
  const p1 = peekBucket(record, T0);
  const p2 = peekBucket(record, T0);
  assert.equal(p1.view.remaining, 100);
  assert.equal(p2.view.remaining, 100);
  // Peeking must not have changed the stored record.
  assert.deepEqual(record, { balance: 100, lastRefill: T0 });
  const spent = spendBucket(record, T0);
  assert.equal(spent.state.balance, 99);
  // And a peek after the spend sees 99, not 100.
  assert.equal(peekBucket(spent.state, T0).view.remaining, 99);
});

// --- migration ---
check('migration: old shape, same-day count carries the remainder in', () => {
  const today = todayUTC(T0);
  assert.deepEqual(migrateRecord({ count: 2, day: today }, T0), { balance: 98, lastRefill: T0 });
  assert.deepEqual(migrateRecord({ count: 0, day: today }, T0), { balance: 100, lastRefill: T0 });
  assert.deepEqual(migrateRecord({ count: 100, day: today }, T0), { balance: 0, lastRefill: T0 });
});
check('migration: old shape from an earlier day resets to 100 (as the old code did)', () => {
  assert.deepEqual(migrateRecord({ count: 90, day: '2026-11-05' }, T0), {
    balance: 100,
    lastRefill: T0,
  });
  assert.deepEqual(migrateRecord({ count: 0, day: '' }, T0), { balance: 100, lastRefill: T0 });
});
check('migration: no record starts a new user at 100; new shape passes through', () => {
  assert.deepEqual(migrateRecord(null, T0), { balance: 100, lastRefill: T0 });
  assert.deepEqual(migrateRecord(undefined, T0), { balance: 100, lastRefill: T0 });
  assert.deepEqual(migrateRecord({}, T0), { balance: 100, lastRefill: T0 });
  assert.deepEqual(migrateRecord({ balance: 150, lastRefill: T0 - 2 * H }, T0), {
    balance: 150,
    lastRefill: T0 - 2 * H,
  });
  // A new-shape balance above the max cap is clamped on read.
  assert.equal(migrateRecord({ balance: 999, lastRefill: T0 }, T0).balance, 250);
});
check('migration + refill: a migrated user refills from the migration moment', () => {
  const today = todayUTC(T0);
  const migrated = migrateRecord({ count: 2, day: today }, T0); // 98 SP
  const after = applyRefill(migrated, T0 + 4 * H);
  assert.deepEqual(after, { balance: 123, lastRefill: T0 + 4 * H });
});

console.log(`\n${passed} bucket tests passed, 0 failed.`);
