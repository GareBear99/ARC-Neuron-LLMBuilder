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
 *   POST /register              — per-install key provisioning (Fix 2).
 *                                Body { userId }. Mints ONE key per
 *                                user id (re-issue returns the same
 *                                key) and returns { ok, key }. No auth
 *                                — it is the provisioning endpoint for
 *                                a client with no key stored. 0 neurons,
 *                                0 SP.
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
 * Per-install keys (Fix 2): POST /register mints one key per
 * install (the per-install user id), stored server-side in that
 * user's limiter DO. A per-install key is accepted alongside the
 * shared secret on /ping, /v1/chat/completions and /temp/activate
 * only — never on /admin/* (those stay shared-secret-only). The
 * default ping server therefore works without manual key entry:
 * a fresh install registers once and stores the minted key.
 * One key per user id, re-issue returns the same key — that is
 * the registration rate limit.
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

import { SP_INITIAL, migrateRecord, peekBucket, quotaView, spendBucket } from './bucket.js';
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
import {
  GENESIS_REFERRAL_ID,
  applyOutcome,
  checkChain,
  genesisReferrerState,
  isTerminalOutcome,
  newActivationRecord,
  newRotationRecord,
  outcomeKey,
  outcomeValue,
  parseOutcomeKey,
  parseOutcomeValue,
  parseQueueKey,
  parseQueueValue,
  queueKey,
  queueValue,
  utcDay,
  validateTempRecord,
} from './tempstore.js';
import {
  GRAB_BATCH_CONCURRENCY,
  GRAB_CHUNK_RECORDS,
  GRAB_CPU_BUDGET_MS,
  GRAB_DAILY_CAP,
  GRAB_LOG_BATCH,
  GRAB_QUEUE_PAGE,
  GRAB_SHARD_WIDTH,
  GRAB_SUBREQUEST_LIMIT,
  GRAB_TIMEZONE,
  chunkRange,
  compareCursors,
  grabDayFor,
  isGrabHour,
  newGrabState,
  shardForTick,
  shardRange,
  shardStubId,
  validateGrabCursor,
  validateGrabState,
} from './grab.js';

const DEFAULT_MODEL = '@cf/meta/llama-3.2-1b-instruct';
const SERVICE = 'lucid-ping-server';
const VERSION = '0.8.1';

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

    if (url.pathname === '/verify') {
      // Mark this user's bucket verified: the grab recognised
      // their temp (FixNet step 2). Verified is sticky — once
      // true it never goes back to false. The grant itself
      // (+1000 SP/day, no cap) is applied by applyRefill on the
      // next /peek or /check, so this route only flips the flag
      // and persists it; it grants nothing by itself. Called by
      // the Worker (runGrabChunk / handleTempActivate), never by
      // a client directly — a client cannot verify itself.
      const state = migrateRecord(record, nowMs);
      state.verified = true;
      await this.state.storage.put('quota', state);
      return new Response(
        JSON.stringify({ ok: true, verified: true, ...quotaView(state, nowMs) }),
        { headers: { 'content-type': 'application/json' } },
      );
    }

    if (url.pathname === '/register-key') {
      // Per-install key registration (Fix 2 — the default ping
      // server works without manual key entry). One key per
      // user id, minted once and stored under 'key' (separate
      // from the 'quota' bucket record, so the bucket math in
      // bucket.js is untouched). Re-issue returns the SAME key
      // — that is the rate limit: a user id can never hold two
      // keys, and re-registering never rotates the key. Called
      // by the Worker (handleRegister), never by a client
      // directly — the client calls POST /register on the
      // Worker, which calls this route on the user's stub.
      const existing = await this.state.storage.get('key');
      if (typeof existing === 'string' && existing) {
        return new Response(JSON.stringify({ ok: true, key: existing }), {
          headers: { 'content-type': 'application/json' },
        });
      }
      const key = mintInstallKey();
      await this.state.storage.put('key', key);
      return new Response(JSON.stringify({ ok: true, key }), {
        headers: { 'content-type': 'application/json' },
      });
    }

    if (url.pathname === '/check-key') {
      // Read-only key check (Fix 2): does the supplied key
      // match this user's stored per-install key? Never mints,
      // never creates state on a bare read — a failed auth
      // attempt must not register a key for an arbitrary user
      // id. Called by the Worker (authorizedClient), never by
      // a client directly. Returns { ok, match } — the key
      // itself is never echoed back.
      let body = {};
      try {
        body = await request.json();
      } catch {
        body = {};
      }
      const stored = await this.state.storage.get('key');
      const match = keysEqual(body.key, stored);
      return new Response(JSON.stringify({ ok: true, match }), {
        headers: { 'content-type': 'application/json' },
      });
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

/**
 * One temp's record (one stub per temp, id `temp:<id>`).
 * State is one record in DO storage under key 'record' — the
 * spec §3.2 shape (id, referralId, status, activationTick,
 * windowStart, windowEnd, verificationState, verifiedTick,
 * grabDay, discarded, createdAt). Thin storage wrapper over the
 * pure logic in tempstore.js, like PingRateLimiter — and
 * unit-testable in Node with fake storage.
 *
 * No Worker route calls this DO yet: the grab (plan step 2) wires
 * the Worker to it. Step 1 is the store + the timed scan only.
 *
 * Routes (all POST, JSON bodies):
 *   /get — read-only: { record } or { record: null }. Never
 *          creates state on a bare read.
 *   /put { record } — validate + store. Bad record -> 400.
 *   /apply { nowMs, referrerState, tick, grabDay } — run the
 *          §1.2 chain check against the stored record and persist
 *          the outcome (verified stamps verifiedTick/grabDay once,
 *          never re-numbered). No record stored -> 404.
 *          Returns { outcome, reason, record }.
 *   /rotate { rotationTempId } — store the rotation pointer
 *          (FixNet temp rotation, design D2): this record yields
 *          the temp `rotationTempId` once verified. Set once,
 *          never overwritten — a re-run returns the existing
 *          pointer ({ already: true }) instead of forking a
 *          second rotation. No record stored -> 404; bad id ->
 *          400. Returns { ok, record, already }.
 */
export class TempRecord {
  constructor(state) {
    this.state = state;
  }

  async fetch(request) {
    const url = new URL(request.url);

    if (url.pathname === '/get') {
      const record = (await this.state.storage.get('record')) || null;
      return new Response(JSON.stringify({ ok: true, record }), {
        headers: { 'content-type': 'application/json' },
      });
    }

    if (url.pathname === '/put') {
      let body = {};
      try {
        body = await request.json();
      } catch {
        return new Response(JSON.stringify({ ok: false, error: 'invalid JSON body' }), {
          status: 400,
          headers: { 'content-type': 'application/json' },
        });
      }
      const { ok, record, error } = validateTempRecord(body.record);
      if (!ok) {
        return new Response(JSON.stringify({ ok: false, error }), {
          status: 400,
          headers: { 'content-type': 'application/json' },
        });
      }
      await this.state.storage.put('record', record);
      return new Response(JSON.stringify({ ok: true, record }), {
        headers: { 'content-type': 'application/json' },
      });
    }

    if (url.pathname === '/apply') {
      let body = {};
      try {
        body = await request.json();
      } catch {
        return new Response(JSON.stringify({ ok: false, error: 'invalid JSON body' }), {
          status: 400,
          headers: { 'content-type': 'application/json' },
        });
      }
      const record = (await this.state.storage.get('record')) || null;
      if (!record) {
        return new Response(JSON.stringify({ ok: false, error: 'no record stored' }), {
          status: 404,
          headers: { 'content-type': 'application/json' },
        });
      }
      const nowMs = typeof body.nowMs === 'number' ? body.nowMs : Date.now();
      const tick = typeof body.tick === 'number' ? body.tick : 0;
      const grabDay = typeof body.grabDay === 'string' ? body.grabDay : null;
      const referrerState =
        body.referrerState === 'verified' ||
        body.referrerState === 'pending' ||
        body.referrerState === 'not_verified' ||
        body.referrerState === 'missing' ||
        body.referrerState === 'genesis' ||
        body.referrerState === 'genesis_not_root'
          ? body.referrerState
          : null;
      const { outcome, reason } = checkChain(record, nowMs, referrerState);
      const next = applyOutcome(record, outcome, tick, grabDay);
      await this.state.storage.put('record', next);
      return new Response(
        JSON.stringify({ ok: true, outcome, reason, record: next }),
        { headers: { 'content-type': 'application/json' } },
      );
    }

    if (url.pathname === '/rotate') {
      let body = {};
      try {
        body = await request.json();
      } catch {
        return new Response(JSON.stringify({ ok: false, error: 'invalid JSON body' }), {
          status: 400,
          headers: { 'content-type': 'application/json' },
        });
      }
      const record = (await this.state.storage.get('record')) || null;
      if (!record) {
        return new Response(JSON.stringify({ ok: false, error: 'no record stored' }), {
          status: 404,
          headers: { 'content-type': 'application/json' },
        });
      }
      const rotationTempId = body.rotationTempId;
      if (typeof rotationTempId !== 'string' || !rotationTempId) {
        return new Response(
          JSON.stringify({ ok: false, error: 'rotationTempId must be a non-empty string' }),
          {
            status: 400,
            headers: { 'content-type': 'application/json' },
          },
        );
      }
      // The pointer is set once, never overwritten: a re-run
      // (a chunk that crashed after /rotate, or the backfill
      // endpoint) reuses the existing rotation instead of
      // forking a second one. The caller reads `record` for
      // the existing pointer.
      if (record.rotationTempId) {
        return new Response(JSON.stringify({ ok: true, record, already: true }), {
          headers: { 'content-type': 'application/json' },
        });
      }
      const next = { ...record, rotationTempId };
      await this.state.storage.put('record', next);
      return new Response(JSON.stringify({ ok: true, record: next, already: false }), {
        headers: { 'content-type': 'application/json' },
      });
    }

    return new Response(JSON.stringify({ ok: false, error: 'unknown temp record route' }), {
      status: 404,
      headers: { 'content-type': 'application/json' },
    });
  }
}

