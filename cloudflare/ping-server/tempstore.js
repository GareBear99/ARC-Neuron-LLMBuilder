/**
 * Temp store — pure functions, no Cloudflare APIs.
 *
 * Shared by worker.js (the TempRecord / TempIndex Durable Objects)
 * and tempstore.test.mjs (Node unit tests). Follows the repo's own
 * pattern: bucket.js / maintenance.js / progress.js hold the pure
 * logic, the DO classes in worker.js are thin storage wrappers.
 *
 * Ground truth: ~/workspace/temp-verification-how-verified-spec.md
 * (step 1 of the dailies — how temps are verified, Gary 2026-11-15
 * ~09:54 PST). Record shape is spec §3.2; the chain check is
 * spec §1.2; the outcome states are spec §2.
 *
 * Two interpretation notes, stated here so the build has one
 * meaning and Gary can correct them (neither is invented silently):
 *
 * 1. "The chain doesn't hold yet" (spec §1.2 step 4) is read as
 *    the REFERRER not being verified yet. The chain is checked in
 *    order — referral -> temp -> verified -> user — so a temp
 *    cannot be recognised before its referrer is. A temp whose
 *    referrer exists but is not yet verified stays `pending` and
 *    is re-checked by the next grab. The alternative reading
 *    (referral present = link unbroken, no referrer-state
 *    dependency) would make "pending after a grab" impossible
 *    except via the cap (plan Q2), which contradicts step 4's
 *    "chain intact so far, but not yet recognised". If Gary means
 *    the alternative, this function changes, not the spec's words.
 * 2. A discarded temp is `expired`, not `not_verified`. The spec
 *    lists discarded under both (§1.2 step 5); expired is the
 *    state that "stops counting and can never be verified later",
 *    which is what discarding means. `not_verified` is reserved
 *    for a broken referral link.
 *
 * Labelling (binding, from the plan): every number in reports
 * built on this module is MEASURED (observed, method named),
 * ESTIMATE (computed from measured inputs, labelled), or UNKNOWN
 * (stated as such, with what would measure it).
 */

export const TEMP_STATUSES = ['temp', 'unverified', 'verified', 'user', 'guest'];
export const VERIFICATION_STATES = ['pending', 'verified', 'not_verified'];

/**
 * The genesis referral — the root of the referral chain.
 * The first temp ever activated (activation tick 1) may carry
 * this referral id, and the grab treats its referrer as verified,
 * so the root verifies on the first grab. It is the bootstrap:
 * without a root there is no verified referrer for any later
 * temp to chain from. Any other temp carrying it is not the root
 * (see genesisReferrerState) and is marked not_verified — the
 * genesis claim cannot be used to skip the chain.
 */
export const GENESIS_REFERRAL_ID = 'ref:genesis';
/** The activation tick of the genesis root: the first temp ever. */
export const GENESIS_ROOT_TICK = 1;

/**
 * Resolve a genesis referral claim to the referrer state the
 * chain check reads. Pure: no storage I/O.
 * - referralId is the genesis id AND the tick is the root tick
 *   (1) -> 'genesis': the referrer is verified by definition.
 * - referralId is the genesis id but the tick is not the root
 *   -> 'genesis_not_root': the claim is not the root.
 * - anything else -> null (not a genesis claim; the caller
 *   resolves the referrer normally).
 */
export function genesisReferrerState(referralId, activationTick) {
  if (referralId !== GENESIS_REFERRAL_ID) return null;
  return activationTick === GENESIS_ROOT_TICK ? 'genesis' : 'genesis_not_root';
}

/** The grab's outcomes, plus `skip` (already verified — never re-verify, never re-number). */
export const GRAB_OUTCOMES = ['verified', 'pending', 'not_verified', 'expired', 'skip'];

