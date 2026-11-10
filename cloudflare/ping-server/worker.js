/**
 * Lucid ping server — Cloudflare Worker.
 *
 * The first working test dummy for the Lucid -> Cloudflare -> model ->
 * stream path. The Worker is global edge by nature: that IS the
 * "global user connect stream". The stream is the SSE token stream
 * from the model.
 *
 * Routes:
 *   GET  /                      — service card (JSON, public).
 *   POST /ping                  — health + echo. Body JSON, any shape;
 *                                returns { ok, service, model, mode, ts,
 *                                echo, quota? }. NOT metered: it is the
 *                                health probe, and it reports the
 *                                caller's remaining quota for free.
 *   POST /v1/chat/completions  — OpenAI-compatible. Body
 *                                { messages: [{role, content}], model?,
 *                                stream? }. model names a Workers AI
 *                                model from the PING_MODELS allowlist;
 *                                absent or unknown falls back to the
 *                                default model. stream:true (default)
 *                                returns SSE
 *                                `data: {choices:[{delta:{content}}]}`
 *                                chunks ending in `data: [DONE]`;
 *                                stream:false returns the OpenAI JSON
 *                                shape. No tools: the dummy model does
 *                                not do tool calls, and the request is
 *                                rejected with 400 if `tools` is present.
 *                                Every model costs 1 SP per request.
 *   POST /admin/progress       — a chain step reports a progress
 *                                event (train/merge/gguf/gate/r2/
 *                                manifest/client). Body { stage,
 *                                status?, step?, total?, percent?,
 *                                loss?, eta_seconds?, run_id?,
 *                                message? }. Admin key required.
 *                                0 neurons, 0 SP — plain DO write.
 *   GET  /admin/progress       — the queryable training-side
 *                                endpoint: the current progress
 *                                (stage, status, step, total,
 *                                percent, bar, loss, ETA, run_id,
 *                                message, age). Admin key required.
 *                                On-demand pull, 0 neurons, 0 SP —
 *                                plain DO read. Lucid is a thin
 *                                client here: one lightweight GET,
 *                                the neuron side answers.
 *
 * Auth (dummy): a shared-secret header. If the worker has a
 * PING_SHARED_SECRET secret set (wrangler secret put), /ping and
 * /v1/chat/completions require `x-lucid-ping-key: <secret>` and
 * answer 401 without it. If no secret is set, the routes are open —
 * this is a test dummy, never a production gate.
 *
 * Identity + quota: a per-user token bucket of SP (stock points).
 * 1 SP per /v1/chat/completions request; SP are like credits — the
 * balance is the user's credit balance. The quota keys off
 * `x-lucid-user`: a per-install id the Lucid client generates once (a
 * random UUID, stored in settings) and sends on every request. It is
 * NOT an account — there is no registration, no PII, and rotating it
 * resets the quota (dummy-grade identity, documented honestly).
 * /v1/chat/completions requires the header (400 without it). The
 * bucket lives in a Durable Object (one stub per user id), in DO
 * storage — see bucket.js. New users start at 100 SP. Refills, two
 * stages, decided by the balance at refill time: below 200 SP, +25 SP
 * every 4 hours, cap 200; at or above 200 SP, +20 SP every 12 hours,
 * cap 250 — so an idle user climbs 200 → 220 → 240 → 250 and no user
 * can ever hold more than 250 SP. If the balance drops below 200
 * through use, refills go back to +25/4h, cap 200, until it reaches
 * 200 again. POST /ping is the registration / health check: it costs
 * 0 SP, never deducts, never 429s — it only reports the SP balance.
 * When the bucket is empty the Worker answers 429 with the limit
 * (the user's current cap, 200 or 250), the next-refill time (unix
 * seconds + seconds until refill), and a Retry-After header — and
 * every chat response carries x-ratelimit-limit /
 * x-ratelimit-remaining / x-ratelimit-reset headers. The server is the
 * sole authority on quota: nothing about it is computed or enforced
 * anywhere else. Old UTC-day state ({ count, day }) migrates on first
 * request after deploy: the remaining balance carries into the bucket,
 * nobody's quota is wiped.
 *
 * Maintenance mode (Gary's rule, 2026-11-07): if a SERVER-side cap
 * is ever hit — the neurons maxed out (10,000/day Workers AI free
 * tier) or the Workers request limit hit (100,000/day) — the server
 * goes down for 24 hours for maintenance. A second Durable Object
 * (PingServerUsage, one global stub) counts chat completions and
 * estimated neurons per UTC day; either cap trips maintenance, and
 * so does an AI error whose message says the quota/neurons are
 * exhausted. In maintenance, POST /v1/chat/completions answers 503
 * with the reason and the return time and spends NO SP; GET / and
 * POST /ping keep working and report the maintenance state honestly.
 * The window is 24 hours from the trip moment (not a calendar day)
 * and expiry is derived from time, so the Worker resumes by itself
 * and a restart/redeploy cannot clear the state. See
 * maintenance.js for the cap math, the estimation honesty note
 * (usage counts when present, ~4 chars/token otherwise), and the
 * known wart (the request that trips the reactive trigger has
 * already spent 1 SP — no refund).
 *
 * Model: the client picks one with body.model on
 * POST /v1/chat/completions. The worker serves any model on the
 * PING_MODELS allowlist — which, by Gary's decision (2026-11-06),
 * holds ONLY Llama 3.2 1B (neurons, 10,000/day, are the only quota
 * that matters for scaling, and 1B is the only model we can support
 * at the user numbers we want within that budget). A body.model
 * that is absent, not a string, or not on the allowlist falls back
 * to the default, env.MODEL (wrangler [vars]), default
 * @cf/meta/llama-3.2-1b-instruct — verified on the official
 * Workers AI pricing page 2026-11-06 as the cheapest Llama chat
 * model listed (2,457 neurons / M input tokens, 18,252 / M
 * output). Free allocation is 10,000 neurons/day, no card. The
 * allowlist is a hard gate: an arbitrary client-supplied string is
 * never passed to the AI binding. Every model costs the same 1 SP
 * per chat completion request — the SP bucket does not vary by
 * model, and POST /ping is still unmetered.
 *
 * Mock mode: under local `wrangler dev` the AI binding exists but
 * `AI.run()` throws "Binding AI needs to be run remotely" — the real
 * binding only works on the edge. The Worker catches exactly that
 * error and answers from a clearly-labelled mock: response header
 * `x-lucid-ping-mock: true`, and the streamed text itself starts with
 * a [mock reply ...] marker. Any other AI error is a loud 502, never
 * a silent mock. The mock proves the HTTP + SSE shape end to end; it
 * does NOT prove the model call. The real model call is only proven
 * after deploy (see README.md). The `mode` field on GET / and /ping
 * reports binding presence (live when env.AI exists); the
 * x-lucid-ping-mock header on a chat response is the ground truth
 * for which path actually served that reply.
 */

