# Lucid ping server

A Cloudflare Worker — the first working test dummy for the
**Lucid → Cloudflare → model → stream** path, and the repo-to-Cloudflare
bridge for the LLMBuilder. A Worker is global edge by nature: that *is*
the "global user connect stream". The stream itself is the SSE token
stream from the model. Our own trained GGUF swaps in behind this same
Worker later.

Scope, deliberately small: no user accounts, no presence system, no auth
service. Two routes and a service card. That is the whole dummy.

## Routes

| Route | What it does |
|---|---|
| `GET /` | Service card: name, version, model, mode (`live`/`mock`), routes. |
| `POST /ping` | Health + echo. Send any JSON; it comes back under `echo`, with `ok`, `model`, `mode`, `ts`. Proves the round trip. |
| `POST /v1/chat/completions` | OpenAI-compatible. Body `{ messages: [{role, content}], model?, stream? }`. `model` names a Workers AI model from the allowlist (see "The models" below); absent or unknown falls back to the default. `stream: true` (the default) returns SSE `data: {choices:[{delta:{content}}]}` chunks ending in `data: [DONE]`. `stream: false` returns the OpenAI JSON shape. `tools` is rejected with 400 — the dummy model does not do tool calls. Every model costs 1 SP per request. |
| `POST /admin/progress` | A chain step reports a progress event. Body `{ stage, status?, step?, total?, percent?, bar?, loss?, eta_seconds?, run_id?, message? }`. Admin key required. 0 neurons, 0 SP — plain DO write. |
| `GET /admin/progress` | The queryable training-side endpoint: the current progress (`stage`, `status`, `step`, `total`, `percent`, `bar`, `loss`, `eta_seconds`, `run_id`, `message`, `updated_at`, `age_seconds`), or `progress: null` when nothing has been reported. Admin key required. On-demand pull, 0 neurons, 0 SP — plain DO read. |

## Auth (dummy)

A shared-secret header. If the Worker has a `PING_SHARED_SECRET` secret
set, `/ping` and `/v1/chat/completions` require

```
x-lucid-ping-key: <secret>
```

and answer `401 { "error": "unauthorized..." }` without it. If no secret
is set, the routes are open. This is a test dummy, never a production
gate — the secret is rotatable and must never be a real credential.

Set the secret for real deploys with `wrangler secret put PING_SHARED_SECRET`.
For local dev, copy `.dev.vars.example` to `.dev.vars` (gitignored) and
fill it in.

## Identity + quota — token bucket in SP (stock points)

The quota is a **token bucket of SP (stock points)**, enforced
server-side, and the server is the sole authority on it — nothing
about the bucket is computed or enforced anywhere else. **1 SP per
chat completion request.** SP are like credits: the balance is the
user's credit balance. The quota keys off the `x-lucid-user` header:
a per-install id the Lucid client generates once (a random UUID,
stored in settings) and sends on every request. It is **not** an
account — no registration, no PII — and rotating it resets the quota.
That is dummy-grade identity, said plainly: it stops casual overuse
and gives every install a fair share, it does not stop a determined
user from minting a new id.

- New users start at **100 SP**.
- Refills, two stages, decided by the balance at refill time:
  **below 200 SP, +25 SP every 4 hours, cap 200**; **at or above
  200 SP, +20 SP every 12 hours, cap 250** — so an idle user climbs
  200 → 220 → 240 → 250 and no user can ever hold more than 250 SP.
  If the balance drops below 200 through use, refills go back to
  +25/4h, cap 200, until it reaches 200 again. Refills are whole
  periods only, so partial periods are never lost.
- `POST /v1/chat/completions` **requires** `x-lucid-user`
  (1–128 chars, `[A-Za-z0-9._-]`); without it the Worker answers 400.
- The bucket lives in a Durable Object — one stub per user id, in DO
  storage (see `bucket.js`). A DO is used because it is consistent
  per user: an in-memory Map would reset on isolate eviction and
  differ across the edge, and KV increments are racy. This is
  Cloudflare's own documented rate-limiting shape.