/**
 * The temp store's index (one stub per tick-range shard, id
 * 'temp:index:<shard>' — grab.js shardForTick; step 2 of the
 * dailies sharded the single 'temp:index' stub, which at 1B
 * would hold ~137 GB against the 10 GB per-DO limit). Each shard
 * holds its range's tick-ordered pending queue (queueKey(tick)
 * -> compact `id|referralId` value) and the per-grab outcome log
 * (outcomeKey(tick, id) -> outcome, latest outcome wins — one
 * entry per temp, so the log does not grow per grab). The index
 * is the causal record: the tick order lives here, and the grab
 * walks it. This settles plan Q4 — verification ticks are
 * server-side records in these index stubs, not in either of
 * Lucid's client rings. Thin storage wrapper over tempstore.js /
 * grab.js, like PingServerUsage.
 *
 * Queue keys are zero-padded (tempstore.js queueKey), so
 * storage.list({ prefix: 'q:' }) returns the queue in
 * activation-tick order with no sort step. The queue value
 * carries the referralId (tempstore.js queueValue) so the grab
 * driver learns it from the queue page and never needs a
 * separate /get per record to resolve the referrer.
 *
 * Routes (all POST, JSON bodies):
 *   /enqueue { activationTick, id, referralId? } — add a queue
 *             entry. Idempotent (same key overwrites). Bad body
 *             -> 400. referralId null/omitted = no referral.
 *   /queue — read-only: { entries: [{ activationTick, id,
 *            referralId, done }] } in tick order. Never creates
 *            state. done is null for a live entry, or the
 *            terminal outcome that discarded it (see below).
 *   /queue-range { startTick, endTick, limit? } — entries in
 *            tick order within [startTick, endTick], at most
 *            limit (default GRAB_QUEUE_PAGE, max the same — one
 *            DO response stays small). The grab driver pages
 *            this to walk a chunk. Entries carry done (null or
 *            the discarding outcome); the driver skips done
 *            entries — no referrer /get, no /apply, no tally.
 *   /log { tick, id, outcome, day?, reason? } — append an
 *            outcome-log entry. 'skip' is not an outcome and is
 *            rejected (400). day (the grab day, 'YYYY-MM-DD')
 *            and reason (why — chain_holds, genesis_root,
 *            no_referral, referrer_pending, ...) ride along
 *            when the caller supplies them, so the log is the
 *            audit record, not just the outcome. This route
 *            logs only; it does NOT mark the queue entry done
 *            (it is the manual single-entry route, not a grab
 *            step).
 *   /log-batch { entries: [{ tick, id, outcome, referralId?,
 *            day?, reason?, nextTemp? }] }
 *            — batch outcome writes (one call per chunk page
 *            instead of one per record). Idempotent by key; a
 *            bad entry rejects the whole batch (400, nothing
 *            written). nextTemp {id, tick} (FixNet temp rotation,
 *            design D4) rides a verified outcome — it is stored
 *            in the outcome value, so the publish can put
 *            next_temp on the verified status entry. DISCARD: for every entry whose outcome is
 *            terminal (verified / not_verified / expired), the
 *            batch ALSO rewrites that tick's queue value as
 *            `id|referralId|done:<outcome>` — the queue entry is
 *            discarded from the nightly walk (the driver skips
 *            it), while the KEY stays: the grab's stopping rule
 *            reads an empty page as "no later ticks exist", so
 *            deleting a queue entry would end a grab early.
 *            The outcome log and the record stub are untouched
 *            — a discarded record is never deleted. Pending
 *            outcomes mark nothing (a pending record is
 *            re-checked by every grab). 'skip' entries are
 *            accepted as MARKING-ONLY: a skip means the record
 *            was already verified (usually by a chunk that
 *            crashed before its /log-batch), so nothing is
 *            written to the outcome log, but the queue entry is
 *            marked done:verified — without this, a crashed
 *            chunk's records would be re-walked every night
 *            forever. EXCEPTION (rotation, design D3): a skip
 *            carrying nextTemp DOES write a log entry — as
 *            'verified' with reason 'already_verified' — because
 *            the crash that produced the skip also means the log
 *            has no verified entry for this temp yet, and the
 *            publish must still learn its next_temp. A skip
 *            without nextTemp writes nothing, as before.
 *            referralId, when the caller supplies it
 *            (the driver does), avoids a storage read for the
 *            marking; when omitted, the handler reads the stored
 *            queue value instead.
 *   /outcomes — read-only: { entries: [{ tick, id, outcome,
 *            day, reason, nextTemp }] } in tick order (the stored order is
 *            the key order, which is tick order). day/reason
 *            are null for entries logged before they were
 *            recorded (legacy plain-outcome values); nextTemp is
 *            null when the outcome carried no rotation.
 *            in tick order. Never creates state.
 *   /status — read-only: { queued, done, logged } counts.
 *            queued counts every queue key (live + discarded);
 *            done counts the discarded ones.
 */
export class TempIndex {
  constructor(state) {
    this.state = state;
  }

  async fetch(request) {
    const url = new URL(request.url);

    if (url.pathname === '/enqueue') {
      let body = {};
      try {
        body = await request.json();
      } catch {
        return new Response(JSON.stringify({ ok: false, error: 'invalid JSON body' }), {
          status: 400,
          headers: { 'content-type': 'application/json' },
        });
      }
      const tick = body.activationTick;
      const id = body.id;
      const referralId = body.referralId ?? null;
      if (
        typeof tick !== 'number' ||
        !Number.isFinite(tick) ||
        tick < 0 ||
        !Number.isInteger(tick) ||
        typeof id !== 'string' ||
        !id ||
        (referralId !== null && typeof referralId !== 'string')
      ) {
        return new Response(
          JSON.stringify({ ok: false, error: 'activationTick must be a non-negative integer, id a non-empty string, referralId a string or null' }),
          { status: 400, headers: { 'content-type': 'application/json' } },
        );
      }
      const key = queueKey(tick);
      await this.state.storage.put(key, queueValue(id, referralId));
      return new Response(JSON.stringify({ ok: true, key }), {
        headers: { 'content-type': 'application/json' },
      });
    }

    if (url.pathname === '/queue') {
      const entries = [];
      for (const [key, value] of await this.state.storage.list({ prefix: 'q:' })) {
        const tick = parseQueueKey(key);
        if (tick !== null) {
          const parsed = parseQueueValue(value);
          if (parsed) entries.push({ activationTick: tick, id: parsed.id, referralId: parsed.referralId, done: parsed.done });
        }
      }
      return new Response(JSON.stringify({ ok: true, entries }), {
        headers: { 'content-type': 'application/json' },
      });
    }

    if (url.pathname === '/queue-range') {
      let body = {};
      try {
        body = await request.json();
      } catch {
        return new Response(JSON.stringify({ ok: false, error: 'invalid JSON body' }), {
          status: 400,
          headers: { 'content-type': 'application/json' },
        });
      }
      const startTick = body.startTick;
      const endTick = body.endTick;
      const limit =
        body.limit === undefined ? GRAB_QUEUE_PAGE : body.limit;
      if (
        typeof startTick !== 'number' ||
        !Number.isInteger(startTick) ||
        startTick < 0 ||
        typeof endTick !== 'number' ||
        !Number.isInteger(endTick) ||
        endTick < startTick ||
        typeof limit !== 'number' ||
        !Number.isInteger(limit) ||
        limit < 1 ||
        limit > GRAB_QUEUE_PAGE
      ) {
        return new Response(
          JSON.stringify({ ok: false, error: `startTick/endTick must be integers with endTick >= startTick, limit an integer 1..${GRAB_QUEUE_PAGE}` }),
          { status: 400, headers: { 'content-type': 'application/json' } },
        );
      }
      const entries = [];
      // Bounded list: start/end are zero-padded queue keys, so
      // the storage scan touches only this range (never the whole
      // shard — a full list() here would materialise 31M keys in
      // the isolate). start is inclusive, end exclusive, limit
      // caps the page. The returned Map is in lexicographic key
      // order, which IS tick order.
      const list = await this.state.storage.list({
        prefix: 'q:',
        start: queueKey(startTick),
        end: queueKey(endTick + 1),
        limit,
      });
      for (const [key, value] of list) {
        const tick = parseQueueKey(key);
        if (tick === null) continue;
        const parsed = parseQueueValue(value);
        if (parsed) entries.push({ activationTick: tick, id: parsed.id, referralId: parsed.referralId, done: parsed.done });
      }
      return new Response(JSON.stringify({ ok: true, entries }), {
        headers: { 'content-type': 'application/json' },
      });
    }

    if (url.pathname === '/log') {
      let body = {};
      try {
        body = await request.json();
      } catch {
        return new Response(JSON.stringify({ ok: false, error: 'invalid JSON body' }), {
          status: 400,
          headers: { 'content-type': 'application/json' },
        });
      }
      const { tick, id, outcome, day, reason } = body;
      if (
        typeof tick !== 'number' ||
        !Number.isFinite(tick) ||
        tick < 0 ||
        !Number.isInteger(tick) ||
        typeof id !== 'string' ||
        !id ||
        !['verified', 'pending', 'not_verified', 'expired'].includes(outcome) ||
        (day !== undefined && day !== null && typeof day !== 'string') ||
        (reason !== undefined && reason !== null && typeof reason !== 'string')
      ) {
        return new Response(
          JSON.stringify({ ok: false, error: 'tick, id and an outcome (verified|pending|not_verified|expired) are required; day and reason, when present, must be strings' }),
          { status: 400, headers: { 'content-type': 'application/json' } },
        );
      }
      await this.state.storage.put(outcomeKey(tick, id), outcomeValue(outcome, day ?? null, reason ?? null));
      return new Response(JSON.stringify({ ok: true }), {
        headers: { 'content-type': 'application/json' },
      });
    }

    if (url.pathname === '/log-batch') {
      let body = {};
      try {
        body = await request.json();
      } catch {
        return new Response(JSON.stringify({ ok: false, error: 'invalid JSON body' }), {
          status: 400,
          headers: { 'content-type': 'application/json' },
        });
      }
      const entries = body.entries;
      if (
        !Array.isArray(entries) ||
        entries.length === 0 ||
        entries.length > GRAB_LOG_BATCH
      ) {
        return new Response(
          JSON.stringify({ ok: false, error: `entries must be a non-empty array of at most ${GRAB_LOG_BATCH}` }),
          { status: 400, headers: { 'content-type': 'application/json' } },
        );
      }
      // Validate everything first: a bad entry rejects the whole
      // batch and nothing is written. 'skip' is accepted as
      // marking-only (see below) — it is not an outcome and is
      // never written to the outcome log, EXCEPT a skip carrying
      // nextTemp (rotation crash repair — see the write loop).
      for (const e of entries) {
        if (
          !e ||
          typeof e.tick !== 'number' ||
          !Number.isFinite(e.tick) ||
          e.tick < 0 ||
          !Number.isInteger(e.tick) ||
          typeof e.id !== 'string' ||
          !e.id ||
          !['verified', 'pending', 'not_verified', 'expired', 'skip'].includes(e.outcome) ||
          (e.referralId !== undefined && e.referralId !== null && typeof e.referralId !== 'string') ||
          (e.day !== undefined && e.day !== null && typeof e.day !== 'string') ||
          (e.reason !== undefined && e.reason !== null && typeof e.reason !== 'string') ||
          (e.nextTemp !== undefined &&
            e.nextTemp !== null &&
            (typeof e.nextTemp !== 'object' ||
              Array.isArray(e.nextTemp) ||
              typeof e.nextTemp.id !== 'string' ||
              !e.nextTemp.id ||
              typeof e.nextTemp.tick !== 'number' ||
              !Number.isInteger(e.nextTemp.tick) ||
              e.nextTemp.tick < 0))
        ) {
          return new Response(
            JSON.stringify({ ok: false, error: 'each entry needs tick, id and an outcome (verified|pending|not_verified|expired|skip); referralId, day and reason, when present, must be strings or null; nextTemp, when present, must be {id, tick} or null' }),
            { status: 400, headers: { 'content-type': 'application/json' } },
          );
        }
      }
      // Idempotent by key (same key overwrites) — a re-run chunk
      // re-logs the same outcomes and changes nothing. 'skip'
      // entries write nothing to the log (nothing happened this
      // grab — the record was already verified), EXCEPT a skip
      // carrying nextTemp: that skip means the record was
      // verified by an earlier grab whose /log-batch never
      // landed, so the log has no verified entry for it — write
      // one now as 'verified' (the record IS verified; the
      // reason rides the entry as 'already_verified'), so the
      // publish still learns its next_temp.
      let logged = 0;
      for (const e of entries) {
        if (e.outcome === 'skip') {
          if (e.nextTemp) {
            await this.state.storage.put(outcomeKey(e.tick, e.id), outcomeValue('verified', e.day ?? null, e.reason ?? null, e.nextTemp));
            logged += 1;
          }
          continue;
        }
        await this.state.storage.put(outcomeKey(e.tick, e.id), outcomeValue(e.outcome, e.day ?? null, e.reason ?? null, e.nextTemp ?? null));
        logged += 1;
      }
      // DISCARD: a terminal outcome discards the queue entry
      // from the nightly walk — rewrite its queue value with the
      // done marker (the key stays, so the grab's density-based
      // stopping rule still holds). Pending marks nothing. A
      // 'skip' marks done:verified: the record IS verified, and
      // its queue entry was only ever unmarked because the grab
      // that verified it crashed before its /log-batch — without
      // this, a crashed chunk's records would be re-walked every
      // night forever. A done marker, once set, is never
      // overwritten with a different outcome (terminal outcomes
      // are final; the driver never re-applies a done record).
      // The referralId rides the entry when the caller supplies
      // it (the driver does); otherwise read the stored queue
      // value so the marking never drops the referral.
      let marked = 0;
      for (const e of entries) {
        const markOutcome = e.outcome === 'skip' ? 'verified' : e.outcome;
        if (!isTerminalOutcome(markOutcome)) continue;
        let referralId = e.referralId ?? null;
        if (e.referralId === undefined) {
          const stored = await this.state.storage.get(queueKey(e.tick));
          const parsed = stored === null ? null : parseQueueValue(stored);
          if (!parsed) continue;
          referralId = parsed.referralId;
          if (parsed.done !== null) continue;
        }
        await this.state.storage.put(queueKey(e.tick), queueValue(e.id, referralId, markOutcome));
        marked += 1;
      }
      return new Response(JSON.stringify({ ok: true, logged, marked }), {
        headers: { 'content-type': 'application/json' },
      });
    }

    if (url.pathname === '/outcomes') {
      const entries = [];
      for (const [key, value] of await this.state.storage.list({ prefix: 'o:' })) {
        const parsed = parseOutcomeKey(key);
        if (!parsed) continue;
        const { outcome, day, reason, nextTemp } = parseOutcomeValue(value);
        if (!outcome) continue;
        entries.push({ tick: parsed.tick, id: parsed.id, outcome, day, reason, nextTemp: nextTemp ?? null });
      }
      return new Response(JSON.stringify({ ok: true, entries }), {
        headers: { 'content-type': 'application/json' },
      });
    }

    if (url.pathname === '/status') {
      const queue = await this.state.storage.list({ prefix: 'q:' });
      const log = await this.state.storage.list({ prefix: 'o:' });
      let done = 0;
      for (const value of queue.values()) {
        const parsed = parseQueueValue(value);
        if (parsed && parsed.done !== null) done += 1;
      }
      return new Response(
        JSON.stringify({ ok: true, queued: queue.size, done, logged: log.size }),
        { headers: { 'content-type': 'application/json' } },
      );
    }

    return new Response(JSON.stringify({ ok: false, error: 'unknown temp index route' }), {
      status: 404,
      headers: { 'content-type': 'application/json' },
    });
  }
}