import { SP_INITIAL, peekBucket, spendBucket } from './bucket.js';
import {
  MAINTENANCE_MS,
  NEURON_DAILY_CAP,
  REQUEST_DAILY_CAP,
  maintenanceResponseBody,
  maintenanceView,
  migrateServerRecord,
  neuronsForRequest,
  recordUsage,
  rollDay,
  tripMaintenance,
} from './maintenance.js';
import {
  progressView,
  sanitizeProgressUpdate,
} from './progress.js';

const DEFAULT_MODEL = '@cf/meta/llama-3.2-1b-instruct';
const SERVICE = 'lucid-ping-server';
const VERSION = '0.4.0';

/**
 * All Workers AI text-generation models the ping server serves.
 *
 * Gary's decision (2026-11-06): ONLY Llama 3.2 1B. Neurons
 * (10,000/day, Cloudflare free tier) are the only quota that
 * matters for scaling, and the 1B is the only model we can support
 * for the user numbers we want (200-1000 users) within that budget
 * — the bigger models (70B, 120B, etc.) burn too many neurons to
 * support that scale. The other 33 models from the Cloudflare
 * catalog snapshot (fetched 2026-11-06) were removed from this
 * allowlist and from the Lucid client's dropdown. The default
 * (Llama 3.2 1B) is the only entry — it is DEFAULT_MODEL, and it
 * is also on this list.
 */
export const PING_MODELS = [
  '@cf/meta/llama-3.2-1b-instruct',
];

/**
 * Resolve which model serves a chat request. The client picks one
 * with body.model; only an exact allowlist match is honoured. An
 * absent, non-string, or unknown model falls back to the configured
 * default (env.MODEL, else DEFAULT_MODEL) — never a 400, never an
 * arbitrary client string passed to the AI binding.
 */
export function resolveModel(body, env) {
  const requested = body && typeof body.model === 'string' ? body.model : null;
  if (requested && PING_MODELS.includes(requested)) return requested;
  return (env && env.MODEL) || DEFAULT_MODEL;
}

const CORS_HEADERS = {
  'access-control-allow-origin': '*',
  'access-control-allow-methods': 'GET, POST, OPTIONS',
  'access-control-allow-headers': 'content-type, x-lucid-ping-key, x-lucid-user',
  'access-control-max-age': '86400',
  'vary': 'origin',
};

const JSON_HEADERS = { 'content-type': 'application/json; charset=utf-8', ...CORS_HEADERS };
const SSE_HEADERS = {
  'content-type': 'text/event-stream; charset=utf-8',
  'cache-control': 'no-cache',
  'connection': 'keep-alive',
  'x-accel-buffering': 'no',
  ...CORS_HEADERS,
};

/**
 * Per-user token bucket (SP — stock points). One stub per user id
 * (idFromName), so users never share a bucket and never block each
 * other. State is one record { balance, lastRefill } — see bucket.js
 * for the refill math, the two stages, and migration from the old
 * { count, day } shape.
 *
 * DO storage note: state lives in the DO's own storage, so it
 * survives isolate restarts and is consistent per user — unlike an
 * in-memory Map (per-isolate, resets on eviction) or KV (eventual
 * consistency, racy increments). This is Cloudflare's own documented
 * rate-limiting shape.
 */
