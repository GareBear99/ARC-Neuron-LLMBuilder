/**
 * Server-side cap tracking + 24-hour maintenance mode — pure
 * functions, no Cloudflare APIs.
 *
 * Shared by worker.js (the server-usage Durable Object) and
 * maintenance.test.mjs / serverUsage.test.mjs (Node unit tests).
 *
 * Gary's rule (2026-11-07): if a server-side cap is ever hit — the
 * neurons maxed out, the Workers request limit hit — the server goes
 * down for 24 hours for maintenance, instead of continuing degraded
 * or hammering a maxed-out cap. The maintenance window is 24 hours
 * from the moment the cap was hit (not a calendar day), and after
 * it the Worker automatically resumes normal service.
 *
 * The caps (Gary's numbers, unchanged — do not invent new ones):
 *   Neurons:  10,000/day (Cloudflare Workers AI free tier).
 *              Llama 3.2 1B: 2,457 neurons / M input tokens,
 *              18,252 / M output tokens.
 *   Requests: 100,000/day (Cloudflare Workers Free tier). Counted
 *              here as chat completions only (the metered path);
 *              GET / and POST /ping are unmetered health endpoints
 *              and are not counted, so this counter is a lower
 *              bound on total Worker invocations.
 *
 * How a cap hit is detected (two triggers, either one trips it):
 *   1. Proactive estimate: every chat completion records its
 *      estimated neuron cost in the server-usage DO. The estimate
 *      uses the AI response `usage` token counts when the platform
 *      provides them, and falls back to a character-based estimate
 *      (~4 chars per token, the standard approximation) for
 *      streaming replies, where usage is often absent. Estimates
 *      are kept fractional (never rounded up per request) so a day
 *      of tiny requests is not over-counted 10x. This is an
 *      ESTIMATE, said plainly: it trips at or near the real cap,
 *      not exactly on it.
 *   2. Reactive platform signal: if `env.AI.run()` throws an error
 *      whose message mentions neurons / quota / exceeding the daily
 *      limit, the Worker treats that as the cap being hit and trips
 *      maintenance immediately. The exact platform error string is
 *      unverified (it only appears on the live edge, never in local
 *      dev), so the match is best-effort and the estimate above is
 *      the primary trigger.
 *
 * What maintenance does:
 *   - POST /v1/chat/completions answers 503 with a JSON body
 *     (reason, when the server is back, Retry-After) and spends
 *     NO SP — the request never reaches the per-user bucket.
 *   - GET / and POST /ping keep working and report the maintenance
 *     state honestly (GET /: `maintenance` field; /ping: same field
 *     in the body). /ping still costs 0 SP and never 429s.
 *   - The state lives in the server-usage Durable Object
 *     (DO storage), so a Worker restart or redeploy does not clear
 *     it. Expiry is derived from time (now < endsAt), never from a
 *     cleanup job — so there is no job to miss.
 *   - The daily counters reset on UTC-day rollover, but an active
 *     maintenance window survives the rollover until its 24 hours
 *     are up.
 *   - A second trip while already in maintenance does NOT reset
 *     the clock: the original start time stands.
 *
 * Known wart, documented honestly: the request that trips the
 * reactive trigger has already spent 1 SP (the SP spend happens
 * before the model call, by design — quota is enforced before
 * work). There is no refund; the refill (+25 SP / 4h) covers it
 * within hours. Requests rejected by the maintenance pre-check
 * spend nothing.
 */

export const MAINTENANCE_MS = 24 * 3600 * 1000; // 24 hours
export const NEURON_DAILY_CAP = 10000; // Workers AI free tier
export const REQUEST_DAILY_CAP = 100000; // Workers Free tier
export const NEURONS_PER_M_INPUT = 2457; // Llama 3.2 1B
export const NEURONS_PER_M_OUTPUT = 18252; // Llama 3.2 1B
export const CHARS_PER_TOKEN = 4; // standard approximation