/**
 * The daily grab's state (one global stub, id 'grab:current').
 * The cursor is the truth: the grab is a chain of chunk
 * invocations, and if any link in the chain dies (CPU cut,
 * failed self-fetch, deploy mid-grab), the next trigger resumes
 * from this cursor — nothing is lost, nothing is double-counted
 * (chunk re-runs are idempotent: /apply never re-numbers a
 * stamp, /log-batch overwrites the same keys). State is one
 * record under key 'grab' — the grab.js shape (grabDay, shard,
 * nextTick, tallies, startedAtMs, updatedAtMs, done, capHit,
 * doneReason). Thin storage wrapper over grab.js, like
 * PingServerUsage.
 *
 * Routes (all POST, JSON bodies):
 *   /get — read-only: { state } or { state: null }. Never
 *          creates state on a bare read.
 *   /start { grabDay } — begin the grab for a day, or return
 *          the existing state for that day (idempotent: a
 *          second start returns the in-progress cursor; a start
 *          for a finished day returns the finished state).
 *          Snapshots maxTick from the tick counter (the highest
 *          tick assigned so far): the grab walks ticks up to
 *          maxTick only, so rotation temps created BY this grab
 *          (later ticks) wait for the next grab — see
 *          newGrabState in grab.js.
 *   /advance { state } — persist the state after a chunk.
 *          The cursor must not move backward (a stale writer is
 *          a 409); tallies must not shrink. Bad shape -> 400.
 *   /finish { tallies } — mark the grab done (doneReason
 *          'exhausted' or 'cap'). The state must exist (404).
 */
export class GrabState {
  constructor(state) {
    this.state = state;
  }