/**
 * Terminal grab outcomes — the record's verification is decided
 * and no future grab can change it (verified is stamped once;
 * not_verified / expired are final). A queue entry whose outcome
 * is terminal is DISCARDED from the nightly walk: the grab marks
 * it done (see queueValue) and never pays the referrer /get +
 * /apply for it again. Pending is NOT terminal — a pending
 * record is re-checked by every grab until it is recognised or
 * expires. 'skip' is not an outcome and is never logged.
 */
export const TERMINAL_OUTCOMES = ['verified', 'not_verified', 'expired'];

/** True when the outcome decides the record for good. */
export function isTerminalOutcome(outcome) {
  return TERMINAL_OUTCOMES.includes(outcome);
}

export const ONE_YEAR_MS = 365 * 24 * 3600 * 1000;

/** UTC date string, e.g. "2026-11-15" — the grab day. */
export function utcDay(nowMs = Date.now()) {
  return new Date(nowMs).toISOString().slice(0, 10);
}

/**
 * A brand-new temp record, from the client-side creation shape
 * (profileStore.ts createProfile: `profile-<random UUID>`, status
 * `temp`, createdAt now). The caller supplies id / referralId /
 * activationTick / windowStart; windowEnd is windowStart + 1 year.
 * ownerUserId is the per-install user id (x-lucid-user) that
 * activated this temp, recorded by the intake — it binds the temp
 * to the install that owns it, so the verified SP grant can only
 * ever be claimed by its owner (a client naming someone else's
 * verified profile id gets nothing). Null for records created
 * before the binding existed; a null owner can never resolve as
 * verified (fail closed).
 */
export function newTempRecord({ id, referralId, activationTick, windowStart, createdAt, status = 'temp', ownerUserId = null }) {
  const start = typeof windowStart === 'string' ? windowStart : new Date(createdAt ?? Date.now()).toISOString();
  return {
    id,
    referralId: referralId ?? null,
    status,
    activationTick,
    windowStart: start,
    windowEnd: new Date(new Date(start).getTime() + ONE_YEAR_MS).toISOString(),
    verificationState: 'pending',
    verifiedTick: null,
    grabDay: null,
    discarded: false,
    createdAt: createdAt ?? start,
    ownerUserId: ownerUserId ?? null,
  };
}

function isNonEmptyString(v) {
  return typeof v === 'string' && v.length > 0;
}

/**
 * A temp record for activation — the yield intake's server-side
 * construction (POST /temp/activate). The client supplies id /
 * referralId; the SERVER assigns the activation tick (never the
 * client — ticks are the causal order and must be monotonic and
 * never re-numbered) and the window (windowStart + 1 year).
 * Built on newTempRecord, then validated by the caller with
 * validateTempRecord before it is stored. referralId null means
 * no referral — the record activates and the grab will mark it
 * not_verified (no_referral); the intake does not reject it.
 */
export function newActivationRecord({ id, referralId = null, activationTick, windowStart, nowMs = Date.now(), ownerUserId = null }) {
  const start = typeof windowStart === 'string' ? windowStart : new Date(nowMs).toISOString();
  return newTempRecord({
    id,
    referralId,
    activationTick,
    windowStart: start,
    createdAt: new Date(nowMs).toISOString(),
    ownerUserId,
  });
}

function isIsoString(v) {
  return typeof v === 'string' && !Number.isNaN(Date.parse(v));
}

/**
 * Validate + normalize a stored temp record to the spec §3.2 shape.
 * Anything unrecognised is rejected (ok: false, error named) —
 * a bad record never enters the store silently. Unknown extra
 * fields are dropped; the returned record is a NEW object.
 */