- `POST /ping` is the registration / health check: it costs **0 SP**
  — it never deducts and never 429s. It reports the caller's SP
  balance for free (when `x-lucid-user` is present), as
  `quota.stock_points` in the body plus the `x-ratelimit-*` headers,
  so a client can always show its balance without spending a request.
- When the bucket is empty the Worker answers **429** with the limit
  (the user's current cap, 200 or 250), the next-refill time (unix
  seconds + seconds until refill), and a `Retry-After` header. Every
  chat response also carries `x-ratelimit-limit` /
  `x-ratelimit-remaining` / `x-ratelimit-reset` headers, where the
  limit is the current cap and the reset is the next refill.

Ceiling check: Workers Free allows 100,000 requests/day total, and
the Workers AI free allocation is **10,000 neurons/day, no credit
card** — that neuron budget, not the SP bucket, is the real ceiling
on total usage: it covers roughly a thousand short test replies a
day across ALL users. Past that, the Worker needs the Paid plan or a
lower per-user limit — a Gary decision, not a code change.

## Maintenance mode — 24 hours on a server-side cap hit

Gary's rule (2026-11-07): if a server-side cap is ever hit, the
server goes down for 24 hours for maintenance instead of continuing
degraded or hammering a maxed-out cap.

- **Triggers (either one trips it):** (1) the estimated neuron
  usage for the UTC day reaches **10,000**; (2) chat completions
  for the UTC day reach **100,000**; (3) an `AI.run()` error whose
  message says the quota/neurons are exhausted (the platform
  itself reporting the cap — best-effort match, the estimate is
  the primary trigger).
- **The window is 24 hours from the trip moment** (not a calendar
  day). Expiry is derived from time, so the Worker resumes by
  itself — no cleanup job, nothing to miss.
- **In maintenance, `POST /v1/chat/completions` answers 503**
  with the reason, the return time (`back_at`, `back_in_seconds`)
  and a `Retry-After` header, and spends **no SP** — the request
  never reaches the per-user bucket.
- **`GET /` and `POST /ping` keep working** and report the
  maintenance state honestly (`maintenance` field, `null` when up).
  `/ping` still costs 0 SP and never 429s.
- **State lives in a second Durable Object** (`PingServerUsage`,
  one global stub) in DO storage, so a restart or redeploy does
  not clear the window. The daily counters reset on UTC-day
  rollover, but an active window survives the rollover until its
  24 hours are up. A second trip while already in maintenance does
  not reset the clock.
- **The neuron estimate is honest, not exact:** the AI response
  `usage` token counts are used when the platform provides them;
  otherwise the estimate is ~4 chars per token on the prompt and
  the reply (streaming replies usually carry no usage). Estimates
  stay fractional so a day of tiny requests is not over-counted.
  Mock replies (local dev) spend 0 neurons but still count as a
  request. The request counter covers chat completions only — `GET
  /` and `/ping` are unmetered health endpoints, so it is a lower
  bound on total Worker invocations.
- **Known wart:** the request that trips the reactive trigger has
  already spent 1 SP (the SP spend happens before the model call,
  by design). There is no refund; the refill (+25 SP / 4h) covers
  it within hours. Requests rejected by the maintenance pre-check
  spend nothing.

## Chain progress — event-driven, queryable, 0 neurons

The training chain (train → merge → gguf → gate → r2 → manifest →
client) reports its progress, and an admin pulls it on demand.
Gary's rules (2026-11-10): **event-driven, no polling** and **it
cannot eat neurons** — and the heavy work does **not** go on the
neuron side.

The correct split:

- **GPU side (training, Colab T4) — the heavy work.** Training
  lives here, and so does progress computation. The trainer
  computes its own percent, ETA, and ASCII bar and pushes an update
  when an event happens (a step/milestone completes, a status
  changes). It is the queryable source of truth for its own
  progress. The trainer posts from its log callback (an event the
  trainer itself fires), batched so it never posts more often than
  10 steps / 30 seconds — plus start, complete, and fail events.
  There is no polling loop anywhere.