export const MAINTENANCE_REASONS = ['neurons_exhausted', 'requests_exhausted'];

export const REASON_DETAIL = {
  neurons_exhausted:
    'estimated neuron usage reached the 10,000/day Workers AI free-tier cap',
  requests_exhausted:
    'chat completions reached the 100,000/day Workers free-tier cap',
};

/** UTC date string, e.g. "2026-11-07" — the neuron/request day. */
export function utcDay(nowMs = Date.now()) {
  return new Date(nowMs).toISOString().slice(0, 10);
}

/** Tokens from characters: ~4 chars per token, rounded up. */
export function estimateTokensFromChars(chars) {
  if (!chars || chars <= 0) return 0;
  return Math.ceil(chars / CHARS_PER_TOKEN);
}

/** Exact neuron cost for known token counts. */
export function neuronsForTokens(promptTokens, completionTokens) {
  return (
    (promptTokens / 1e6) * NEURONS_PER_M_INPUT +
    (completionTokens / 1e6) * NEURONS_PER_M_OUTPUT
  );
}

/** Neuron cost estimated from character counts (streaming path). */
export function estimateNeurons(inputChars, outputChars) {
  return neuronsForTokens(
    estimateTokensFromChars(inputChars),
    estimateTokensFromChars(outputChars),
  );
}

/**
 * Neuron cost from an AI response `usage` object
 * ({ prompt_tokens, completion_tokens }), or null when the usage
 * is missing or unusable — the caller falls back to the character
 * estimate in that case.
 */
export function neuronsFromUsage(usage) {
  if (!usage || typeof usage !== 'object') return null;
  const p = usage.prompt_tokens;
  const c = usage.completion_tokens;
  if (typeof p !== 'number' || typeof c !== 'number') return null;
  if (!Number.isFinite(p) || !Number.isFinite(c) || p < 0 || c < 0) return null;
  return neuronsForTokens(p, c);
}

/**
 * Neuron cost for one chat completion: the `usage` token counts
 * when the platform provided them, else the character estimate
 * from the prompt text (or `promptChars`) and the reply text (or
 * `outputChars`).
 */
export function neuronsForRequest({ promptText = '', promptChars = 0, outputText = '', outputChars = 0, usage = null }) {
  const fromUsage = neuronsFromUsage(usage);
  if (fromUsage !== null) return fromUsage;
  const inChars = promptText ? promptText.length : promptChars;
  const outChars = outputText ? outputText.length : outputChars;
  return estimateNeurons(inChars, outChars);
}

/** A fresh server-usage record for the given moment. */
export function newServerState(nowMs) {
  return { day: utcDay(nowMs), requests: 0, neurons: 0, maintenance: null };
}

function validMaintenance(m) {
  return (
    m &&
    typeof m === 'object' &&
    MAINTENANCE_REASONS.includes(m.reason) &&
    typeof m.startedAtMs === 'number' &&
    Number.isFinite(m.startedAtMs) &&
    typeof m.endsAtMs === 'number' &&
    Number.isFinite(m.endsAtMs) &&
    m.endsAtMs > m.startedAtMs &&
    typeof m.detail === 'string'
  );
}

/**
 * Migrate a stored server-usage record to the current shape.
 * Anything unrecognised (or no record) starts fresh — counters at
 * zero, no maintenance. A stored record keeps its counters (clamped
 * to >= 0) and its maintenance window if it is well-formed.
 */
export function migrateServerRecord(record, nowMs) {
  if (
    record &&
    typeof record.day === 'string' &&
    typeof record.requests === 'number' &&
    Number.isFinite(record.requests) &&
    typeof record.neurons === 'number' &&
    Number.isFinite(record.neurons)
  ) {
    return {
      day: record.day,
      requests: Math.max(0, Math.floor(record.requests)),
      neurons: Math.max(0, record.neurons),
      maintenance: validMaintenance(record.maintenance) ? record.maintenance : null,
    };
  }
  return newServerState(nowMs);
}