export function validateTempRecord(record) {
  if (!record || typeof record !== 'object' || Array.isArray(record)) {
    return { ok: false, record: null, error: 'record must be an object' };
  }
  if (!isNonEmptyString(record.id)) {
    return { ok: false, record: null, error: 'id must be a non-empty string' };
  }
  if (
    record.referralId !== null &&
    record.referralId !== undefined &&
    !isNonEmptyString(record.referralId)
  ) {
    return { ok: false, record: null, error: 'referralId must be a non-empty string or null' };
  }
  if (!TEMP_STATUSES.includes(record.status)) {
    return { ok: false, record: null, error: `status must be one of ${TEMP_STATUSES.join(', ')}` };
  }
  if (
    typeof record.activationTick !== 'number' ||
    !Number.isFinite(record.activationTick) ||
    record.activationTick < 0 ||
    !Number.isInteger(record.activationTick)
  ) {
    return { ok: false, record: null, error: 'activationTick must be a non-negative integer' };
  }
  if (!isIsoString(record.windowStart) || !isIsoString(record.windowEnd)) {
    return { ok: false, record: null, error: 'windowStart/windowEnd must be ISO timestamps' };
  }
  if (Date.parse(record.windowEnd) <= Date.parse(record.windowStart)) {
    return { ok: false, record: null, error: 'windowEnd must be after windowStart' };
  }
  if (!VERIFICATION_STATES.includes(record.verificationState)) {
    return { ok: false, record: null, error: `verificationState must be one of ${VERIFICATION_STATES.join(', ')}` };
  }
  if (
    record.verifiedTick !== null &&
    (typeof record.verifiedTick !== 'number' ||
      !Number.isFinite(record.verifiedTick) ||
      record.verifiedTick < 0 ||
      !Number.isInteger(record.verifiedTick))
  ) {
    return { ok: false, record: null, error: 'verifiedTick must be a non-negative integer or null' };
  }
  if (record.grabDay !== null && !isIsoString(record.grabDay)) {
    return { ok: false, record: null, error: 'grabDay must be a UTC date string or null' };
  }
  if (typeof record.discarded !== 'boolean') {
    return { ok: false, record: null, error: 'discarded must be a boolean' };
  }
  if (!isIsoString(record.createdAt)) {
    return { ok: false, record: null, error: 'createdAt must be an ISO timestamp' };
  }
  if (
    record.ownerUserId !== null &&
    record.ownerUserId !== undefined &&
    !isNonEmptyString(record.ownerUserId)
  ) {
    return { ok: false, record: null, error: 'ownerUserId must be a non-empty string or null' };
  }
  // A verified record must carry its stamp; a pending record must not.
  if (record.verificationState === 'verified' && record.verifiedTick === null) {
    return { ok: false, record: null, error: 'a verified record must carry verifiedTick' };
  }
  if (record.verificationState !== 'verified' && record.verifiedTick !== null) {
    return { ok: false, record: null, error: 'only a verified record may carry verifiedTick' };
  }
  return {
    ok: true,
    record: {
      id: record.id,
      referralId: record.referralId ?? null,
      status: record.status,
      activationTick: record.activationTick,
      windowStart: record.windowStart,
      windowEnd: record.windowEnd,
      verificationState: record.verificationState,
      verifiedTick: record.verifiedTick ?? null,
      grabDay: record.grabDay ?? null,
      discarded: record.discarded,
      createdAt: record.createdAt,
      ownerUserId: record.ownerUserId ?? null,
    },
    error: null,
  };
}

/**
 * The grab's chain check (spec §1.2), pure: no storage I/O.
 *
 * @param {object} record — a validated temp record.
 * @param {number} nowMs — the grab moment (unix ms).
 * @param {string|null} referrerState — the referrer's verification
 *   state as the scan knows it: 'verified' | 'pending' |
 *   'not_verified' | 'missing' (referralId points at no record),
 *   'genesis' (the record is the genesis root — its referral is
 *   'ref:genesis' and its tick is the root tick, so the referrer
 *   is verified by definition), 'genesis_not_root' (the record
 *   claims 'ref:genesis' but is not the root tick), or null when
 *   the record carries no referralId at all.
 *   The scan resolves this from the outcome log / the referrer's
 *   record stub, in activation-tick order, before calling this.
 * @returns {{ outcome, reason }} — outcome is one of GRAB_OUTCOMES.
 *   'skip' means already verified: leave the record untouched.
 *
 * Check order (spec §1.2, steps in order):
 *   (d) already verified -> skip (never re-verify, never re-number)
 *   (b) discarded -> expired (stops counting, never verified later)
 *   (c) past the 1-year window -> expired
 *   (a) no referral id, or the referral link is broken -> not_verified
 *   (a) genesis claim but not the root tick -> not_verified
 *   (a) referrer exists but is not yet verified -> pending
 *   (a) genesis root, or referrer verified -> verified
 */