- **Neuron side (this Worker) — only a pass.** It stores what the
  training side reported (one record, latest wins, in a Durable
  Object) and serves it on demand. It is a plain pass-through: it
  NEVER computes progress (no percent derivation, no bar rendering,
  no ETA math), never trains, and never does inference for progress.
  It only validates the shape and stores/serves the values verbatim.
  The neuron side only handles a pass — a lightweight inference
  request (the ping fallback) — nothing heavy.
- **Lucid (client) — lightweight.** It just sends one GET that
  passes to the neuron side. The only strain on Lucid is that
  request. Lucid does not compute, store, or poll progress, and it
  never carries the training load.

**0 neurons, 0 SP:** the progress endpoints are plain Durable
Object reads/writes. They never call Workers AI, never go through
the chat-completions path, and never touch the per-user SP bucket.
Reading or writing progress costs 0 SP and 0 neurons. The Worker
routes them before the AI path so they cannot accidentally invoke
the model.

**Auth:** the shared secret (`x-lucid-ping-key`), the same key as
`/ping` and `/v1/chat/completions` — the admin key. Both endpoints
answer 401 without it.

**How the trainer reports** (`scripts/training/train_lora.py`):
enabled only when a ping key is configured — CLI
`--progress-key` / `--progress-url`, or env `LUCID_PING_KEY` /
`LUCID_PING_URL` (default URL: the live worker). No key → no
reporting, training is unchanged. The POST is fire-and-forget
(2s timeout, all errors swallowed) — a failed report can never
fail the training run. The key is never printed or logged. In
Colab, set `LUCID_PING_KEY` from a Colab secret.

**How other chain steps report** (`scripts/training/progress.py`,
stdlib only, reusable by merge/gguf/gate — same POST shape):

```bash
python scripts/training/progress.py --stage merge --step 1 --total 3 \
    --status completed --message "Adapter merged"
python scripts/training/progress.py --stage gguf --step 0 --total 1 \
    --message "GGUF convert started"
```

**How an admin pulls the progress** (one lightweight GET — a
pull, not a poll; replace `<secret>` with the shared secret):

```bash
curl -s https://lucid-ping-server.admension.workers.dev/admin/progress \
  -H 'x-lucid-ping-key: <secret>'
# {
#   "ok": true,
#   "progress": {
#     "stage": "train",
#     "status": "running",
#     "step": 42,
#     "total": 152,
#     "percent": 27.6,
#     "bar": "[██████░░░░░░░░░░░░░░] 27.6%",
#     "loss": 1.23,
#     "eta_seconds": 540,
#     "run_id": "lora-1b-20261110",
#     "message": "Training step 42/152",
#     "updated_at": "2026-11-10T22:00:00.000Z",
#     "age_seconds": 12
#   }
# }
```

`progress` is `null` when nothing has ever been reported.
`age_seconds` tells you how stale the number is (seconds since
the last update). A chain step reports an event the same way:

```bash
curl -s -X POST https://lucid-ping-server.admension.workers.dev/admin/progress \
  -H 'content-type: application/json' -H 'x-lucid-ping-key: <secret>' \
  -d '{"stage":"train","status":"running","step":42,"total":152,"percent":27.6,"bar":"[██████░░░░░░░░░░░░░░] 27.6%","loss":1.23,"eta_seconds":540,"run_id":"lora-1b-20261110","message":"Training step 42/152"}'
# { "ok": true, "progress": { ...same shape as the GET... } }
```

**Storage:** a third Durable Object (`PingProgress`, one global
stub `progress:current`, DO storage) — the same pattern as the
rate limiter and the server-usage counter. No KV, no paid service.
The record is the latest update only (no history). Tests:
`node progress.test.mjs` (12 checks) and
`python3 -m unittest tests.test_progress_reporter` (14 checks).

