/**
 * Chain progress reporting — pure functions, no Cloudflare APIs.
 *
 * Gary's rule (2026-11-10): progress reporting is EVENT-DRIVEN and
 * must NEVER eat neurons.
 *
 *   Event-driven: a progress update is PUSHED only when an event
 *   happens — a training step/milestone completes, a chain step
 *   finishes, a status changes. There is NO polling loop anywhere:
 *   nothing checks on a timer. The trainer posts from its log
 *   callback (an event the trainer itself fires), batched so it
 *   never posts more often than a sane minimum interval. The admin
 *   pulls the progress on demand with a single GET when they ask —
 *   that is a pull, not a poll.
 *
 *   Zero neurons, zero SP: the progress endpoints are plain data
 *   operations (Durable Object reads and writes). They NEVER call
 *   Workers AI, never go through the chat-completions path, and
 *   never touch the per-user SP bucket. Reading or writing progress
 *   costs 0 SP and 0 neurons. The Worker routes them before the AI
 *   path so they cannot accidentally invoke the model.
 *
 * The correct split (Gary, 2026-11-10 — correction): the heavy work
 * does NOT go on the neuron side. The neuron side (Workers AI /
 * ping server) only handles a PASS — a lightweight inference
 * request. Training is heavy compute and lives on the GPU side
 * (Colab T4). So:
 *
 *   * GPU side (training) — the heavy work. It COMPUTES its own
 *     progress (percent, ETA, ASCII bar) and pushes it, event-driven.
 *     It is the queryable source of truth for its own progress.
 *   * Neuron side (this Worker) — only a pass. It STORES what the
 *     training side reported and SERVES it on demand. It is a plain
 *     pass-through: it NEVER computes progress (no percent
 *     derivation, no bar rendering, no ETA math), never trains, and
 *     never does inference for progress. It only validates the shape
 *     (bounds-checks) and stores/serves the values verbatim.
 *   * Lucid (client) — lightweight. It just sends one GET that
 *     passes to the neuron side. The only strain on Lucid is that
 *     request. It does not compute, store, or poll progress.
 *
 * Shared by worker.js (the PingProgress Durable Object) and
 * progress.test.mjs (Node unit tests). The server is the sole
 * authority on the CURRENT stored progress: nothing about it is
 * computed or enforced anywhere else — but the VALUES it stores
 * were computed on the training side, not here.
 *
 * One record, one global stub ('progress:current'):
 *   { stage, status, step, total, percent, bar, loss, eta_seconds,
 *     run_id, message, updated_at_ms }
 * The record is overwritten by each update (latest wins) — there is
 * no history, no per-step log. An admin reads the latest state.
 *
 * Stages (the training chain, in order): train, merge, gguf, gate,
 * r2, manifest, client. `idle` means no chain is running; `done`
 * means the chain finished. Unknown stage strings are accepted
 * (bounded length) so a future step can report without a code
 * change, but the known list is the contract.
 */

export const PROGRESS_STAGES = [
  'train',
  'merge',
  'gguf',
  'gate',
  'r2',
  'manifest',
  'client',
  'idle',
  'done',
];

export const PROGRESS_STATUSES = ['running', 'completed', 'failed', 'idle'];

// Max length for the ASCII bar string the training side sends.
// The neuron side stores it verbatim (bounded), it never renders it.
export const BAR_MAX_LEN = 64;

/** Clamp a number to [min, max]; non-finite input becomes `fallback`. */
function clampNumber(value, min, max, fallback) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return fallback;
  if (value < min) return min;
  if (value > max) return max;
  return value;
}

/** A bounded string (max length, trimmed); anything else becomes `fallback`. */
function boundedString(value, maxLen, fallback) {
  if (typeof value !== 'string') return fallback;
  const s = value.trim();
  if (!s) return fallback;
  return s.length > maxLen ? s.slice(0, maxLen) : s;
}

/**
 * Validate + normalize a raw POST body into the stored progress
 * record. Unknown/extra fields are dropped (the stored shape is
 * fixed). Returns { ok: true, record } or { ok: false, error }.
 * `nowMs` is the server timestamp (the record's updated_at_ms) —
 * the reporter never supplies its own clock.
 *
 * PASS-THROUGH: the percent, bar, and ETA are taken VERBATIM from
 * what the training side reported (clamped/bounded only). This
 * function NEVER derives a percent from step/total, NEVER forces
 * 100% on completed, and NEVER renders a bar — that computation
 * lives on the GPU/training side (scripts/training/progress.py).
 * If the reporter did not send a percent/bar, they stay null/''.
 */
export function sanitizeProgressUpdate(body, nowMs) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    return { ok: false, error: 'progress body must be a JSON object' };
  }
  const stage = boundedString(body.stage, 64, null);
  if (!stage) {
    return { ok: false, error: 'progress.stage is required (a non-empty string, e.g. "train")' };
  }
  const statusRaw = boundedString(body.status, 32, 'running');
  const status = PROGRESS_STATUSES.includes(statusRaw) ? statusRaw : 'running';

  const step =
    typeof body.step === 'number' && Number.isFinite(body.step) && body.step >= 0
      ? Math.floor(body.step)
      : 0;
  const total =
    typeof body.total === 'number' && Number.isFinite(body.total) && body.total > 0
      ? Math.floor(body.total)
      : null;
  // Percent and bar are taken verbatim from the training side
  // (clamped/bounded only). The neuron side never computes them.
  const percent = clampNumber(body.percent, 0, 100, null);
  const bar = boundedString(body.bar, BAR_MAX_LEN, '');

  const loss =
    typeof body.loss === 'number' && Number.isFinite(body.loss) && body.loss >= 0
      ? body.loss
      : null;
  const etaSeconds =
    typeof body.eta_seconds === 'number' && Number.isFinite(body.eta_seconds) && body.eta_seconds >= 0
      ? Math.round(body.eta_seconds)
      : null;

  return {
    ok: true,
    record: {
      stage,
      status,
      step,
      total,
      percent: percent === null ? null : Math.round(percent * 10) / 10,
      bar,
      loss,
      eta_seconds: etaSeconds,
      run_id: boundedString(body.run_id, 128, null),
      message: boundedString(body.message, 500, null),
      updated_at_ms: nowMs,
    },
  };
}

/**
 * The public progress view (what GET /admin/progress returns), or
 * null when no progress has ever been reported. Returns the stored
 * values verbatim (the bar is the one the training side sent), plus
 * the age of the record (seconds since the last update) so an admin
 * can tell at a glance whether the number is fresh or stale. Age is
 * freshness metadata about the report, not progress computation.
 */
export function progressView(record, nowMs) {
  if (!record || typeof record !== 'object') return null;
  const updatedAtMs =
    typeof record.updated_at_ms === 'number' && Number.isFinite(record.updated_at_ms)
      ? record.updated_at_ms
      : nowMs;
  return {
    stage: record.stage ?? null,
    status: record.status ?? null,
    step: typeof record.step === 'number' ? record.step : 0,
    total: typeof record.total === 'number' ? record.total : null,
    percent: typeof record.percent === 'number' ? record.percent : null,
    bar: typeof record.bar === 'string' ? record.bar : '',
    loss: typeof record.loss === 'number' ? record.loss : null,
    eta_seconds: typeof record.eta_seconds === 'number' ? record.eta_seconds : null,
    run_id: record.run_id ?? null,
    message: record.message ?? null,
    updated_at: new Date(updatedAtMs).toISOString(),
    age_seconds: Math.max(0, Math.floor((nowMs - updatedAtMs) / 1000)),
  };
}