export function checkChain(record, nowMs, referrerState) {
  if (record.verificationState === 'verified') {
    return { outcome: 'skip', reason: 'already_verified' };
  }
  if (record.discarded) {
    return { outcome: 'expired', reason: 'discarded' };
  }
  if (nowMs > Date.parse(record.windowEnd)) {
    return { outcome: 'expired', reason: 'window_expired' };
  }
  if (!record.referralId) {
    return { outcome: 'not_verified', reason: 'no_referral' };
  }
  if (referrerState === 'genesis_not_root') {
    return { outcome: 'not_verified', reason: 'genesis_not_root' };
  }
  if (referrerState === 'missing') {
    return { outcome: 'not_verified', reason: 'referral_broken' };
  }
  if (referrerState !== 'verified' && referrerState !== 'genesis') {
    return { outcome: 'pending', reason: 'referrer_pending' };
  }
  return { outcome: 'verified', reason: referrerState === 'genesis' ? 'genesis_root' : 'chain_holds' };
}

/**
 * Apply a grab outcome to a record. Pure: returns a NEW record,
 * the input is untouched. Only 'verified' stamps verifiedTick /
 * grabDay — and only once: applying 'verified' to an already
 * verified record returns the record unchanged (the tick is never
 * re-numbered). 'pending' leaves the record as pending (no stamp).
 * 'not_verified' flips verificationState; 'expired' flips it and
 * keeps the record (it stops counting, it is not deleted).
 */
export function applyOutcome(record, outcome, tick, grabDay) {
  if (outcome === 'skip') return { ...record };
  if (outcome === 'verified') {
    if (record.verificationState === 'verified') return { ...record };
    return {
      ...record,
      status: record.status === 'temp' || record.status === 'unverified' ? 'verified' : record.status,
      verificationState: 'verified',
      verifiedTick: tick,
      grabDay,
    };
  }
  if (outcome === 'pending') {
    return { ...record, verificationState: 'pending' };
  }
  if (outcome === 'not_verified') {
    return { ...record, verificationState: 'not_verified' };
  }
  if (outcome === 'expired') {
    return { ...record, verificationState: 'not_verified' };
  }
  throw new Error(`unknown grab outcome: ${outcome}`);
}

/**
 * Index queue key for an activation tick. Zero-padded to 16 digits
 * so lexicographic key order IS activation-tick order — the DO
 * storage list({ prefix: 'q:' }) then walks the queue in order
 * with no sort step. Ticks beyond 10^16 would break the padding;
 * at one tick per temp that is 10 quadrillion temps, not a real
 * bound for this design.
 */
export function queueKey(tick) {
  return `q:${String(tick).padStart(16, '0')}`;
}

/** Inverse of queueKey: the activation tick for a queue key, or null. */
export function parseQueueKey(key) {
  const m = /^q:(\d{16})$/.exec(key);
  return m ? Number(m[1]) : null;
}

/** Outcome-log key for a grab tick + temp id. */
export function outcomeKey(tick, id) {
  return `o:${String(tick).padStart(16, '0')}:${id}`;
}

/** Inverse of outcomeKey: { tick, id }, or null. */
export function parseOutcomeKey(key) {
  const m = /^o:(\d{16}):(.+)$/.exec(key);
  return m ? { tick: Number(m[1]), id: m[2] } : null;
}

