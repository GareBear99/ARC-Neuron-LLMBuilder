/**
 * Token bucket (stock points) — pure functions, no Cloudflare APIs.
 *
 * Shared by worker.js (the Durable Object) and bucket.test.mjs (Node
 * unit tests). The server is the sole authority on quota: nothing
 * about the bucket is computed or enforced anywhere else.
 *
 * Currency: SP — stock points. 1 SP per /v1/chat/completions request.
 * SP are like credits: the balance is the user's credit balance.
 * POST /ping (the registration / health check) costs 0 SP — it never
 * deducts and never 429s. Only chat completions spend SP.
 *
 * Two stages, decided by the balance at refill time:
 *   Stage 1 (balance < 200):  +25 SP every 4 hours,  cap 200 SP.
 *   Stage 2 (balance >= 200): +20 SP every 12 hours, cap 250 SP.
 * When the balance drops below 200 through use, refills go back to
 * stage 1 (+25/4h, cap 200) until it reaches 200 again, then stage 2
 * resumes. So an idle user climbs 200 → 220 → 240 → 250 over three
 * 12-hour periods, and no user can ever hold more than 250 SP.
 *
 * State per user (one DO record): { balance, lastRefill } where
 * lastRefill is the unix-ms timestamp of the last refill boundary
 * consumed. Refills are whole periods only: lastRefill advances by
 * exactly the consumed periods, so partial periods are never lost
 * (no drift). New users start at 100 SP.
 *
 * Migration: the old shape was { count, day } (100/day, UTC-day
 * buckets). On first request after deploy the remaining balance is
 * carried into the bucket (nobody's quota is wiped) and lastRefill
 * is set to now; if the old state cannot be read, the user starts
 * at 100 SP.
 */

export const SP_INITIAL = 100;

// Stage 1: balance < 200.
export const STAGE_1 = { refill: 25, periodMs: 4 * 3600 * 1000, cap: 200 };
// Stage 2: balance >= 200.
export const STAGE_2 = { refill: 20, periodMs: 12 * 3600 * 1000, cap: 250 };
export const STAGE_2_THRESHOLD = 200;
export const MAX_CAP = 250;
// The old daily allowance, for migration only.
const OLD_DAILY_LIMIT = 100;

/** The refill stage for a balance: 1 below 200 SP, 2 at or above. */
export function stageFor(balance) {
  return balance >= STAGE_2_THRESHOLD ? STAGE_2 : STAGE_1;
}

/**
 * Apply the refills due between lastRefill and nowMs.
 * The stage is decided by the balance BEFORE the refill. Whole
 * periods only; lastRefill advances by exactly the consumed periods
 * (no drift — a leftover partial period stays banked for next time).
 * Returns a NEW state { balance, lastRefill }; the input is untouched.
 */
export function applyRefill(state, nowMs) {
  const stage = stageFor(state.balance);
  const elapsed = nowMs - state.lastRefill;
  if (elapsed < stage.periodMs) {
    return { balance: state.balance, lastRefill: state.lastRefill };
  }
  const periods = Math.floor(elapsed / stage.periodMs);
  return {
    balance: Math.min(stage.cap, state.balance + periods * stage.refill),
    lastRefill: state.lastRefill + periods * stage.periodMs,
  };
}

/**
 * Quota view for headers and bodies: limit is the CURRENT cap for the
 * user's stage (200 or 250), remaining is the balance, reset is the
 * next refill boundary (unix seconds) under that stage's cadence.
 * The stage here is the stage of the CURRENT balance — the stage that
 * will govern the NEXT refill — so the reported limit/reset always
 * describe what actually happens next.
 */
export function quotaView(state, nowMs) {
  const stage = stageFor(state.balance);
  const reset = Math.floor((state.lastRefill + stage.periodMs) / 1000);
  return {
    limit: stage.cap,
    remaining: Math.max(0, state.balance),
    reset,
    reset_in_seconds: Math.max(0, reset - Math.floor(nowMs / 1000)),
  };
}

/** A brand-new user: 100 SP, refill clock starts now. */
export function newUserState(nowMs) {
  return { balance: SP_INITIAL, lastRefill: nowMs };
}

/** UTC date string, e.g. "2026-11-06" — old-shape migration only. */
export function todayUTC(nowMs = Date.now()) {
  return new Date(nowMs).toISOString().slice(0, 10);
}

/**
 * Migrate a stored DO record to the new shape { balance, lastRefill }.
 * - New shape (numeric balance): keep it, clamped to [0, 250]; keep
 *   lastRefill if numeric, else nowMs.
 * - Old shape (numeric count): the remaining balance for today carries
 *   in — max(0, 100 - count) when the record is from today, 100 when
 *   it is from an earlier day (the old code would have reset it);
 *   lastRefill is set to nowMs. Nobody's quota is wiped.
 * - Anything else / no record: a new user (100 SP, lastRefill nowMs).
 */
export function migrateRecord(record, nowMs) {
  if (record && typeof record.balance === 'number' && Number.isFinite(record.balance)) {
    return {
      balance: Math.min(MAX_CAP, Math.max(0, Math.floor(record.balance))),
      lastRefill:
        typeof record.lastRefill === 'number' && Number.isFinite(record.lastRefill)
          ? record.lastRefill
          : nowMs,
    };
  }
  if (record && typeof record.count === 'number' && Number.isFinite(record.count)) {
    const balance =
      record.day === todayUTC(nowMs)
        ? Math.max(0, OLD_DAILY_LIMIT - Math.floor(record.count))
        : SP_INITIAL;
    return { balance, lastRefill: nowMs };
  }
  return newUserState(nowMs);
}

/**
 * Pure DO operations (no storage I/O) — the DO class is a thin wrapper
 * around these, so they are unit-testable in Node.
 *
 * peekBucket(record, nowMs): the /ping read — refilled view, no
 *   deduction, nothing to persist. A peek never spends SP.
 * spendBucket(record, nowMs): the /check — refilled, then minus 1 SP
 *   if any remain; `state` is what the DO persists, `allowed` says
 *   whether the request may proceed.
 */
export function peekBucket(record, nowMs) {
  const state = applyRefill(migrateRecord(record, nowMs), nowMs);
  return { state, view: quotaView(state, nowMs) };
}

export function spendBucket(record, nowMs) {
  const refilled = applyRefill(migrateRecord(record, nowMs), nowMs);
  const state = { balance: refilled.balance, lastRefill: refilled.lastRefill };
  let allowed = false;
  if (state.balance >= 1) {
    state.balance -= 1;
    allowed = true;
  }
  return { state, allowed, view: quotaView(state, nowMs) };
}