export class PingRateLimiter {
  constructor(state) {
    this.state = state;
  }

  async fetch(request) {
    const url = new URL(request.url);
    const nowMs = Date.now();
    const record = (await this.state.storage.get('quota')) || null;

    if (url.pathname === '/peek') {
      // Non-consuming read: /ping reports the SP balance for free.
      // A peek never spends SP and never persists anything.
      const { view } = peekBucket(record, nowMs);
      return new Response(JSON.stringify({ ok: true, ...view }), {
        headers: { 'content-type': 'application/json' },
      });
    }

    if (url.pathname === '/check') {
      // Consuming check: spend 1 SP if any remain.
      const { state, allowed, view } = spendBucket(record, nowMs);
      await this.state.storage.put('quota', state);
      return new Response(
        JSON.stringify({ ok: true, allowed, ...view }),
        { headers: { 'content-type': 'application/json' } },
      );
    }

    return new Response(JSON.stringify({ ok: false, error: 'unknown limiter route' }), {
      status: 404,
      headers: { 'content-type': 'application/json' },
    });
  }
}

/**
 * Server-wide usage + maintenance state (one global stub, id
 * 'server:usage'). State is one record
 * { day, requests, neurons, maintenance } in DO storage — see
 * maintenance.js for the cap math, the 24h window, and the day
 * rollover. The Worker is the only caller (via serverUsageCall);
 * there is no public route to this DO. Pure logic lives in
 * maintenance.js, so this class is a thin storage wrapper, like
 * PingRateLimiter — and unit-testable in Node with fake storage.
 *
 * Routes (all POST, JSON bodies):
 *   /status — read-only view: { day, requests, neurons,
 *             maintenance } where maintenance is the public view
 *             or null. Rolls the day (persisted only when the day
 *             actually changed); never creates state on a bare read.
 *   /record { neurons } — one finished chat completion: +1
 *             request, +neurons estimate. Trips maintenance when a
 *             cap is reached. Returns { tripped, reason,
 *             maintenance, requests, neurons }.
 *   /trip { reason, detail } — enter maintenance immediately (the
 *             reactive trigger: the AI platform said the quota is
 *             exhausted). A second trip while active does not reset
 *             the clock. Returns { maintenance }.
 */
export class PingServerUsage {
  constructor(state) {
    this.state = state;
  }

  async fetch(request) {
    const url = new URL(request.url);
    const nowMs = Date.now();
    const record = (await this.state.storage.get('usage')) || null;

    if (url.pathname === '/status') {
      if (!record) {
        // Bare read on a fresh DO: report the fresh view without
        // creating state — a status check must not write.
        const fresh = migrateServerRecord(null, nowMs);
        return new Response(
          JSON.stringify({
            ok: true,
            day: fresh.day,
            requests: 0,
            neurons: 0,
            maintenance: null,
          }),
          { headers: { 'content-type': 'application/json' } },
        );
      }
      const state = rollDay(migrateServerRecord(record, nowMs), nowMs);
      if (state.day !== record.day) {
        await this.state.storage.put('usage', state);
      }
      return new Response(
        JSON.stringify({
          ok: true,
          day: state.day,
          requests: state.requests,
          neurons: state.neurons,
          maintenance: maintenanceView(state.maintenance, nowMs),
        }),
        { headers: { 'content-type': 'application/json' } },
      );
    }

    if (url.pathname === '/record') {
      let body = {};
      try {
        body = await request.json();
      } catch {
        body = {};
      }
      const neurons =
        typeof body.neurons === 'number' && Number.isFinite(body.neurons) && body.neurons >= 0
          ? body.neurons
          : 0;
      const { state, tripped, reason } = recordUsage(
        migrateServerRecord(record, nowMs),
        neurons,
        nowMs,
      );
      await this.state.storage.put('usage', state);
      return new Response(
        JSON.stringify({
          ok: true,
          tripped,
          reason,
          maintenance: maintenanceView(state.maintenance, nowMs),
          requests: state.requests,
          neurons: state.neurons,
        }),
        { headers: { 'content-type': 'application/json' } },
      );
    }

    if (url.pathname === '/trip') {
      let body = {};
      try {
        body = await request.json();
      } catch {
        body = {};
      }
      const reason = body.reason === 'requests_exhausted' ? 'requests_exhausted' : 'neurons_exhausted';
      const detail = typeof body.detail === 'string' ? body.detail : '';
      const state = tripMaintenance(migrateServerRecord(record, nowMs), reason, detail, nowMs);
      await this.state.storage.put('usage', state);
      return new Response(
        JSON.stringify({ ok: true, maintenance: maintenanceView(state.maintenance, nowMs) }),
        { headers: { 'content-type': 'application/json' } },
      );
    }

    return new Response(JSON.stringify({ ok: false, error: 'unknown usage route' }), {
      status: 404,
      headers: { 'content-type': 'application/json' },
    });
  }
}