/** True while the maintenance window is still running. */
export function isMaintenanceActive(maintenance, nowMs) {
  return Boolean(
    maintenance && typeof maintenance.endsAtMs === 'number' && nowMs < maintenance.endsAtMs,
  );
}

/**
 * Roll the counters to a new UTC day. Counters reset; an ACTIVE
 * maintenance window survives the rollover until its 24 hours are
 * up. An expired window is dropped.
 */
export function rollDay(state, nowMs) {
  const today = utcDay(nowMs);
  if (state.day === today) return state;
  return {
    day: today,
    requests: 0,
    neurons: 0,
    maintenance: isMaintenanceActive(state.maintenance, nowMs) ? state.maintenance : null,
  };
}

/**
 * The public maintenance view: null when inactive, else the reason
 * and the return time. `started_at` / `back_at` are ISO strings;
 * `back_in_seconds` counts down to zero.
 */
export function maintenanceView(maintenance, nowMs) {
  if (!isMaintenanceActive(maintenance, nowMs)) return null;
  return {
    active: true,
    reason: maintenance.reason,
    reason_detail: maintenance.detail,
    started_at: new Date(maintenance.startedAtMs).toISOString(),
    back_at: new Date(maintenance.endsAtMs).toISOString(),
    back_in_seconds: Math.max(0, Math.floor((maintenance.endsAtMs - nowMs) / 1000)),
  };
}

/**
 * Enter maintenance. A second trip while already in maintenance
 * does NOT reset the clock — the original start time stands.
 * Returns a NEW state; the input is untouched.
 */
export function tripMaintenance(state, reason, detail, nowMs) {
  const rolled = rollDay(state, nowMs);
  if (isMaintenanceActive(rolled.maintenance, nowMs)) return rolled;
  const safeReason = MAINTENANCE_REASONS.includes(reason) ? reason : 'neurons_exhausted';
  return {
    ...rolled,
    maintenance: {
      reason: safeReason,
      detail: typeof detail === 'string' && detail ? detail : REASON_DETAIL[safeReason],
      startedAtMs: nowMs,
      endsAtMs: nowMs + MAINTENANCE_MS,
    },
  };
}

/**
 * Record one finished chat completion: +1 request, +`neurons`
 * estimated neurons. Trips maintenance when a cap is reached.
 * Returns { state, tripped, reason } — reason is null unless the
 * call tripped maintenance. While already in maintenance the
 * counters still advance (they are factual) but the window is
 * never reset or extended.
 */
export function recordUsage(state, neurons, nowMs) {
  const rolled = rollDay(state, nowMs);
  const next = {
    ...rolled,
    requests: rolled.requests + 1,
    neurons: rolled.neurons + (typeof neurons === 'number' && Number.isFinite(neurons) && neurons > 0 ? neurons : 0),
  };
  if (isMaintenanceActive(next.maintenance, nowMs)) {
    return { state: next, tripped: false, reason: null };
  }
  if (next.neurons >= NEURON_DAILY_CAP) {
    return {
      state: tripMaintenance(next, 'neurons_exhausted', REASON_DETAIL.neurons_exhausted, nowMs),
      tripped: true,
      reason: 'neurons_exhausted',
    };
  }
  if (next.requests >= REQUEST_DAILY_CAP) {
    return {
      state: tripMaintenance(next, 'requests_exhausted', REASON_DETAIL.requests_exhausted, nowMs),
      tripped: true,
      reason: 'requests_exhausted',
    };
  }
  return { state: next, tripped: false, reason: null };
}

/**
 * The 503 maintenance response body, built from a maintenance
 * view (see maintenanceView). `retry_after` matches
 * `back_in_seconds` so clients can honour it as a header too.
 */
export function maintenanceResponseBody(view) {
  return {
    ok: false,
    error: `maintenance: server down for maintenance — ${view.reason_detail}; back at ${view.back_at}`,
    maintenance: view,
    retry_after: view.back_in_seconds,
  };
}