## The model — only Llama 3.2 1B, on the SP system

The client picks a model with `body.model` on
`POST /v1/chat/completions`. The Worker serves any model on the
allowlist in `worker.js` (`PING_MODELS`) — which, by Gary's
decision (2026-11-06), holds **only Llama 3.2 1B**
(`@cf/meta/llama-3.2-1b-instruct`, the default). Neurons
(10,000/day, Cloudflare free tier) are the only quota that
matters for scaling, and 1B is the only model we can support for
the user numbers we want (200-1000 users) within that budget —
the bigger models burn too many neurons to support that scale.
The other 33 models from Cloudflare's model catalog snapshot
(fetched 2026-11-06) were removed from the allowlist and from
the Lucid client's dropdown.

The service card (`GET /`) lists it under `models`, so a
client can build its picker from the server instead of hardcoding
the list.

**How `body.model` works:** only an exact allowlist match is
honoured. If `body.model` is absent, not a string, or not on the
allowlist, the Worker serves the default — `@cf/meta/llama-3.2-1b-instruct`,
set in `wrangler.toml` `[vars] MODEL` — and never answers 400 for
the model. An arbitrary client-supplied string is never passed to
the AI binding; that is the whole point of the allowlist.

**Excluded from the catalog's 39, deliberately:** the four
Cloudflare decision/extraction models (`@cf/cloudflare/clairic`,
`@cf/cloudflare/clef`, `@cf/cloudflare/clef-flash`,
`@cf/cloudflare/clef-omni`) — they take a typed-question schema, not
messages, so they cannot answer a chat request — and
`@cf/meta/llama-guard-3-8b`, a content-safety classifier whose output
is a safe/unsafe label, not a reply.

**They all run on the SP system:** every model costs **1 SP per
chat completion request**, the same as the default always did. A 70B
or 120B reply spends the same 1 SP as a 1B reply — the SP bucket
does not vary by model, and `POST /ping` is still unmetered (0 SP).
The real ceiling is still the Workers AI free allocation
(**10,000 neurons/day, no credit card**): the big models burn far
more neurons per reply than the 1B default, so a day of heavy 70B/120B
use will hit the neuron budget long before the SP bucket runs dry —
that is a Cloudflare billing ceiling, not an SP rule, and past it the
Worker needs the Paid plan or a lower per-user limit (a Gary
decision, not a code change).

The default, `@cf/meta/llama-3.2-1b-instruct`, is the cheapest Llama
chat model on the official Workers AI pricing page
(`developers.cloudflare.com/workers-ai/platform/pricing/`, checked
2026-11-06) — 2,457 neurons per M input tokens, 18,252 per M output
tokens. The free allocation covers roughly a thousand short test
replies a day at that size.

Cloudflare ships and retires Workers AI models without notice, so
the allowlist is a snapshot (2026-11-06). A retired model fails at
the AI binding with a loud 502, never a fake reply; re-check the
list against the catalog when a model stops working.

## Mock vs live

Under local `wrangler dev` the AI binding exists but `AI.run()`
throws "Binding AI needs to be run remotely" — the real binding only
works on the edge. The Worker catches exactly that error and answers
from a clearly-labelled mock: response header
`x-lucid-ping-mock: true`, and the streamed text itself starts with
`[mock reply — no Workers AI binding in local dev]`. Any other AI
error is a loud 502, never a silent mock. The mock proves the HTTP +
SSE shape end to end; it does **not** prove the model call. The real
model call is only proven after deploy — see below.

The `mode` field on `GET /` and `/ping` reports binding presence
(`live` when `env.AI` exists — which is also true under local dev),
so the **`x-lucid-ping-mock` header on a chat response is the ground
truth** for which path actually served that reply.

## Local verification