/**
 * Chain progress state (one global stub, id 'progress:current').
 * State is one record
 * { stage, status, step, total, percent, loss, eta_seconds,
 *   run_id, message, updated_at_ms } in DO storage — see progress.js
 * for the shape, the validation, and the ASCII bar.
 *
 * Event-driven (Gary's rule, 2026-11-10): an update is PUSHED only
 * when a chain step reports an event (a training step/milestone
 * completes, a step finishes, a status changes). There is no
 * polling loop anywhere — nothing checks on a timer. The admin
 * pulls the current state on demand with GET /admin/progress (a
 * single pull, not a poll).
 *
 * Zero neurons, zero SP: this is a plain data operation (DO read /
 * write). It NEVER calls Workers AI, never goes through the
 * chat-completions path, and never touches the per-user SP bucket.
 * Reading or writing progress costs 0 SP and 0 neurons.
 *
 * Routes (all POST, JSON bodies):
 *   /update { stage, status?, step?, total?, percent?, loss?,
 *             eta_seconds?, run_id?, message? } — validate +
 *             store (latest wins, no history). Returns the stored
 *             progress view. Bad body -> 400.
 *   /status — read-only view: the stored progress view, or null
 *             when nothing has ever been reported. Never creates
 *             state on a bare read.
 */
export class PingProgress {
  constructor(state) {
    this.state = state;
  }

  async fetch(request) {
    const url = new URL(request.url);
    const nowMs = Date.now();

    if (url.pathname === '/status') {
      const record = (await this.state.storage.get('progress')) || null;
      return new Response(
        JSON.stringify({ ok: true, progress: progressView(record, nowMs) }),
        { headers: { 'content-type': 'application/json' } },
      );
    }

    if (url.pathname === '/update') {
      let body = {};
      try {
        body = await request.json();
      } catch {
        return new Response(JSON.stringify({ ok: false, error: 'invalid JSON body' }), {
          status: 400,
          headers: { 'content-type': 'application/json' },
        });
      }
      const { ok, record, error } = sanitizeProgressUpdate(body, nowMs);
      if (!ok) {
        return new Response(JSON.stringify({ ok: false, error }), {
          status: 400,
          headers: { 'content-type': 'application/json' },
        });
      }
      await this.state.storage.put('progress', record);
      return new Response(
        JSON.stringify({ ok: true, progress: progressView(record, nowMs) }),
        { headers: { 'content-type': 'application/json' } },
      );
    }

    return new Response(JSON.stringify({ ok: false, error: 'unknown progress route' }), {
      status: 404,
      headers: { 'content-type': 'application/json' },
    });
  }
}

function jsonResponse(status, body, extraHeaders = {}) {
  return new Response(JSON.stringify(body, null, 2), {
    status,
    headers: { ...JSON_HEADERS, ...extraHeaders },
  });
}

function errorResponse(status, error, extraHeaders = {}) {
  return jsonResponse(status, { ok: false, error }, extraHeaders);
}

/** Shared-secret gate. Open when no secret is configured (dummy). */
function authorized(request, env) {
  const secret = env.PING_SHARED_SECRET;
  if (!secret) return true;
  const supplied = request.headers.get('x-lucid-ping-key');
  return supplied === secret;
}

/** Per-install user id from the x-lucid-user header, or null. */
function userId(request) {
  const id = request.headers.get('x-lucid-user');
  if (!id || id.length > 128 || !/^[A-Za-z0-9._-]+$/.test(id)) return null;
  return id;
}

function mode(env) {
  return env.AI ? 'live' : 'mock';
}

function rateLimitHeaders(quota) {
  return {
    'x-ratelimit-limit': String(quota.limit),
    'x-ratelimit-remaining': String(quota.remaining),
    'x-ratelimit-reset': String(quota.reset),
  };
}

/** Talk to the caller's Durable Object stub. `spend` = true consumes one request. */
async function quotaFor(env, id, spend) {
  if (!env.RATE_LIMITER) {
    throw new Error('rate limiter binding (RATE_LIMITER) is not configured');
  }
  const stub = env.RATE_LIMITER.get(env.RATE_LIMITER.idFromName(`user:${id}`));
  const res = await stub.fetch(
    new Request(`http://limiter/${spend ? 'check' : 'peek'}`, { method: 'POST' }),
  );
  if (!res.ok) throw new Error(`rate limiter error: HTTP ${res.status}`);
  return res.json();
}

/**
 * Talk to the single global server-usage stub. Fail-open: a missing
 * binding or a DO error returns null, and the caller treats null as
 * "no maintenance known" — a broken usage counter must never take
 * the server down by itself, and a missing binding must not 503
 * the health endpoints.
 */