  async fetch(request) {
    const url = new URL(request.url);

    if (url.pathname === '/get') {
      const state = (await this.state.storage.get('grab')) || null;
      return new Response(JSON.stringify({ ok: true, state }), {
        headers: { 'content-type': 'application/json' },
      });
    }

    if (url.pathname === '/start') {
      let body = {};
      try {
        body = await request.json();
      } catch {
        return new Response(JSON.stringify({ ok: false, error: 'invalid JSON body' }), {
          status: 400,
          headers: { 'content-type': 'application/json' },
        });
      }
      if (typeof body.grabDay !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(body.grabDay)) {
        return new Response(JSON.stringify({ ok: false, error: 'grabDay must be a UTC date string' }), {
          status: 400,
          headers: { 'content-type': 'application/json' },
        });
      }
      const existing = (await this.state.storage.get('grab')) || null;
      if (existing && existing.grabDay === body.grabDay) {
        return new Response(JSON.stringify({ ok: true, state: existing, resumed: true }), {
          headers: { 'content-type': 'application/json' },
        });
      }
      // The shard width is part of the grab's configuration and
      // is stored on the state (grab.js newGrabState): the
      // cursor validation in /advance uses the stored width, so
      // a grab run with a narrower width (tests, or a future
      // re-shard) validates against its own width, not the
      // production one. A bad width falls back to the default.
      const shardWidth =
        typeof body.shardWidth === 'number' &&
        Number.isInteger(body.shardWidth) &&
        body.shardWidth >= 1
          ? body.shardWidth
          : GRAB_SHARD_WIDTH;
      // Rotation bound (FixNet temp rotation): snapshot the
      // highest tick assigned so far (the counter holds the
      // NEXT tick to assign) — the grab walks ticks up to
      // maxTick only. Rotations created by THIS grab take later
      // ticks and are walked by the NEXT grab; without the
      // snapshot the grab would never exhaust (each verified
      // rotation enqueues a new tick inside the shard
      // remainder). A temp activated mid-grab likewise waits
      // for the next day's grab — the bound makes that
      // deterministic instead of chunk-timing-dependent.
      const nextTickCounter = (await this.state.storage.get('nextActivationTick')) ?? 1;
      const maxTick = nextTickCounter - 1;
      const state = newGrabState(body.grabDay, Date.now(), shardWidth, maxTick);
      await this.state.storage.put('grab', state);
      return new Response(JSON.stringify({ ok: true, state, resumed: false }), {
        headers: { 'content-type': 'application/json' },
      });
    }

    if (url.pathname === '/advance') {
      let body = {};
      try {
        body = await request.json();
      } catch {
        return new Response(JSON.stringify({ ok: false, error: 'invalid JSON body' }), {
          status: 400,
          headers: { 'content-type': 'application/json' },
        });
      }
      const { ok, state, error } = validateGrabState(body.state);
      if (!ok) {
        return new Response(JSON.stringify({ ok: false, error }), {
          status: 400,
          headers: { 'content-type': 'application/json' },
        });
      }
      const existing = (await this.state.storage.get('grab')) || null;
      if (existing && existing.grabDay === state.grabDay) {
        // The cursor never moves backward and tallies never shrink
        // — a stale writer (an old invocation finishing late) is
        // rejected, not silently applied.
        if (compareCursors({ shard: state.shard, nextTick: state.nextTick }, { shard: existing.shard, nextTick: existing.nextTick }) < 0) {
          return new Response(JSON.stringify({ ok: false, error: 'cursor moved backward' }), {
            status: 409,
            headers: { 'content-type': 'application/json' },
          });
        }
        for (const k of ['checked', 'verified', 'pending', 'not_verified', 'expired', 'skipped']) {
          if (state.tallies[k] < existing.tallies[k]) {
            return new Response(JSON.stringify({ ok: false, error: `tallies.${k} shrank` }), {
              status: 409,
              headers: { 'content-type': 'application/json' },
            });
          }
        }
      }
      await this.state.storage.put('grab', { ...state, updatedAtMs: Date.now() });
      return new Response(JSON.stringify({ ok: true, state }), {
        headers: { 'content-type': 'application/json' },
      });
    }

    if (url.pathname === '/finish') {
      let body = {};
      try {
        body = await request.json();
      } catch {
        return new Response(JSON.stringify({ ok: false, error: 'invalid JSON body' }), {
          status: 400,
          headers: { 'content-type': 'application/json' },
        });
      }
      const existing = (await this.state.storage.get('grab')) || null;
      if (!existing) {
        return new Response(JSON.stringify({ ok: false, error: 'no grab started' }), {
          status: 404,
          headers: { 'content-type': 'application/json' },
        });
      }
      if (body.doneReason !== 'exhausted' && body.doneReason !== 'cap') {
        return new Response(JSON.stringify({ ok: false, error: "doneReason must be 'exhausted' or 'cap'" }), {
          status: 400,
          headers: { 'content-type': 'application/json' },
        });
      }
      const state = {
        ...existing,
        tallies: body.tallies ?? existing.tallies,
        done: true,
        capHit: body.doneReason === 'cap',
        doneReason: body.doneReason,
        updatedAtMs: Date.now(),
      };
      const { ok, error } = validateGrabState(state);
      if (!ok) {
        return new Response(JSON.stringify({ ok: false, error }), {
          status: 400,
          headers: { 'content-type': 'application/json' },
        });
      }
      await this.state.storage.put('grab', state);
      return new Response(JSON.stringify({ ok: true, state }), {
        headers: { 'content-type': 'application/json' },
      });
    }

    if (url.pathname === '/next-tick') {
      // The activation-tick counter (the yield intake's tick
      // source — POST /temp/activate). Activation ticks are the
      // causal order: monotonic, assigned once by the SERVER,
      // never by the client, never re-numbered. The counter lives
      // under its own key ('nextActivationTick'), separate from
      // the grab state ('grab'), so a grab start/finish never
      // touches it. A Durable Object serves one request at a
      // time, so the read-increment-write here is atomic — two
      // concurrent activations can never receive the same tick.
      // First tick is 1 (ticks start at 1; shardForTick maps
      // tick 1 to shard 0).
      const next = (await this.state.storage.get('nextActivationTick')) ?? 1;
      await this.state.storage.put('nextActivationTick', next + 1);
      return new Response(JSON.stringify({ ok: true, tick: next }), {
        headers: { 'content-type': 'application/json' },
      });
    }

    return new Response(JSON.stringify({ ok: false, error: 'unknown grab state route' }), {
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

/**
 * Mint a per-install key (Fix 2). 32 cryptographically random
 * bytes, hex-encoded, prefixed `pk-` so a per-install key is
 * never confused with the shared secret. 67 chars total.
 * Called only by the PingRateLimiter /register-key route (which
 * stores it once per user id and re-issues the same key).
 */
export function mintInstallKey() {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  let hex = '';
  for (const b of bytes) hex += b.toString(16).padStart(2, '0');
  return `pk-${hex}`;
}

/** Constant-time string comparison (for key checks — no early exit on length or content). */
export function keysEqual(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string') return false;
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

/**
 * Client-route gate (Fix 2). Accepts EITHER the shared secret
 * (x-lucid-ping-key === PING_SHARED_SECRET, the manually-entered
 * key Gary pasted) OR a valid per-install key for the user id in
 * x-lucid-user (the key POST /register minted for that install).
 * Used ONLY by the client routes (/ping, /v1/chat/completions,
 * /temp/activate) — the /admin/* routes keep authorized()
 * (shared secret only), so a per-install key can never reach
 * the grab, the progress store, or the outcome log. Open when
 * no secret is configured (dummy, same as authorized()). Async
 * because the per-install check is a Durable Object read (the
 * user's limiter stub /check-key) — and fail-closed: a missing
 * binding, a missing user id, or a DO error means not
 * authorized, never a silent pass.
 */
export async function authorizedClient(request, env) {
  const secret = env.PING_SHARED_SECRET;
  if (!secret) return true;
  const supplied = request.headers.get('x-lucid-ping-key');
  if (!supplied) return false;
  if (supplied === secret) return true;
  const id = userId(request);
  if (!id || !env.RATE_LIMITER) return false;
  try {
    const stub = env.RATE_LIMITER.get(env.RATE_LIMITER.idFromName(`user:${id}`));
    const res = await stub.fetch(
      new Request('http://limiter/check-key', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ key: supplied }),
      }),
    );
    if (!res.ok) return false;
    const parsed = await res.json();
    return parsed && parsed.ok === true && parsed.match === true;
  } catch {
    return false;
  }
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
 * Mark one user's SP bucket verified (PingRateLimiter /verify).
 * Called by the grab when a temp verifies, and by the intake
 * when a re-activation finds an already-verified record. The
 * user id is the temp's ownerUserId — the per-install id that
 * activated the temp — so the grant can only ever land on the
 * install that owns the verified temp. Fail-open: a missing
 * binding, a missing user id, or a DO error returns null and
 * the caller carries on — a failed grant must never fail the
 * grab or the intake (the next grab's 'skip' re-marks it).
 */
async function markUserVerified(env, userId) {
  if (!env.RATE_LIMITER || !userId) return null;
  try {
    const stub = env.RATE_LIMITER.get(env.RATE_LIMITER.idFromName(`user:${userId}`));
    const res = await stub.fetch(new Request('http://limiter/verify', { method: 'POST' }));
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
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
  if (!(await authorizedClient(request, env))) {
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
  if (!(await authorizedClient(request, env))) {
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

/**
 * The daily grab — step 2 of the dailies (how temps are verified).
 * One ping call to Cloudflare per day became, after the step-1
 * prototype's measured verdict (one call cannot work over the
 * store at 1B), CHUNKED PASSES over a SHARDED INDEX. This section
 * is the grab's Worker side; the pure math lives in grab.js, the
 * record shape and chain check in tempstore.js.
 *
 * Gary's framing: the pass is a pass of cryptographic hashes —
 * the check per record (checkChain, pure, no I/O) is cheap; the
 * chunking/sharding is about the storage round-trips and the
 * invocation CPU budget, not the check. The driver below is built
 * to that framing: per record it does ~2 stub calls (one referrer
 * /get, one /apply — the /get the step-1 scan did per record is
 * gone, the referralId rides the queue entry) plus batched log
 * writes, and the pure check is measured separately (grab-scan).
 *
 * Invocation shape: POST /admin/grab runs ONE chunk and returns;
 * the next chunk is chained by a self-fetch via ctx.waitUntil
 * (the cursor in the GrabState DO is the truth — if the chain
 * breaks, the next hourly cron wake-up resumes it). The
 * scheduled() handler gates on the 00:00 America/Vancouver hour.
 * Chunks are sized (grab.js GRAB_CHUNK_RECORDS) to fit the
 * binding invocation budgets with margin: ~15 s CPU (half the
 * 30 s Paid HTTP default) and ~400k subrequests (40% of the
 * configured 1,000,000 [limits] — the Paid default is 10,000,
 * which would cap chunks at ~5,000 records; the raise is a
 * required deployment setting, see wrangler.toml).
 *
 * Safety: a DO failure fails the chunk LOUD (the error
 * propagates, the cursor does not advance, the next trigger
 * retries the chunk). A chunk re-run is idempotent (/apply never
 * re-numbers a stamp; /log-batch overwrites the same keys).
 * The cap (Q2, decided in grab.js: queue for the next day) is
 * enforced per batch — an overshoot of at most one batch
 * (GRAB_BATCH_CONCURRENCY records) past the cap is possible and
 * is within measurement noise at 1B.
 */

/** Call a DO stub route and parse its JSON; a DO error throws (fail-loud, never a silent skip). */
async function doJson(stub, path, body) {
  const res = await stub.fetch(
    new Request(`http://do${path}`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    }),
  );
  const parsed = await res.json().catch(() => null);
  if (!res.ok || !parsed || parsed.ok === false) {
    throw new Error(`DO ${path} failed: HTTP ${res.status} ${parsed && parsed.error ? parsed.error : ''}`);
  }
  return parsed;
}

/** A temp's record stub. */
function tempRecordStub(env, id) {
  if (!env.TEMP_STORE) throw new Error('temp store binding (TEMP_STORE) is not configured');
  return env.TEMP_STORE.get(env.TEMP_STORE.idFromName(`temp:${id}`));
}

/** An index shard's stub. */
function tempIndexStub(env, shard) {
  if (!env.TEMP_INDEX) throw new Error('temp index binding (TEMP_INDEX) is not configured');
  return env.TEMP_INDEX.get(env.TEMP_INDEX.idFromName(shardStubId(shard)));
}

/** The grab-state stub (one global stub). */
function grabStateStub(env) {
  if (!env.GRAB_STATE) throw new Error('grab state binding (GRAB_STATE) is not configured');
  return env.GRAB_STATE.get(env.GRAB_STATE.idFromName('grab:current'));
}

/**
 * Ensure a rotation temp exists for a verified temp (FixNet temp
 * rotation, design D2/D3). Returns { id, tick, created } — the
 * rotation temp's id + its activation tick, and whether this call
 * created it. Idempotent: when oldRecord.rotationTempId is
 * already set, the existing rotation is REUSED, never duplicated.
 *
 * Create path (no rotation yet): a tick from GrabState
 * /next-tick, the pointer stored on the old record FIRST
 * (TempRecord /rotate), then the rotation record (/put) and its
 * queue entry (/enqueue). Pointer-first so a crash after this
 * point always leaves the rotation id recoverable — the reuse
 * path below — instead of an orphaned rotation record.
 *
 * Reuse path (rotationTempId set): the rotation record is read
 * for its tick and re-enqueued (idempotent by key — repairs a
 * crash between /put and /enqueue). If the record is missing (a
 * crash between /rotate and /put), it is rebuilt under the SAME
 * id with a fresh tick and enqueued — the id is the pointer, the
 * tick is re-allocated (the lost tick is a hole, which the
 * range-based queue paging tolerates, as /temp/activate already
 * proves).
 *
 * The new temp's referralId is the old temp's id (the chain
 * resolves the referrer as verified → 'chain_holds' on the next
 * grab); NEVER 'ref:genesis' (that would be genesis_not_root →
 * not_verified). ownerUserId is inherited from the old temp (the
 * SP grant stays on the profile-id bucket). Guests never reach
 * here — the caller only rotates verified / skipped records,
 * and a guest temp never verifies.
 *
 * shardWidth is the grab's configured index width (the driver's
 * state.shardWidth): the rotation's queue entry must land in the
 * shard the next grab walks under that width. Production always
 * uses the default (GRAB_SHARD_WIDTH); the parameter exists so
 * a narrow-width test grab finds its rotations.
 */
async function ensureRotation(env, oldRecord, nowMs, shardWidth = GRAB_SHARD_WIDTH) {
  if (oldRecord.rotationTempId) {
    const existing = await doJson(tempRecordStub(env, oldRecord.rotationTempId), '/get');
    if (existing.record) {
      await doJson(tempIndexStub(env, shardForTick(existing.record.activationTick, shardWidth)), '/enqueue', {
        activationTick: existing.record.activationTick,
        id: existing.record.id,
        referralId: existing.record.referralId,
      });
      return { id: existing.record.id, tick: existing.record.activationTick, created: false };
    }
    const { tick } = await doJson(grabStateStub(env), '/next-tick', {});
    const rebuilt = newRotationRecord({ oldRecord, activationTick: tick, nowMs, id: oldRecord.rotationTempId });
    const { ok, record, error } = validateTempRecord(rebuilt);
    if (!ok) throw new Error(`rotation record failed validation: ${error}`);
    await doJson(tempRecordStub(env, record.id), '/put', { record });
    await doJson(tempIndexStub(env, shardForTick(tick, shardWidth)), '/enqueue', {
      activationTick: tick,
      id: record.id,
      referralId: record.referralId,
    });
    return { id: record.id, tick, created: false };
  }
  const { tick } = await doJson(grabStateStub(env), '/next-tick', {});
  const built = newRotationRecord({ oldRecord, activationTick: tick, nowMs });
  const { ok, record, error } = validateTempRecord(built);
  if (!ok) throw new Error(`rotation record failed validation: ${error}`);
  await doJson(tempRecordStub(env, oldRecord.id), '/rotate', { rotationTempId: record.id });
  await doJson(tempRecordStub(env, record.id), '/put', { record });
  await doJson(tempIndexStub(env, shardForTick(tick, shardWidth)), '/enqueue', {
    activationTick: tick,
    id: record.id,
    referralId: record.referralId,
  });
  return { id: record.id, tick, created: true };
}

/**
 * Run ONE chunk of the grab from a grab state. Pure driver over
 * the DO bindings: pages the current shard's queue-remainder,
 * applies the chain check per record in tick-order batches, logs
 * the outcomes in batches, and returns the next state (not yet
 * persisted — the caller /advance's it) plus chunk stats.
 * Never spans shards; never re-verifies (the /apply 'skip'
 * path); stops early on the cap.
 */
async function runGrabChunk(env, state, opts = {}) {
  const nowMs = opts.nowMs ?? Date.now();
  const grabDay = opts.grabDay ?? grabDayFor(nowMs);
  const chunkRecords = opts.chunkRecords ?? GRAB_CHUNK_RECORDS;
  const concurrency = opts.concurrency ?? GRAB_BATCH_CONCURRENCY;
  const shardWidth = opts.shardWidth ?? state.shardWidth ?? GRAB_SHARD_WIDTH;
  const cap = opts.cap ?? GRAB_DAILY_CAP;

  // The cursor can land one past a shard's end when the previous
  // chunk ended exactly on the boundary (chunkRecords filled at
  // shardEnd). That shard is FULLY processed — every tick up to
  // its end was checked — so advance to the next shard and probe
  // IT. Only a shard remainder that actually pages EMPTY means
  // the grab is done; a cursor past a shard's end must never be
  // read as "exhausted" (that bug would silently skip every
  // later shard).
  let shard = state.shard;
  let { startTick, endTick: shardEnd } = shardRange(shard, shardWidth);
  let fromTick = Math.max(state.nextTick, startTick);
  while (fromTick > shardEnd) {
    shard += 1;
    ({ startTick, endTick: shardEnd } = shardRange(shard, shardWidth));
    fromTick = startTick;
  }

  // Rotation bound (FixNet temp rotation): the grab walks ticks
  // up to state.maxTick ONLY — the highest tick that existed
  // when the grab started (snapshotted by /start). Rotation
  // temps created by THIS grab, and temps activated mid-grab,
  // carry later ticks and wait for the next grab. When the
  // cursor has walked through maxTick, the grab is done — the
  // bound, not an empty page, proves exhaustion for this grab.
  // A legacy state (maxTick null) walks unbounded, as before.
  const maxTick = typeof state.maxTick === 'number' ? state.maxTick : null;
  if (maxTick !== null && fromTick > maxTick) {
    const nextState = {
      ...state,
      shard,
      nextTick: state.nextTick,
      tallies: { ...state.tallies },
      updatedAtMs: Date.now(),
      done: true,
      capHit: false,
      doneReason: 'exhausted',
    };
    return {
      state: nextState,
      chunk: {
        shard,
        startTick: fromTick,
        endTick: fromTick - 1,
        records: 0,
        verified: 0,
        shardExhausted: true,
        capHit: false,
      },
      done: true,
      doneReason: 'exhausted',
      capHit: false,
    };
  }
  const walkEnd = maxTick === null ? shardEnd : Math.min(shardEnd, maxTick);

  // Page the shard remainder [fromTick, shardEnd], collecting up
  // to chunkRecords entries. The shard remainder is exhausted
  // only when BOTH hold: the last page was short (nothing more
  // exists in the range) AND the chunk took every entry the
  // pages returned. A short page alone does not exhaust the
  // shard when the chunk truncated the returned entries — the
  // cut-off entries are still unprocessed in this shard.
  const entries = [];
  let pageStart = fromTick;
  let shardExhausted = false;
  while (entries.length < chunkRecords && pageStart <= walkEnd) {
    const page = await doJson(tempIndexStub(env, shard), '/queue-range', {
      startTick: pageStart,
      endTick: walkEnd,
      limit: GRAB_QUEUE_PAGE,
    });
    for (const e of page.entries) {
      // Done entries are discarded from the nightly walk — skip
      // them here (no referrer /get, no /apply, no tally). The
      // page advance below still uses the raw page (done entries
      // included), so paging walks the full tick range and the
      // density-based stopping rule still holds.
      if (!e.done) entries.push(e);
    }
    if (page.entries.length < GRAB_QUEUE_PAGE) {
      shardExhausted = true;
      break;
    }
    if (entries.length >= chunkRecords) break;
    pageStart = page.entries[page.entries.length - 1].activationTick + 1;
  }
  let truncated = false;
  if (entries.length > chunkRecords) {
    entries.length = chunkRecords;
    truncated = true;
  }
  if (pageStart > walkEnd) shardExhausted = true;
  if (truncated) shardExhausted = false;

  const tallies = { ...state.tallies };
  const outcomes = [];
  // Per-install user ids whose temp verified in this chunk
  // (or was already verified — 'skip'). Marked verified on
  // their SP buckets after the outcomes are logged, so the
  // 1,000 SP/day grant only lands once the outcome is durable.
  const verifiedOwners = [];
  let processed = 0;
  let capHit = false;

  // Tick-order batches; Promise.all within a batch, batches
  // sequential. A referrer is an earlier tick, so it is in an
  // earlier batch or an earlier chunk — except the ~batch-sized
  // fraction inside the same batch, which reads the referrer's
  // pre-apply state and pends one grab (safe, negligible).
  // Each batch runs in two phases — resolve ALL referrer states
  // first, then apply — so a same-batch referrer is always read
  // BEFORE any of the batch's applies land (deterministic,
  // pre-batch state), never a read/write race.
  for (let i = 0; i < entries.length; i += concurrency) {
    const batch = entries.slice(i, i + concurrency);
    const referrerStates = await Promise.all(
      batch.map(async (entry) => {
        // The genesis claim is only the root: referralId
        // 'ref:genesis' AND activation tick 1. Any later temp
        // carrying it is not the root and is marked not_verified
        // (genesis_not_root) — the claim cannot be used to skip
        // the chain. A referral-less temp gets null and the
        // chain check marks it not_verified (no_referral).
        const genesis = genesisReferrerState(entry.referralId, entry.activationTick);
        if (genesis === 'genesis_not_root') return 'genesis_not_root';
        if (genesis === 'genesis') return 'genesis';
        if (!entry.referralId) return null;
        const ref = await doJson(tempRecordStub(env, entry.referralId), '/get');
        return !ref.record
          ? 'missing'
          : ref.record.verificationState === 'verified'
            ? 'verified'
            : 'pending';
      }),
    );
    const results = await Promise.all(
      batch.map(async (entry, j) => {
        const applied = await doJson(tempRecordStub(env, entry.id), '/apply', {
          nowMs,
          referrerState: referrerStates[j],
          tick: entry.activationTick,
          grabDay,
        });
        return {
          entry,
          outcome: applied.outcome,
          // The reason the chain check gave (chain_holds,
          // genesis_root, no_referral, ...) — it rides the
          // outcome log so the publish can say why, not just
          // what. The owner is the per-install id that activated
          // the temp — the SP grant lands on that install only.
          // The record rides along so the results loop can read
          // rotationTempId without a second /get.
          reason: typeof applied.reason === 'string' ? applied.reason : null,
          record: applied.record,
          ownerUserId:
            applied.record && typeof applied.record.ownerUserId === 'string'
              ? applied.record.ownerUserId
              : null,
        };
      }),
    );
    for (const { entry, outcome, reason, record, ownerUserId } of results) {
      tallies.checked += 1;
      // The outcome is 'skip'; the tally key is 'skipped' —
      // tallies['skip'] would be NaN (and null after JSON).
      tallies[outcome === 'skip' ? 'skipped' : outcome] += 1;
      processed += 1;
      // Rotation (FixNet temp rotation, design D2/D3): a
      // verified temp yields its successor HERE, in the grab —
      // on fresh 'verified' AND on 'skip' (crash recovery: a
      // chunk that crashed before its /log-batch re-processes a
      // verified record whose rotation may not exist yet).
      // ensureRotation is idempotent — a rotationTempId that is
      // already set is REUSED, never duplicated. Sequential,
      // one record at a time: the tick allocation (/next-tick)
      // must never race, and the fake test DO interleaves
      // concurrent calls where the real DO serializes — the
      // driver must be correct in both. Cost, stated: ~4 extra
      // subrequests per verified record (next-tick, /rotate,
      // /put, /enqueue) — the chunk sizing (GRAB_CHUNK_RECORDS)
      // was measured without rotations and needs re-measuring
      // at the step-6 edge check. The nextTemp rides the
      // outcome entry so /log-batch logs it and the publish +
      // client can follow the chain.
      let nextTemp = null;
      if (outcome === 'verified' || outcome === 'skip') {
        const rotation = await ensureRotation(env, record, nowMs, shardWidth);
        nextTemp = { id: rotation.id, tick: rotation.tick };
      }
      // Every outcome rides /log-batch — including 'skip', which
      // /log-batch takes as marking-only (done:verified, no log
      // write): a skipped record was verified by an earlier grab,
      // or by a chunk that crashed before its /log-batch. The
      // referralId rides along so the marking never needs a
      // storage read for it. EXCEPTION: a skip carrying nextTemp
      // DOES write a log entry (as 'verified') — see /log-batch.
      outcomes.push({ tick: entry.activationTick, id: entry.id, outcome, referralId: entry.referralId ?? null, day: grabDay, reason: reason ?? null, nextTemp });
      // A refused genesis claim is worth a log line: a temp
      // claimed the root and was not the root tick. (It fires
      // here, on the outcome, not at resolution — an
      // already-verified record that happens to carry the claim
      // skips and is never refused.)
      if (outcome === 'not_verified' && reason === 'genesis_not_root') {
        console.log(`[grab] genesis claim refused: ${entry.id} tick ${entry.activationTick} is not the root tick`);
      }
      // A verified temp grants its owner the verified SP
      // allowance (1,000/day) — and a skipped one is already
      // verified, so it re-marks (idempotent) in case the grab
      // that verified it crashed before marking. The marking
      // happens after the log-batch below, so the grant only
      // lands once the outcome is durably logged.
      if ((outcome === 'verified' || outcome === 'skip') && ownerUserId) {
        verifiedOwners.push(ownerUserId);
      }
    }
    if (tallies.verified >= cap) {
      capHit = true;
      break;
    }
  }

  // Log the outcomes in batches (idempotent by key) — and, in
  // the same call, discard the terminal ones from the nightly
  // walk (/log-batch marks their queue entries done; 'skip'
  // entries mark done:verified without a log write).
  for (let i = 0; i < outcomes.length; i += GRAB_LOG_BATCH) {
    await doJson(tempIndexStub(env, shard), '/log-batch', {
      entries: outcomes.slice(i, i + GRAB_LOG_BATCH),
    });
  }

  // The outcomes are durably logged — now mark the verified
  // owners' SP buckets (1,000 SP/day, no cap). Deduped: one
  // user may own several verified temps in a chunk. Fail-open
  // per owner (markUserVerified never throws): a failed mark is
  // retried by the next grab's 'skip', which re-marks.
  for (const ownerUserId of new Set(verifiedOwners)) {
    await markUserVerified(env, ownerUserId);
  }

  // The next cursor. A cap-hit grab stops here (the rest queue
  // for the next day — Q2). An exhausted shard moves to the next
  // shard; an empty shard remainder means the grab is done:
  // activation ticks are a dense monotonic counter and shards
  // fill in order, so an empty shard implies no later ticks
  // exist. Otherwise the cursor stays in this shard.
  let nextState = {
    ...state,
    shard,
    nextTick: state.nextTick,
    tallies,
    updatedAtMs: Date.now(),
    done: state.done,
    capHit: state.capHit,
    doneReason: state.doneReason,
  };
  let done = false;
  let doneReason = null;
  if (capHit) {
    done = true;
    doneReason = 'cap';
    nextState.nextTick =
      processed > 0 ? entries[processed - 1].activationTick + 1 : state.nextTick;
  } else if (shardExhausted) {
    if (processed === 0) {
      done = true;
      doneReason = 'exhausted';
      nextState.nextTick = state.nextTick;
    } else {
      const next = shardRange(shard + 1, shardWidth);
      nextState.shard = shard + 1;
      nextState.nextTick = next.startTick;
    }
  } else {
    nextState.nextTick = entries[processed - 1].activationTick + 1;
  }
  nextState.done = done;
  nextState.capHit = capHit;
  nextState.doneReason = doneReason;
  return {
    state: nextState,
    chunk: {
      shard,
      startTick: fromTick,
      endTick: processed > 0 ? entries[processed - 1].activationTick : fromTick - 1,
      records: processed,
      verified: tallies.verified - state.tallies.verified,
      shardExhausted,
      capHit,
    },
    done,
    doneReason,
    capHit,
  };
}

/**
 * Chain the next chunk: a self-fetch to this Worker's own grab
 * endpoint, scheduled via ctx.waitUntil so the current
 * invocation returns immediately. The origin comes from the
 * triggering request (POST) or the GRAB_PUBLIC_URL var
 * (scheduled); the admin key comes from env (the shared secret
 * the Worker itself holds). If there is no origin or no secret,
 * no chain is scheduled — the cursor is the truth and the next
 * hourly cron wake-up resumes the grab (slow backstop). A
 * failed chain is swallowed: it only delays the grab, never
 * loses work. Safety note: in local dev the secret is unset, so
 * a local chain fetch carries no key and production (which has
 * the secret set) answers 401 — a local run can never poke the
 * production grab.
 */
function chainGrab(env, ctx, origin) {
  if (!origin || !env.PING_SHARED_SECRET || !ctx || typeof ctx.waitUntil !== 'function') {
    return false;
  }
  const chained = fetch(`${origin}/admin/grab`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-lucid-ping-key': env.PING_SHARED_SECRET,
    },
    body: JSON.stringify({ chain: true }),
  }).catch(() => null);
  try {
    ctx.waitUntil(chained);
  } catch {
    return false;
  }
  return true;
}

/** Read the grab state (or null when no grab has ever started). */
async function grabStateGet(env) {
  return doJson(grabStateStub(env), '/get');
}

/**
 * One grab step: start/resume today's grab, run one chunk,
 * persist the cursor, chain the next chunk unless done.
 * Returns { done, capHit, doneReason, state, chunk, chained }.
 * A re-run after a finished grab returns the finished state
 * without doing any work (idempotent).
 */
async function grabStep(env, ctx, opts = {}) {
  const nowMs = opts.nowMs ?? Date.now();
  const grabDay = grabDayFor(nowMs);
  const origin = opts.origin ?? null;
  const chain = opts.chain !== false;

  const got = await grabStateGet(env);
  let state = got.state;
  if (state && state.grabDay === grabDay && state.done) {
    return { done: true, capHit: state.capHit, doneReason: state.doneReason, state, chunk: null, chained: false };
  }
  if (!state || state.grabDay !== grabDay) {
    const started = await doJson(grabStateStub(env), '/start', {
      grabDay,
      shardWidth: opts.chunk?.shardWidth,
    });
    state = started.state;
  }

  const run = await runGrabChunk(env, state, { nowMs, grabDay, ...opts.chunk });
  if (run.done) {
    const finished = await doJson(grabStateStub(env), '/finish', {
      tallies: run.state.tallies,
      doneReason: run.doneReason,
    });
    return { done: true, capHit: run.capHit, doneReason: run.doneReason, state: finished.state, chunk: run.chunk, chained: false };
  }
  const advanced = await doJson(grabStateStub(env), '/advance', { state: run.state });
  let chained = false;
  if (chain) chained = chainGrab(env, ctx, origin);
  return { done: false, capHit: false, doneReason: null, state: advanced.state, chunk: run.chunk, chained };
}

/**
 * The daily grab — the queryable admin endpoint.
 *
 * The grab is a data check: it runs no model call, it is not a
 * chat completion, and it spends 0 neurons and 0 SP (spec §1.2
 * step 9 — the corrected model: 1 ping call to Cloudflare per
 * day, flat, count-independent; the chunked passes are many
 * invocations of one daily grab, each one a data check).
 *
 * POST /admin/grab — run one chunk of today's grab (admin key).
 *   Body: { chain?: boolean } — chain the next chunk (default
 *   true; false drives the grab manually, one chunk per call —
 *   the local-test shape). Returns the chunk result + the
 *   cursor + the tallies. A second call after the grab is done
 *   returns the finished state without work.
 * GET /admin/grab — read-only: the grab state, or null when no
 *   grab has ever started. Never creates state.
 * The status lookup (any temp checks verified/pending/not
 * verified) is step 3, NOT this route — it rides the FixNet
 * connection (Q5, decided), not the grab endpoint.
 */
async function handleGrabPost(request, env, ctx) {
  if (!authorized(request, env)) {
    return errorResponse(401, 'unauthorized: missing or wrong x-lucid-ping-key');
  }
  let body = {};
  try {
    body = await request.json();
  } catch {
    body = {};
  }
  const origin = new URL(request.url).origin;
  const step = await grabStep(env, ctx, {
    chain: body.chain !== false,
    origin,
    chunk: {
      chunkRecords: typeof body.chunkRecords === 'number' ? body.chunkRecords : undefined,
      concurrency: typeof body.concurrency === 'number' ? body.concurrency : undefined,
      shardWidth: typeof body.shardWidth === 'number' ? body.shardWidth : undefined,
      cap: typeof body.cap === 'number' ? body.cap : undefined,
    },
  });
  return jsonResponse(200, {
    ok: true,
    done: step.done,
    capHit: step.capHit,
    doneReason: step.doneReason,
    state: step.state,
    chunk: step.chunk,
    chained: step.chained,
  });
}

async function handleGrabGet(request, env) {
  if (!authorized(request, env)) {
    return errorResponse(401, 'unauthorized: missing or wrong x-lucid-ping-key');
  }
  const got = await grabStateGet(env);
  return jsonResponse(200, { ok: true, state: got.state });
}

/**
 * GET /admin/grab-outcomes — read-only: the grab's outcome log
 * across every temp-index shard, in activation-tick order.
 * This is the publish step's read end (FixNet step 3): the
 * daily Pages publish reads this route and writes the status
 * table the clients pull. Admin key only — the log carries
 * every temp id, so it never goes to a client directly.
 *
 * Query params (all optional):
 *   shard=N — read one shard only (a single shard's /outcomes).
 *   day=YYYY-MM-DD — keep only outcomes decided on that grab day.
 * Without params: every shard the grab cursor has reached
 * (0..state.shard), merged and sorted by tick. The shard
 * fan-out is capped at 64 (shard width 31,250,000 ticks — 64
 * shards is 2B ticks, far past the 1B/day cap); a larger
 * cursor returns shards 0..63 and reports truncated: true, so
 * the publish reads the rest by shard.
 *
 * Response: { ok, grabDay, shards, truncated, outcomes:
 * [{ tick, id, outcome, day, reason, next_temp }] } — one entry per temp
 * (latest outcome wins in the log), in tick order. day/reason
 * are null for entries logged before they were recorded.
 * next_temp {id, tick} is the rotation temp the grab created for
 * a verified temp (design D4), or null — the publish puts it on
 * the verified status entry and the client rotates to it.
 */
async function handleGrabOutcomes(request, env) {
  if (!authorized(request, env)) {
    return errorResponse(401, 'unauthorized: missing or wrong x-lucid-ping-key');
  }
  const url = new URL(request.url);
  const dayFilter = url.searchParams.get('day');
  const shardParam = url.searchParams.get('shard');
  const got = await grabStateGet(env);
  const state = got.state;
  const maxShard = state && typeof state.shard === 'number' ? state.shard : 0;
  let shards;
  if (shardParam !== null) {
    const single = Number(shardParam);
    if (!Number.isInteger(single) || single < 0) {
      return errorResponse(400, 'shard must be a non-negative integer');
    }
    shards = [single];
  } else {
    const top = Math.min(maxShard, 63);
    shards = Array.from({ length: top + 1 }, (_, i) => i);
  }
  const truncated = shardParam === null && maxShard > 63;
  const outcomes = [];
  for (const shard of shards) {
    const res = await doJson(tempIndexStub(env, shard), '/outcomes');
    if (!res.ok || !Array.isArray(res.entries)) continue;
    for (const e of res.entries) {
      if (dayFilter && e.day !== dayFilter) continue;
      outcomes.push({
        tick: e.tick,
        id: e.id,
        outcome: e.outcome,
        day: e.day,
        reason: e.reason,
        next_temp: e.nextTemp ?? null,
      });
    }
  }
  outcomes.sort((a, b) => a.tick - b.tick);
  return jsonResponse(200, {
    ok: true,
    grabDay: state ? state.grabDay : null,
    shards: shards.length,
    truncated,
    outcomes,
  });
}

/**
 * POST /admin/rotate — backfill a rotation for an already-verified
 * temp (FixNet temp rotation, design D3). The grab's chunk walk
 * SKIPS done queue entries, so a temp verified before rotation
 * existed (Genesis, verified 2026-11-17) never re-enters the walk
 * — this one-time endpoint creates its rotation instead. Admin
 * key only. Body { id }. It ALSO writes the rotation into the
 * outcome log (via /log-batch's skip+nextTemp lane, preserving
 * the entry's original day/reason) — the publish reads ONLY the
 * outcome log, so without this the client would never learn the
 * next_temp and the temp would never rotate on sync.
 *
 * Returns { ok, id, next_temp: { id, tick }, created }: created
 * true when this call created the rotation, false when one
 * already existed (idempotent — the existing rotation is
 * returned). 400 when the temp exists but is not verified (only
 * a verified temp yields a rotation; guests never verify), 404
 * when no such temp exists.
 *
 * Body { id, shardWidth? }: shardWidth is the index width the
 * next grab will walk (the /admin/grab test hook); it defaults
 * to the production width. Production callers omit it.
 */
async function handleRotatePost(request, env) {
  if (!authorized(request, env)) {
    return errorResponse(401, 'unauthorized: missing or wrong x-lucid-ping-key');
  }
  let body = {};
  try {
    body = await request.json();
  } catch {
    return errorResponse(400, 'invalid JSON body');
  }
  const id = body.id;
  if (typeof id !== 'string' || !id) {
    return errorResponse(400, 'id must be a non-empty string');
  }
  const shardWidth =
    typeof body.shardWidth === 'number' &&
    Number.isInteger(body.shardWidth) &&
    body.shardWidth >= 1
      ? body.shardWidth
      : GRAB_SHARD_WIDTH;
  const got = await doJson(tempRecordStub(env, id), '/get');
  if (!got.record) {
    return errorResponse(404, 'no such temp');
  }
  if (got.record.verificationState !== 'verified') {
    return errorResponse(400, 'temp is not verified');
  }
  const rotation = await ensureRotation(env, got.record, Date.now(), shardWidth);
  // Surface the rotation to the publish: the outcome log entry for
  // this temp was written by the grab that verified it (before
  // rotation existed), so it carries next_temp: null — and the
  // publish reads ONLY the outcome log, so without this the client
  // would never learn the next_temp and the temp would never
  // rotate on sync. Write it back with the next_temp via
  // /log-batch's skip+nextTemp lane (the crash-repair path — a
  // skip carrying nextTemp writes the entry as 'verified' with
  // the given day/reason/nextTemp). Preserve the entry's original
  // day/reason; if there is no logged entry (the verifying grab
  // crashed before its /log-batch), attribute it to the current
  // grab day with reason 'already_verified'. Runs on every call
  // (created or already-existing), so a retry after a failed
  // log write still surfaces the rotation.
  const shard = shardForTick(got.record.activationTick, shardWidth);
  let day = null;
  let reason = null;
  let found = false;
  const outcomesRes = await doJson(tempIndexStub(env, shard), '/outcomes');
  if (outcomesRes.ok && Array.isArray(outcomesRes.entries)) {
    const existing = outcomesRes.entries.find(
      (e) => e.tick === got.record.activationTick && e.id === id,
    );
    if (existing) {
      found = true;
      day = existing.day ?? null;
      reason = existing.reason ?? null;
    }
  }
  if (!found) {
    const grabState = await grabStateGet(env);
    day =
      grabState.state && typeof grabState.state.grabDay === 'string'
        ? grabState.state.grabDay
        : null;
    reason = 'already_verified';
  }
  const logRes = await doJson(tempIndexStub(env, shard), '/log-batch', {
    entries: [
      {
        tick: got.record.activationTick,
        id,
        outcome: 'skip',
        day,
        reason,
        nextTemp: { id: rotation.id, tick: rotation.tick },
      },
    ],
  });
  if (!logRes.ok) {
    return errorResponse(500, 'rotation created but the outcome log update failed — retry the backfill');
  }
  return jsonResponse(200, {
    ok: true,
    id,
    next_temp: { id: rotation.id, tick: rotation.tick },
    created: rotation.created,
  });
}

/**
 * Per-install key registration (Fix 2 — Gary 2026-11-17 06:31 MST:
 * "if its default i shouldnt have to input it"). The default ping
 * server works without manual key entry: a fresh install with no
 * key stored calls this once, gets a per-install key, and stores
 * it (the Lucid client's ensureDefaultPingKey — deployed d8c6a54).
 *
 * POST /register — body { userId }. The userId is the per-install
 * id (the same id the client sends as x-lucid-user). The server
 * mints ONE key per userId (the user's limiter stub stores it
 * under 'key'; re-issue returns the SAME key — that is the rate
 * limit) and returns { ok: true, key }. The key is accepted by
 * authorizedClient() alongside PING_SHARED_SECRET for /ping,
 * /v1/chat/completions and /temp/activate — never for /admin/*.
 *
 * Auth: NONE — this is the provisioning endpoint, called by a
 * client that has no key yet. The userId is a random per-install
 * UUID (the client generates it once), so minting requires
 * knowing it; a key is only useful with its own userId, and a
 * minted key for a random userId spends from a bucket nobody
 * owns. Bad userId -> 400. DO unavailable -> 503 (the client
 * degrades to manual entry — ensureDefaultPingKey returns false
 * on any failure and the call proceeds without a key). 0 neurons,
 * 0 SP — plain DO read/write, never Workers AI.
 */
async function handleRegister(request, env) {
  let body = {};
  try {
    body = await request.json();
  } catch {
    return errorResponse(400, 'invalid JSON body');
  }
  const userIdValue = body.userId;
  if (
    typeof userIdValue !== 'string' ||
    !userIdValue ||
    userIdValue.length > 128 ||
    !/^[A-Za-z0-9._-]+$/.test(userIdValue)
  ) {
    return errorResponse(400, 'userId must be a non-empty string of 1-128 [A-Za-z0-9._-] characters');
  }
  if (!env.RATE_LIMITER) {
    return errorResponse(503, 'rate limiter binding (RATE_LIMITER) is not configured');
  }
  try {
    const stub = env.RATE_LIMITER.get(env.RATE_LIMITER.idFromName(`user:${userIdValue}`));
    const res = await stub.fetch(new Request('http://limiter/register-key', { method: 'POST' }));
    if (!res.ok) return errorResponse(503, 'key registry unavailable');
    const parsed = await res.json();
    if (!parsed || parsed.ok !== true || typeof parsed.key !== 'string' || !parsed.key) {
      return errorResponse(503, 'key registry unavailable');
    }
    return jsonResponse(200, { ok: true, key: parsed.key });
  } catch (err) {
    return errorResponse(503, `key registry unavailable: ${err instanceof Error ? err.message : String(err)}`);
  }
}

/**
 * The yield intake — how a client's temp record enters the temp
 * store so the daily grab can verify it (step 1 of the dailies,
 * the activation half of the spec §1.2: a temp is ACTIVATED when
 * its record is registered in the store with the referral that
 * brought it in).
 *
 * POST /temp/activate — the client sends its temp's id (the
 * `profile-<uuid>` from createProfile) and the referral that
 * brought it in, if any. The SERVER assigns the activation tick
 * (GrabState /next-tick — monotonic, never the client, never
 * re-numbered), builds the record (window = now + 1 year,
 * verificationState pending), stores it (TempRecord /put) and
 * enqueues it (TempIndex /enqueue). Idempotent: re-activating an
 * id that already has a record returns its ORIGINAL tick and
 * re-enqueues it (crash recovery — a /put that landed without
 * its /enqueue is repaired by the retry, never re-numbered).
 *
 * Auth: the shared secret (x-lucid-ping-key), same as /admin/*
 * and /ping — the client already holds it (pingServer.ts
 * pingHeaders). No secret configured locally = open, like the
 * other routes. 0 neurons, 0 SP — plain DO reads/writes, never
 * Workers AI. One activation per temp, ever; a temp with no
 * referral activates fine and the grab will mark it
 * not_verified (no_referral). A referrer that does not exist
 * yet is fine too — the grab marks the temp pending until the
 * referrer verifies, or not_verified (referral_broken) if the
 * referrer never appears.
 *
 * Failure mode, stated: if /put lands and /enqueue throws, the
 * call answers 500 with the record created but not queued — the
 * client retries, and the retry takes the resumed path and
 * enqueues it. A DO failure fails loud (same contract as the
 * grab); nothing is silently half-activated.
 */
async function handleTempActivate(request, env) {
  if (!(await authorizedClient(request, env))) {
    return errorResponse(401, 'unauthorized: missing or wrong x-lucid-ping-key');
  }
  let body = {};
  try {
    body = await request.json();
  } catch {
    return errorResponse(400, 'invalid JSON body');
  }
  const id = body.id;
  const referralId = body.referralId ?? null;
  const windowStart = body.windowStart ?? null;
  if (
    typeof id !== 'string' ||
    !id.startsWith('profile-') ||
    id.length <= 'profile-'.length ||
    (referralId !== null && typeof referralId !== 'string') ||
    (referralId !== null && referralId.length === 0) ||
    (windowStart !== null && (typeof windowStart !== 'string' || Number.isNaN(Date.parse(windowStart))))
  ) {
    return errorResponse(400, 'id must be a profile-<uuid> string; referralId a non-empty string or null; windowStart an ISO timestamp or null');
  }
  const nowMs = Date.now();
  // The per-install user id that activated this temp (the
  // x-lucid-user header — the same id the SP bucket is keyed
  // by). It binds the temp to the install that owns it, so the
  // verified SP grant can only ever land on that install. Null
  // when the caller sent no usable header — the temp still
  // activates and can still verify, but no SP grant can bind
  // to it until a re-activation carries the header.
  const ownerUserId = userId(request);
  const existing = await doJson(tempRecordStub(env, id), '/get');
  if (existing.record) {
    // Resumed: the tick is the original, never re-numbered.
    // Re-enqueue (idempotent by key) in case the first
    // activation's /enqueue never landed.
    await doJson(tempIndexStub(env, shardForTick(existing.record.activationTick)), '/enqueue', {
      activationTick: existing.record.activationTick,
      id,
      referralId: existing.record.referralId,
    });
    // An already-verified record re-activating under its owner
    // re-marks the SP bucket (idempotent) — the grant survives
    // a grab that verified the temp but crashed before marking.
    if (existing.record.verificationState === 'verified' && ownerUserId) {
      await markUserVerified(env, ownerUserId);
    }
    return jsonResponse(200, {
      ok: true,
      resumed: true,
      id,
      activationTick: existing.record.activationTick,
      verificationState: existing.record.verificationState,
      windowEnd: existing.record.windowEnd,
      referralId: existing.record.referralId,
    });
  }
  const { tick } = await doJson(grabStateStub(env), '/next-tick', {});
  const built = newActivationRecord({
    id,
    referralId,
    activationTick: tick,
    windowStart: windowStart ?? undefined,
    nowMs,
    ownerUserId,
  });
  const { ok, record, error } = validateTempRecord(built);
  if (!ok) return errorResponse(400, error);
  await doJson(tempRecordStub(env, id), '/put', { record });
  await doJson(tempIndexStub(env, shardForTick(tick)), '/enqueue', {
    activationTick: tick,
    id,
    referralId: record.referralId,
  });
  return jsonResponse(200, {
    ok: true,
    resumed: false,
    id,
    activationTick: tick,
    verificationState: record.verificationState,
    windowEnd: record.windowEnd,
    referralId: record.referralId,
  });
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
          verified: { refill: 1000, period_hours: 24, cap: 'none — the on-hand balance is the cap', applies_when: 'temp verified by the daily grab' },
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
          'POST /register',
          'POST /admin/progress',
          'GET /admin/progress',
          'POST /admin/grab',
          'GET /admin/grab',
          'GET /admin/grab-outcomes',
          'POST /admin/rotate',
          'POST /temp/activate',
        ],
        temp: {
          note: 'The yield intake (step 1 of the dailies — how a client temp record enters the store). POST /temp/activate registers one temp: the client sends its profile-<uuid> id and the referral that brought it in; the server assigns the activation tick (monotonic, never re-numbered), stores the record and enqueues it. Idempotent — re-activating an id returns its original tick. 0 neurons, 0 SP. DISCARD: when the grab applies a terminal outcome (verified / not_verified / expired) it marks that tick\'s queue entry done — the entry is discarded from the nightly walk (the driver skips it), the key stays so the grab\'s density-based stopping rule still holds, and the record + outcome log are never deleted. Pending records are re-checked by every grab.',
          activation_tick: 'server-assigned, GrabState /next-tick, first tick 1',
          window: 'activation + 1 year',
        },
        grab: {
          note: 'The daily grab (step 2 of the dailies — how temps are verified). One grab a day at 12:00 AM America/Vancouver: chunked passes over the sharded temp index, in activation-tick order. 0 neurons, 0 SP — plain Durable Object reads/writes, never Workers AI. POST /admin/grab runs one chunk (and chains the next unless the body says chain: false); GET /admin/grab reads the grab state; GET /admin/grab-outcomes reads the outcome log (the publish step reads it to write the FixNet Pages status table). The status lookup (any temp checks verified/pending/not verified) is step 3, through the FixNet connection — not this route.',
          daily_cap: GRAB_DAILY_CAP,
          cap_overflow: 'queue_next_day',
          shard_width_ticks: GRAB_SHARD_WIDTH,
          chunk_records: GRAB_CHUNK_RECORDS,
          cpu_budget_ms: GRAB_CPU_BUDGET_MS,
          subrequest_limit: GRAB_SUBREQUEST_LIMIT,
          timezone: GRAB_TIMEZONE,
        },
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

    // The daily grab (step 2 of the dailies — how temps are
    // verified). Plain DO reads/writes, routed before the AI
    // path so they can never invoke the model; 0 neurons, 0 SP.
    // POST runs one chunk (and chains the next unless the body
    // says chain: false); GET reads the grab state.
    if (url.pathname === '/admin/grab' && request.method === 'POST') {
      return handleGrabPost(request, env, ctx);
    }

    if (url.pathname === '/admin/grab' && request.method === 'GET') {
      return handleGrabGet(request, env);
    }

    if (url.pathname === '/admin/grab-outcomes' && request.method === 'GET') {
      return handleGrabOutcomes(request, env);
    }

    // Rotation backfill (FixNet temp rotation, design D3 — the
    // one-time endpoint for already-verified temps that never
    // re-enter the grab walk). Admin key only; 0 neurons, 0 SP.
    if (url.pathname === '/admin/rotate' && request.method === 'POST') {
      return handleRotatePost(request, env);
    }

    // Per-install key registration (Fix 2 — the default ping
    // server works without manual key entry). Plain DO
    // read/write, routed before the AI path so it can never
    // invoke the model; 0 neurons, 0 SP. POST /register mints
    // one key per userId (re-issue returns the same key). No
    // auth — it is the provisioning endpoint for a client that
    // has no key yet.
    if (url.pathname === '/register' && request.method === 'POST') {
      return handleRegister(request, env);
    }

    // The yield intake (step 1 of the dailies — how a client's
    // temp record enters the store). Plain DO reads/writes,
    // routed before the AI path so it can never invoke the
    // model; 0 neurons, 0 SP. POST /temp/activate registers one
    // temp (shared secret or a per-install key for that user).
    if (url.pathname === '/temp/activate' && request.method === 'POST') {
      return handleTempActivate(request, env);
    }

    if (url.pathname === '/v1/chat/completions' && request.method === 'POST') {
      return handleChatCompletions(request, env, ctx);
    }

    return errorResponse(404, `not found: ${request.method} ${url.pathname}`);
  },

  /**
   * Cron wake-up (hourly — see [triggers] in wrangler.toml).
   * The grab runs at 12:00 AM America/Vancouver; the handler
   * gates on the local hour via Intl, so it follows the
   * runtime's tz database — BC is on permanent Pacific time
   * (PCT, UTC-7) from 1 Nov 2026, so 12am Gary's time is 07:00
   * UTC year-round (tzdata 2026b+; a stale-tzdata runtime would
   * fire at 08:00 UTC instead — same UTC day, one hour late).
   * The handler does nothing the other 23 hours. When it is the
   * grab hour it runs one chunk of today's grab and chains the
   * rest via the GRAB_PUBLIC_URL var; a grab already done today
   * is a no-op, and a stalled grab (a broken chain) resumes
   * from its cursor. The cron is the backstop — the chain does
   * the bulk of the work back-to-back, the hourly wake-up
   * catches anything the chain dropped.
   */
  async scheduled(event, env, ctx) {
    const nowMs = event.scheduledTime;
    if (!isGrabHour(nowMs)) return;
    try {
      await grabStep(env, ctx, { nowMs, chain: true, origin: env.GRAB_PUBLIC_URL ?? null });
    } catch (err) {
      // A failed wake-up must never throw out of scheduled():
      // the cursor is the truth and the next hourly wake-up
      // retries. Log loudly instead.
      console.log(`[grab] scheduled wake-up failed: ${err instanceof Error ? err.message : String(err)}`);
    }
  },
};