```bash
cd cloudflare/ping-server
node bucket.test.mjs      # SP bucket math — 22 checks, pure, no network
node models.test.mjs      # body.model routing + allowlist — 12 checks, pure
node maintenance.test.mjs # 24h maintenance mode math — 25 checks, pure
node serverUsage.test.mjs # server-usage DO routes — 9 checks, pure (fake storage)
node progress.test.mjs    # chain progress — 12 checks, pure (fake storage);
                          # POST + GET /admin/progress round-trip, 0 neurons, 0 SP
./verify-local.sh
```

`verify-local.sh` starts `wrangler dev --local` on port 8787, curls
`GET /`, `POST /ping` (echo case + free quota lookup),
`POST /v1/chat/completions` streamed and non-streamed, a wrong-key
401, a missing-identity 400, and then spends a whole 100-SP starting
balance for one test user to prove the 101st request gets a 429 with
a next-refill time (a second user is unaffected), and proves /ping
never deducts SP. It also proves the model routing end to end: an
allowlisted `body.model` is served and named in the response
`.model` (and still costs exactly 1 SP), an unknown model and an
absent model both fall back to the default, and `GET /` lists the
single allowlisted model (Llama 3.2 1B). Then it prints the transcripts and stops the
server. Expected results are written at the top of the script; the
mock replies are labelled mock, as above.

## Deploy — needs Gary's approval first

Do **not** deploy on your own. The deploy needs Gary's explicit
approval because it creates a live Worker on his Cloudflare account
(`Gdoman99@gmail.com`, subdomain `admension.workers.dev`) and the
first live call spends his free Workers AI neurons.

```bash
cd cloudflare/ping-server
npx wrangler login            # one-time, opens a browser OAuth flow
npx wrangler secret put PING_SHARED_SECRET
npx wrangler deploy
```

Expected URL: `https://lucid-ping-server.admension.workers.dev`

After deploy, verify live from any shell (replace `<secret>`):

```bash
curl -s -X POST https://lucid-ping-server.admension.workers.dev/ping \
  -H 'content-type: application/json' -H 'x-lucid-ping-key: <secret>' \
  -d '{"message":"hello"}'
# expect: { "ok": true, "mode": "live", ... }

curl -s -N -X POST https://lucid-ping-server.admension.workers.dev/v1/chat/completions \
  -H 'content-type: application/json' -H 'x-lucid-ping-key: <secret>' \
  -d '{"messages":[{"role":"user","content":"Say the word PINGBACK and nothing else."}],"stream":true}'
# expect: SSE chunks ending in data: [DONE], concatenated text contains PINGBACK,
# and the response header x-lucid-ping-mock: false
```

## Swapping in our own model

When the LLMBuilder promotes a GGUF worth serving, the swap happens
behind this same Worker, in one of two ways — the Worker contract
(`POST /v1/chat/completions`, SSE, `x-lucid-ping-key`) does not change,
so Lucid needs no update:

1. **llama.cpp server (repo's existing serving story):** run the GGUF
   under `llama.cpp:server` (see the repo's
   `docker-compose.local-backends.yml`) on a box with a GPU, and have
   the Worker proxy `/v1/chat/completions` to it instead of calling
   `env.AI.run`. The Worker stays the auth + routing front door.
2. **Workers AI custom model:** only if Cloudflare opens custom-model
   deployment below Enterprise — not available on the free tier today.

## Lucid side

`lucid-terminal`: `electron/services/pingServer.ts` (client) +
`electron/ipc/ai.ts` (routes `ai:chat` to the ping server when
Settings → AI → "Ping server (test)" is enabled) +
`src/components/Settings/SettingsPanel.tsx` (endpoint + key fields).
The client posts to `{endpoint}/v1/chat/completions` and streams the
SSE reply into the chat exactly like the OpenAI path does. Live test
against a local Worker (skipped unless the env var is set):

```bash
# terminal 1: start the Worker (see "Local verification" above)
# terminal 2:
cd ~/workspace/lucid-terminal
LUCID_PING_LIVE_URL=http://127.0.0.1:8787 LUCID_PING_KEY=ping-test-secret \
  npx vitest run tests/pingServerLive.test.ts
```