async function serverUsageCall(env, path, body) {
  if (!env.SERVER_USAGE) return null;
  try {
    const stub = env.SERVER_USAGE.get(env.SERVER_USAGE.idFromName('server:usage'));
    const res = await stub.fetch(
      new Request(`http://usage${path}`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: body ? JSON.stringify(body) : undefined,
      }),
    );
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

/**
 * Talk to the single global progress stub. Fail-open: a missing
 * binding or a DO error returns null, and the caller answers 503 —
 * a broken progress store must never take the chat path down, and
 * the progress endpoints are separate routes that never touch AI.
 * A DO 4xx (e.g. a bad update body) still returns its JSON body,
 * so the caller can pass the 400 through instead of masking it
 * as a 503.
 */
async function progressCall(env, path, body) {
  if (!env.PROGRESS) return null;
  try {
    const stub = env.PROGRESS.get(env.PROGRESS.idFromName('progress:current'));
    const res = await stub.fetch(
      new Request(`http://progress${path}`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: body ? JSON.stringify(body) : undefined,
      }),
    );
    try {
      return await res.json();
    } catch {
      return null;
    }
  } catch {
    return null;
  }
}

/** The public maintenance view, or null when not in maintenance (or unknown). */
async function maintenanceCheck(env) {
  const status = await serverUsageCall(env, '/status');
  return status ? status.maintenance : null;
}

/** Record one finished chat completion (fire-and-forget safe: never throws). */
async function recordServerUsage(env, neurons) {
  try {
    await serverUsageCall(env, '/record', { neurons });
  } catch {
    // Usage accounting is best-effort telemetry; a failed record
    // must never fail the request it describes.
  }
}

/**
 * Enter maintenance now (the reactive trigger). Returns the public
 * maintenance view, or null if the DO could not be reached — in
 * which case the caller builds a fallback view from the trip
 * moment itself, so the current request still reports maintenance
 * even when persistence failed.
 */
async function tripServerMaintenance(env, reason, detail) {
  const res = await serverUsageCall(env, '/trip', { reason, detail });
  if (res && res.maintenance) return res.maintenance;
  const nowMs = Date.now();
  return maintenanceView(
    { reason, detail, startedAtMs: nowMs, endsAtMs: nowMs + MAINTENANCE_MS },
    nowMs,
  );
}

/** The 503 maintenance answer for a chat request. Spends no SP. */
function maintenance503(view) {
  return jsonResponse(503, maintenanceResponseBody(view), {
    'retry-after': String(view.back_in_seconds),
    'x-lucid-maintenance': 'true',
  });
}

/**
 * Best-effort platform signal: does this AI error say the
 * server-side quota is exhausted? The exact platform string is
 * unverified (it only appears on the live edge, never in local
 * dev), so the match is deliberately narrow — neuron / quota /
 * exceeding / daily-limit language — and the proactive estimate
 * is the primary trigger. A match here only fires on the AI-call
 * path, never on other errors.
 */
function isCapError(err) {
  const msg = err instanceof Error ? err.message : String(err);
  return /neuron/i.test(msg) || /quota/i.test(msg) || /exceed/i.test(msg) || /daily limit/i.test(msg);
}

/** Last user message, for the mock echo. */
function lastUserText(messages) {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m && m.role === 'user' && typeof m.content === 'string') return m.content;
  }
  return '';
}

function mockText(messages) {
  const echo = lastUserText(messages).slice(0, 200);
  return `[mock reply — no Workers AI binding in local dev] You said: ${echo || '(nothing)'}`;
}

function sseChunk(content) {
  return `data: ${JSON.stringify({ choices: [{ index: 0, delta: { content } }] })}\n\n`;
}

/** Mock SSE stream: one content chunk, then [DONE]. */
function mockStream(text) {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(sseChunk(text)));
      controller.enqueue(encoder.encode('data: [DONE]\n\n'));
      controller.close();
    },
  });
}

/**
 * Transform a raw Workers AI SSE stream into OpenAI-format SSE.
 *
 * Workers AI streams `data: {"response":"...","p":"...","usage":{...}}`
 * chunks; the Lucid client parses `choices[0].delta.content`, so each
 * chunk's `response` text is rewritten through sseChunk(). Lines arrive
 * split across chunk boundaries, so the transform buffers to whole
 * lines; a line that is not JSON, or JSON without `response` text
 * (e.g. a usage-only chunk), is dropped — the stream never dies on
 * one bad line. The upstream `data: [DONE]` is passed through; if the
 * stream ends without one, it is emitted here so the client always
 * sees the terminator.
 */