/**
 * Outcome-log value. The log is the causal record of the grab,
 * so each entry carries not just the outcome but the grab day
 * it was decided and the reason why — the publish step (FixNet
 * Pages) and any audit read the log, and a bare outcome does not
 * say why a temp failed. Compact JSON: {"o":"verified",
 * "d":"2026-11-16","r":"chain_holds"}. day and reason are
 * optional (null when absent); a legacy plain-outcome value
 * ("verified") parses as { outcome, day: null, reason: null }.
 */
export function outcomeValue(outcome, day = null, reason = null) {
  return JSON.stringify({
    o: outcome,
    d: typeof day === 'string' && day ? day : null,
    r: typeof reason === 'string' && reason ? reason : null,
  });
}

/**
 * Inverse of outcomeValue. Accepts both the JSON form and a
 * legacy plain-outcome string. Returns { outcome, day, reason }
 * with day/reason null when absent. Never throws: an
 * unparseable value is read as a legacy outcome string when it
 * is one of the known outcomes, else { outcome: null, day: null,
 * reason: null }.
 */
export function parseOutcomeValue(value) {
  if (typeof value !== 'string') return { outcome: null, day: null, reason: null };
  if (!value.startsWith('{')) {
    return GRAB_OUTCOMES.includes(value)
      ? { outcome: value, day: null, reason: null }
      : { outcome: null, day: null, reason: null };
  }
  try {
    const parsed = JSON.parse(value);
    if (!parsed || typeof parsed !== 'object') return { outcome: null, day: null, reason: null };
    return {
      outcome: GRAB_OUTCOMES.includes(parsed.o) ? parsed.o : null,
      day: typeof parsed.d === 'string' && parsed.d ? parsed.d : null,
      reason: typeof parsed.r === 'string' && parsed.r ? parsed.r : null,
    };
  } catch {
    return { outcome: null, day: null, reason: null };
  }
}

/**
 * Queue value for an entry (step 2 of the dailies — the grab).
 * Compact string `id|referralId` (referralId empty when null):
 * the driver learns the referralId from the queue page, so it
 * never needs a separate /get per record to resolve the
 * referrer — the /get was 20% of the step-1 scan's cost. The
 * `|` separator cannot appear in an id: profile ids are
 * `profile-<uuid>` ([A-Za-z0-9-] only) and 'ref:genesis' has no
 * `|` either. A plain id with no `|` parses as referralId null
 * (the step-1 seed wrote bare ids — still readable).
 *
 * DISCARD (the done marker): when the grab applies a terminal
 * outcome to a record, /log-batch rewrites its queue value as
 * `id|referralId|done:<outcome>` — the queue entry is DISCARDED
 * from the nightly walk (the driver skips done entries: no
 * referrer /get, no /apply, no tally), while the KEY stays in
 * place. The key must stay: the grab's stopping rule reads an
 * empty page as "no later ticks exist" (activation ticks are a
 * dense monotonic counter), so DELETING a queue entry would end
 * a grab early and skip live records. Marking keeps the density
 * and the causal record (the outcome log and the record stub
 * are untouched — the record is never deleted).
 */
export function queueValue(id, referralId, done = null) {
  const base = `${id}|${referralId ?? ''}`;
  return done === null || done === undefined ? base : `${base}|done:${done}`;
}

/**
 * Inverse of queueValue: { id, referralId, done }, or null when
 * malformed. done is null for a live entry, or the terminal
 * outcome that discarded it. A done marker for a non-terminal
 * outcome ('done:pending', 'done:skip') is malformed — pending
 * is never discarded, skip is never logged.
 */
export function parseQueueValue(value) {
  if (typeof value !== 'string' || !value) return null;
  const parts = value.split('|');
  if (parts.length === 1) return { id: value, referralId: null, done: null };
  if (parts.length === 2) {
    return { id: parts[0], referralId: parts[1] === '' ? null : parts[1], done: null };
  }
  if (parts.length === 3 && parts[2].startsWith('done:')) {
    const done = parts[2].slice(5);
    if (!TERMINAL_OUTCOMES.includes(done)) return null;
    return { id: parts[0], referralId: parts[1] === '' ? null : parts[1], done };
  }
  return null;
}