function openAiStream(aiStream, hooks = {}) {
  const encoder = new TextEncoder();
  const decoder = new TextDecoder();
  let buffer = '';
  let doneSent = false;
  // Usage accounting for the maintenance estimate: streamed output
  // chars (the neuron estimate falls back to these when the platform
  // sends no usage object) and the usage object itself when a chunk
  // carries one. Reported once, in flush(), via hooks.onDone — the
  // stream never waits on it and a hook failure never breaks the
  // reply.
  let outputChars = 0;
  let usage = null;

  const handleLine = (line, controller) => {
    if (!line) return;
    const payload = line.startsWith('data:') ? line.slice('data:'.length).trim() : line;
    if (payload === '[DONE]') {
      if (!doneSent) {
        controller.enqueue(encoder.encode('data: [DONE]\n\n'));
        doneSent = true;
      }
      return;
    }
    let parsed;
    try {
      parsed = JSON.parse(payload);
    } catch {
      return; // not JSON — drop the line, never crash the stream
    }
    if (parsed && typeof parsed.usage === 'object' && parsed.usage !== null) {
      usage = parsed.usage;
    }
    if (parsed && typeof parsed.response === 'string' && parsed.response) {
      outputChars += parsed.response.length;
      controller.enqueue(encoder.encode(sseChunk(parsed.response)));
    }
    // Chunks without response text (e.g. usage-only) are dropped.
  };

  return aiStream.pipeThrough(
    new TransformStream({
      transform(chunk, controller) {
        buffer += decoder.decode(chunk, { stream: true });
        let idx;
        while ((idx = buffer.indexOf('\n')) >= 0) {
          const line = buffer.slice(0, idx).trim();
          buffer = buffer.slice(idx + 1);
          handleLine(line, controller);
        }
      },
      flush(controller) {
        if (buffer.trim()) handleLine(buffer.trim(), controller);
        if (!doneSent) controller.enqueue(encoder.encode('data: [DONE]\n\n'));
        if (typeof hooks.onDone === 'function') {
          try {
            hooks.onDone({ outputChars, usage });
          } catch {
            // Accounting must never break the stream.
          }
        }
      },
    }),
  );
}

function openAiJson(model, content) {
  return {
    id: `chatcmpl-ping-${Date.now()}`,
    object: 'chat.completion',
    created: Math.floor(Date.now() / 1000),
    model,
    choices: [
      {
        index: 0,
        message: { role: 'assistant', content },
        finish_reason: 'stop',
      },
    ],
    usage: null,
  };
}

/**
 * Chain progress — the queryable training-side endpoint.
 *
 * The GPU training side is QUERYABLE (Gary, 2026-11-10): an admin
 * (or Lucid) asks for the progress and the neuron side answers.
 * Lucid stays a thin client — it just sends one lightweight GET
 * that passes to the neuron side. The only strain on Lucid is that
 * request. Lucid does NOT compute, store, or poll progress, and it
 * never carries the training load; the heavy work (training,
 * progress computation) stays on the neuron side, and the ping
 * server is the queryable source of truth for its own progress.
 *
 * Plain data operations (0 neurons, 0 SP): these handlers never
 * call Workers AI, never go through the chat-completions path, and
 * never touch the per-user SP bucket. They read/write the progress
 * Durable Object only. They are routed before the AI path so they
 * cannot accidentally invoke the model.
 *
 * Auth: the shared secret (x-lucid-ping-key), the same key as
 * /ping and /v1/chat/completions — the admin key. 401 without it.
 * POST /admin/progress — a chain step reports an event (a training
 *   step/milestone completed, a step finished, a status changed).
 *   Body: { stage, status?, step?, total?, percent?, loss?,
 *   eta_seconds?, run_id?, message? }. Returns the stored view.
 *   Bad body -> 400. DO unreachable -> 503. The reporter
 *   (trainer) never blocks on this and never fails if it errors.
 * GET /admin/progress — on-demand pull: one lightweight GET, the
 *   current progress view, or progress: null when nothing has ever
 *   been reported. DO unreachable -> 503.
 */
async function handleProgressPost(request, env) {
  if (!authorized(request, env)) {
    return errorResponse(401, 'unauthorized: missing or wrong x-lucid-ping-key');
  }
  let body;
  try {
    body = await request.json();
  } catch {
    return errorResponse(400, 'invalid JSON body');
  }
  const res = await progressCall(env, '/update', body);
  if (!res) {
    return errorResponse(503, 'progress store unavailable');
  }
  if (!res.ok) {
    return errorResponse(400, res.error || 'invalid progress update');
  }
  return jsonResponse(200, { ok: true, progress: res.progress });
}

async function handleProgressGet(request, env) {
  if (!authorized(request, env)) {
    return errorResponse(401, 'unauthorized: missing or wrong x-lucid-ping-key');
  }
  const res = await progressCall(env, '/status');
  if (!res) {
    return errorResponse(503, 'progress store unavailable');
  }
  return jsonResponse(200, { ok: true, progress: res.progress });
}

async function handlePing(request, env) {
  if (!authorized(request, env)) {
    return errorResponse(401, 'unauthorized: missing or wrong x-lucid-ping-key');
  }
  let echo = null;
  try {
    echo = await request.json();
  } catch {
    echo = null; // empty body is fine — /ping is a health check
  }
  const body = {
    ok: true,
    service: SERVICE,
    version: VERSION,
    model: env.MODEL || DEFAULT_MODEL,
    mode: mode(env),
    ai_binding: Boolean(env.AI),
    ts: new Date().toISOString(),
    echo,
    quota: null,
    // Maintenance state, honestly reported: null when the server is
    // up (or unknown), the view object while in maintenance. /ping
    // answers 200 in maintenance too — it is the health check.
    maintenance: null,
  };
  // Maintenance state is a best-effort read: a missing binding or a
  // DO error leaves it null (unknown), never a 503 — /ping must
  // always answer.
  try {
    body.maintenance = await maintenanceCheck(env);
  } catch {
    body.maintenance = null;
  }
  // Free quota lookup for the caller, when they identify themselves.
  // /ping never spends SP — it is the registration / health check.
  const id = userId(request);
  if (id) {
    try {
      const q = await quotaFor(env, id, false);
      body.quota = {
        limit: q.limit,
        remaining: q.remaining,
        reset: q.reset,
        reset_in_seconds: q.reset_in_seconds,
        stock_points: q.remaining,
      };
    } catch (err) {
      return errorResponse(503, `rate limiter unavailable: ${err instanceof Error ? err.message : String(err)}`);
    }
  }
  return jsonResponse(200, body);
}

async function handleChatCompletions(request, env, ctx) {
  if (!authorized(request, env)) {
    return errorResponse(401, 'unauthorized: missing or wrong x-lucid-ping-key');
  }
  // Maintenance pre-check: a server in maintenance answers 503 and
  // spends NO SP — the request never reaches the per-user bucket.
  // The check is best-effort (null = unknown = proceed as normal).
  const maint = await maintenanceCheck(env);
  if (maint) {
    return maintenance503(maint);
  }
  // Background work (stream usage recording) runs via waitUntil
  // when the runtime provides it; otherwise fire-and-forget.
  const schedule = (promise) => {
    const guarded = Promise.resolve(promise).catch(() => {});
    if (ctx && typeof ctx.waitUntil === 'function') {
      try {
        ctx.waitUntil(guarded);
      } catch {
        // fall through — the guarded promise still runs
      }
    }
  };
  const id = userId(request);
  if (!id) {
    return errorResponse(
      400,
      'x-lucid-user header required: a per-install id (any 1-128 char [A-Za-z0-9._-] token). The Lucid client generates one once and stores it in settings.',
    );
  }

  let body;
  try {
    body = await request.json();
  } catch {
    return errorResponse(400, 'invalid JSON body');
  }
  if (body.tools !== undefined) {
    return errorResponse(400, 'tools are not supported by the ping server dummy model');
  }
  const messages = body.messages;
  if (!Array.isArray(messages) || messages.length === 0) {
    return errorResponse(400, 'messages must be a non-empty array');
  }
  for (const m of messages) {
    if (!m || typeof m.role !== 'string' || typeof m.content !== 'string') {
      return errorResponse(400, 'each message needs a string role and string content');
    }
  }
  const stream = body.stream !== false; // streaming is the default
  // The client picks a model with body.model; only an exact
  // allowlist match is honoured, otherwise the configured default.
  // SP is charged per request, not per model — 1 SP either way.
  const model = resolveModel(body, env);
  // Prompt size for the neuron estimate (the stream path only has
  // character counts, not token counts — see maintenance.js).
  const promptChars = messages.reduce(
    (n, m) => n + (typeof m.content === 'string' ? m.content.length : 0),
    0,
  );

  // --- Quota: spend 1 SP before any model work. ---
  let quota;
  try {
    quota = await quotaFor(env, id, true);
  } catch (err) {
    return errorResponse(503, `rate limiter unavailable: ${err instanceof Error ? err.message : String(err)}`);
  }
  if (!quota.allowed) {
    return jsonResponse(
      429,
      {
        ok: false,
        error: `rate limit exceeded: 0 SP remaining (cap ${quota.limit} SP; next refill in ${quota.reset_in_seconds}s)`,
        limit: quota.limit,
        remaining: 0,
        reset: quota.reset,
        reset_in_seconds: quota.reset_in_seconds,
      },
      { ...rateLimitHeaders(quota), 'retry-after': String(quota.reset_in_seconds) },
    );
  }
  const headers = rateLimitHeaders(quota);

  // --- Mock mode: the AI binding exists under local wrangler dev but
  // AI.run() throws "Binding AI needs to be run remotely". Catch
  // exactly that error and answer from the labelled mock. ---
  const isLocalDevError = (err) => /needs to be run remotely/i.test(err instanceof Error ? err.message : String(err));

  if (!env.AI) {
    const text = mockText(messages);
    // Mock replies spend no neurons (no model ran), but the request
    // still counts toward the daily request cap.
    await recordServerUsage(env, 0);
    if (stream) {
      return new Response(mockStream(text), {
        status: 200,
        headers: { ...SSE_HEADERS, ...headers, 'x-lucid-ping-mock': 'true' },
      });
    }
    return jsonResponse(200, openAiJson(model, text), { ...headers, 'x-lucid-ping-mock': 'true' });
  }

  // --- Live mode: Workers AI on the edge. ---
  try {
    if (stream) {
      const aiStream = await env.AI.run(model, { messages, stream: true });
      const out = openAiStream(aiStream, {
        // Record the estimated neuron cost when the stream ends.
        // waitUntil keeps the Worker alive for it; the reply never
        // waits on the accounting.
        onDone: ({ outputChars, usage }) => {
          schedule(
            recordServerUsage(
              env,
              neuronsForRequest({ promptChars, outputChars, usage }),
            ),
          );
        },
      });
      return new Response(out, {
        status: 200,
        headers: { ...SSE_HEADERS, ...headers, 'x-lucid-ping-mock': 'false' },
      });
    }
    const result = await env.AI.run(model, { messages });
    const content =
      typeof result === 'object' && result !== null && typeof result.response === 'string'
        ? result.response
        : JSON.stringify(result);
    await recordServerUsage(
      env,
      neuronsForRequest({
        promptChars,
        outputText: content,
        usage:
          typeof result === 'object' && result !== null && typeof result.usage === 'object'
            ? result.usage
            : null,
      }),
    );
    return jsonResponse(200, openAiJson(model, content), { ...headers, 'x-lucid-ping-mock': 'false' });
  } catch (err) {
    if (isLocalDevError(err)) {
      // Local dev only: the binding is present but inert. Labelled mock.
      const text = mockText(messages);
      await recordServerUsage(env, 0);
      if (stream) {
        return new Response(mockStream(text), {
          status: 200,
          headers: { ...SSE_HEADERS, ...headers, 'x-lucid-ping-mock': 'true' },
        });
      }
      return jsonResponse(200, openAiJson(model, text), { ...headers, 'x-lucid-ping-mock': 'true' });
    }
    if (isCapError(err)) {
      // Reactive trigger: the platform says the server-side cap is
      // exhausted. Trip maintenance for 24h and answer 503 — the
      // server stops serving instead of 502ing every request until
      // the day rolls over. (The 1 SP for this request was already
      // spent before the model call; there is no refund — the refill
      // covers it within hours. See maintenance.js.)
      const view = await tripServerMaintenance(
        env,
        'neurons_exhausted',
        `workers-ai error: ${err instanceof Error ? err.message : String(err)}`,
      );
      return maintenance503(view);
    }
    // Quota / model / upstream failure: loud 502, never a fake reply.
    // (The request was already spent against the SP bucket.)
    return errorResponse(502, `workers-ai error: ${err instanceof Error ? err.message : String(err)}`, headers);
  }
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    if (url.pathname === '/' && request.method === 'GET') {
      // Maintenance state is a best-effort read: null when the
      // server is up (or the usage DO is unreachable).
      let maint = null;
      try {
        maint = await maintenanceCheck(env);
      } catch {
        maint = null;
      }
      return jsonResponse(200, {
        ok: true,
        service: SERVICE,
        version: VERSION,
        model: env.MODEL || DEFAULT_MODEL,
        models: PING_MODELS,
        mode: mode(env),
        ai_binding: Boolean(env.AI),
        maintenance: maint,
        quota: {
          unit: 'SP',
          unit_name: 'stock points',
          initial: SP_INITIAL,
          stage_1: { refill: 25, period_hours: 4, cap: 200 },
          stage_2: { refill: 20, period_hours: 12, cap: 250, applies_when: 'balance >= 200' },
        },
        server_caps: {
          neurons_per_day: NEURON_DAILY_CAP,
          requests_per_day: REQUEST_DAILY_CAP,
          maintenance_hours: MAINTENANCE_MS / 3600000,
          note: 'When a server-side cap is hit, the server goes down for 24 hours for maintenance (503, no SP spent) instead of serving degraded.',
        },
        routes: [
          'GET /',
          'POST /ping',
          'POST /v1/chat/completions',
          'POST /admin/progress',
          'GET /admin/progress',
        ],
        progress: {
          note: 'Chain progress (train -> merge -> gguf -> gate -> r2 -> manifest -> client). Event-driven pushes from the chain steps; queryable on demand via GET /admin/progress (admin key). 0 neurons, 0 SP — plain Durable Object reads/writes, never Workers AI.',
        },
      });
    }

    if (url.pathname === '/ping' && request.method === 'POST') {
      return handlePing(request, env);
    }

    // Chain progress (queryable, 0 neurons, 0 SP — plain DO
    // reads/writes, routed before the AI path so they can never
    // invoke the model). See handleProgressPost/handleProgressGet.
    if (url.pathname === '/admin/progress' && request.method === 'POST') {
      return handleProgressPost(request, env);
    }

    if (url.pathname === '/admin/progress' && request.method === 'GET') {
      return handleProgressGet(request, env);
    }

    if (url.pathname === '/v1/chat/completions' && request.method === 'POST') {
      return handleChatCompletions(request, env, ctx);
    }

    return errorResponse(404, `not found: ${request.method} ${url.pathname}`);
  },
};
