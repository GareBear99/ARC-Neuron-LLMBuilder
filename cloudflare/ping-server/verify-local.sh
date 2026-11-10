#!/usr/bin/env bash
# Local verification for the Lucid ping server.
#
# Starts `wrangler dev --local` on port 8787, curls every route, prints
# the transcripts, stops the server. No Cloudflare account, no deploy,
# no real model call — under local dev the AI binding throws "Binding AI
# needs to be run remotely", so the Worker answers chat completions from
# its labelled mock (see worker.js "Mock mode"). The Durable Object
# rate limiter runs in miniflare, so the quota IS verified for real.
# NOTE: local DO state persists on disk under .wrangler/state between
# runs (that is miniflare's local persistence — and proof the counter
# is durable, not in-memory). The quota test therefore uses run-unique
# user ids (pid + timestamp), so a re-run never inherits a spent quota
# from the previous run.
#
# Expected results (hand-checkable):
#   GET  /                                  -> 200, mode "live" (the AI
#                                              binding is present under
#                                              local dev — the ground
#                                              truth for mock is the
#                                              x-lucid-ping-mock header
#                                              on chat responses),
#                                              maintenance: null, and a
#                                              server_caps block with the
#                                              10,000 neurons/day and
#                                              100,000 requests/day caps
#   POST /ping {message:"hello", n:1}        -> 200, echo EQUALS the sent
#                                              object, quota block present
#                                              when x-lucid-user is sent,
#                                              maintenance: null
#   POST /v1/chat/completions stream:true    -> 200 text/event-stream,
#                                              chunks + `data: [DONE]`,
#                                              text starts "[mock reply ...]",
#                                              header x-lucid-ping-mock: true,
#                                              x-ratelimit-remaining: 99
#                                              (first spend for that user)
#   POST /v1/chat/completions stream:false   -> 200 JSON, choices[0].message.content
#                                              contains "[mock reply ...]"
#   POST /ping with a wrong key              -> 401 unauthorized
#   POST /ping with no key (secret is set)   -> 401 unauthorized
#   POST /v1/chat/completions with tools     -> 400 tools not supported
#   POST /v1/chat/completions, no x-lucid-user -> 400 identity required
#   GET  /nope                              -> 404
#   Models (body.model routing): the allowlisted model (Llama 3.2 1B)
#   in body.model is served and named in the response `.model`; an
#   unknown model, or no model, falls back to the default
#   (@cf/meta/llama-3.2-1b-instruct). Every request costs exactly 1
#   SP. GET / lists the single allowlisted model. Gary's decision
#   (2026-11-06): ONLY Llama 3.2 1B — the other 33 models were
#   removed (neurons, 10,000/day, are the only quota that matters).
#   Quota (token bucket, SP — stock points): a new user starts at 100
#   SP. User A spends 100 SP; the 100th shows remaining 0, the 101st
#   -> 429 with limit 200, reset (unix, next refill) and a Retry-After
#   header. User B is unaffected (200). /ping as user A still answers
#   200 and reports remaining 0 (unmetered). A fresh user C proves
#   /ping never deducts: two /ping calls both report 100 SP, one chat
#   spend drops it to 99, /ping still reports 99.
set -u
cd "$(dirname "$0")"

PORT=8787
BASE="http://127.0.0.1:$PORT"
TEST_SECRET="ping-test-secret"
# Run-unique: local DO state persists between runs (see header note).
USER_A="verify-user-a-$$-$(date +%s)"
USER_B="verify-user-b-$$-$(date +%s)"
USER_C="verify-user-c-$$-$(date +%s)"
USER_M="verify-user-m-$$-$(date +%s)"

# --- test-only secret: wrangler dev reads .dev.vars for local secrets.
# Back up an existing one, restore it on exit; the test secret is a
# throwaway and is never committed (.dev.vars is gitignored).
HAD_DEV_VARS=0
[ -f .dev.vars ] && HAD_DEV_VARS=1 && cp .dev.vars .dev.vars.verify-bak
printf 'PING_SHARED_SECRET=%s\n' "$TEST_SECRET" > .dev.vars

cleanup() {
  # Kill whatever listens on the port. A plain `kill $DEV_PID` only
  # kills the npx wrapper — the node server survives, holds the port,
  # and the next run's curls silently hit the stale server (that exact
  # failure bit the 2026-11-06 verify run: wrong-key /ping returned 200
  # from a stale server whose env had been hot-reloaded without
  # .dev.vars). fuser kills by port, so it cannot miss the real
  # listener; the pkill pattern is the backup. The [w] bracket keeps
  # pkill from matching this script's own command line.
  fuser -k "$PORT/tcp" 2>/dev/null || true
  pkill -f "[w]rangler dev --local --port $PORT" 2>/dev/null || true
  if [ -n "${DEV_PID:-}" ] && kill -0 "$DEV_PID" 2>/dev/null; then kill "$DEV_PID" 2>/dev/null; wait "$DEV_PID" 2>/dev/null; fi
  sleep 1
  if curl -fsS -o /dev/null -m 1 "$BASE/" 2>/dev/null; then echo "WARNING: port $PORT still answering after cleanup" >&2; fi
  if [ "$HAD_DEV_VARS" = 1 ]; then mv -f .dev.vars.verify-bak .dev.vars; else rm -f .dev.vars; fi
}
trap cleanup EXIT

# --- make sure no stale server holds the port (see cleanup note)
fuser -k "$PORT/tcp" 2>/dev/null || true
pkill -f "[w]rangler dev --local --port $PORT" 2>/dev/null || true
sleep 1
for _ in $(seq 1 10); do
  curl -fsS -o /dev/null -m 1 "$BASE/" 2>/dev/null || break
  sleep 1
done
if curl -fsS -o /dev/null -m 1 "$BASE/" 2>/dev/null; then
  echo "FAIL: port $PORT is still answering after killing stale servers"
  exit 1
fi

# --- start local dev server
npx --no-install wrangler dev --local --port "$PORT" > /tmp/lucid-ping-verify.log 2>&1 &
DEV_PID=$!

for _ in $(seq 1 30); do
  curl -fsS -o /dev/null "$BASE/" 2>/dev/null && break
  sleep 1
done
curl -fsS -o /dev/null "$BASE/" || { echo "FAIL: wrangler dev did not come up"; tail -20 /tmp/lucid-ping-verify.log; exit 1; }
# Prove this is OUR server, not a stale one: the log must show the
# secret loaded and no address-in-use error.
if grep -q "Address already in use" /tmp/lucid-ping-verify.log; then
  echo "FAIL: wrangler dev hit 'Address already in use' — a stale server holds $PORT"
  exit 1
fi
grep -q "Using secrets defined in .dev.vars" /tmp/lucid-ping-verify.log || { echo "FAIL: wrangler dev did not load .dev.vars (no test secret)"; exit 1; }
echo "== wrangler dev up on $BASE (pid $DEV_PID)"
echo

echo "== 1. GET /"
curl -sS "$BASE/" -o /tmp/lucid-ping-service.json
cat /tmp/lucid-ping-service.json
grep -q '"unit": "SP"' /tmp/lucid-ping-service.json || { echo "FAIL: service card does not report the SP bucket"; exit 1; }
grep -q '"cap": 250' /tmp/lucid-ping-service.json || { echo "FAIL: service card does not report the 250 SP stage-2 cap"; exit 1; }
grep -q '"maintenance": null' /tmp/lucid-ping-service.json || { echo "FAIL: service card does not report maintenance: null"; exit 1; }
grep -q '"neurons_per_day": 10000' /tmp/lucid-ping-service.json || { echo "FAIL: service card does not report the 10,000 neurons/day cap"; exit 1; }
grep -q '"requests_per_day": 100000' /tmp/lucid-ping-service.json || { echo "FAIL: service card does not report the 100,000 requests/day cap"; exit 1; }
echo; echo

echo "== 2. POST /ping  {\"message\":\"hello\",\"n\":1} as $USER_A  (expect echo to equal the sent object + quota block + maintenance: null)"
curl -sS -X POST "$BASE/ping" -H 'content-type: application/json' -H "x-lucid-ping-key: $TEST_SECRET" -H "x-lucid-user: $USER_A" -d '{"message":"hello","n":1}' -o /tmp/lucid-ping-hello.json
cat /tmp/lucid-ping-hello.json
grep -q '"maintenance": null' /tmp/lucid-ping-hello.json || { echo "FAIL: /ping does not report maintenance: null"; exit 1; }
echo; echo

echo "== 3. POST /v1/chat/completions stream:true as $USER_A  (expect SSE chunks + data: [DONE], mock marker, remaining 99)"
curl -sS -N -D - -X POST "$BASE/v1/chat/completions" -H 'content-type: application/json' -H "x-lucid-ping-key: $TEST_SECRET" -H "x-lucid-user: $USER_A" -d '{"messages":[{"role":"user","content":"Say the word PINGBACK and nothing else."}],"stream":true}' -o /tmp/lucid-ping-stream.txt
cat /tmp/lucid-ping-stream.txt
echo; echo

echo "== 4. POST /v1/chat/completions stream:false as $USER_A  (expect JSON choices[0].message.content)"
curl -sS -X POST "$BASE/v1/chat/completions" -H 'content-type: application/json' -H "x-lucid-ping-key: $TEST_SECRET" -H "x-lucid-user: $USER_A" -d '{"messages":[{"role":"user","content":"Say the word PINGBACK and nothing else."}],"stream":false}'
echo; echo

echo "== 5. POST /ping with a WRONG key  (expect 401)"
curl -sS -w '\nHTTP %{http_code}\n' -X POST "$BASE/ping" -H 'content-type: application/json' -H 'x-lucid-ping-key: wrong-key' -d '{"message":"hello"}'
echo

echo "== 6. POST /ping with NO key  (expect 401)"
curl -sS -w '\nHTTP %{http_code}\n' -X POST "$BASE/ping" -H 'content-type: application/json' -d '{"message":"hello"}'
echo

echo "== 7. POST /v1/chat/completions with tools  (expect 400)"
curl -sS -w '\nHTTP %{http_code}\n' -X POST "$BASE/v1/chat/completions" -H 'content-type: application/json' -H "x-lucid-ping-key: $TEST_SECRET" -H "x-lucid-user: $USER_A" -d '{"messages":[{"role":"user","content":"hi"}],"tools":[]}'
echo

echo "== 8. POST /v1/chat/completions with NO x-lucid-user  (expect 400)"
curl -sS -w '\nHTTP %{http_code}\n' -X POST "$BASE/v1/chat/completions" -H 'content-type: application/json' -H "x-lucid-ping-key: $TEST_SECRET" -d '{"messages":[{"role":"user","content":"hi"}]}'
echo

echo "== 9. GET /nope  (expect 404)"
curl -sS -w '\nHTTP %{http_code}\n' "$BASE/nope"
echo

echo "== 9b. MODELS: body.model routing (fresh $USER_M — every request costs exactly 1 SP)"
echo "    allowlisted model (expect 200, .model == @cf/meta/llama-3.2-1b-instruct, remaining 99):"
curl -sS -D /tmp/lucid-ping-m1.h -X POST "$BASE/v1/chat/completions" -H 'content-type: application/json' -H "x-lucid-ping-key: $TEST_SECRET" -H "x-lucid-user: $USER_M" -d '{"messages":[{"role":"user","content":"hi"}],"model":"@cf/meta/llama-3.2-1b-instruct","stream":false}' -o /tmp/lucid-ping-m1.json
cat /tmp/lucid-ping-m1.json
grep -q '"model": "@cf/meta/llama-3.2-1b-instruct"' /tmp/lucid-ping-m1.json || { echo "FAIL: allowlisted model was not served"; exit 1; }
grep -qi 'x-ratelimit-remaining: 99' /tmp/lucid-ping-m1.h || { echo "FAIL: allowlisted-model request did not cost exactly 1 SP"; cat /tmp/lucid-ping-m1.h; exit 1; }
echo "    unknown model (expect 200, .model falls back to the default @cf/meta/llama-3.2-1b-instruct):"
curl -sS -X POST "$BASE/v1/chat/completions" -H 'content-type: application/json' -H "x-lucid-ping-key: $TEST_SECRET" -H "x-lucid-user: $USER_M" -d '{"messages":[{"role":"user","content":"hi"}],"model":"@cf/meta/llama-9-999b-instruct","stream":false}' -o /tmp/lucid-ping-m2.json
grep -q '"model": "@cf/meta/llama-3.2-1b-instruct"' /tmp/lucid-ping-m2.json || { echo "FAIL: unknown model did not fall back to the default"; exit 1; }
echo "    no model (expect 200, .model == default):"
curl -sS -X POST "$BASE/v1/chat/completions" -H 'content-type: application/json' -H "x-lucid-ping-key: $TEST_SECRET" -H "x-lucid-user: $USER_M" -d '{"messages":[{"role":"user","content":"hi"}],"stream":false}' -o /tmp/lucid-ping-m3.json
grep -q '"model": "@cf/meta/llama-3.2-1b-instruct"' /tmp/lucid-ping-m3.json || { echo "FAIL: absent model did not fall back to the default"; exit 1; }
echo "    service card lists the single allowlisted model (expect models.length 1, the default 1B only):"
node -e "const s=require('/tmp/lucid-ping-service.json'); if(!Array.isArray(s.models)||s.models.length!==1){console.error('FAIL: service card models.length is '+(s.models&&s.models.length));process.exit(1);} if(s.models[0]!=='@cf/meta/llama-3.2-1b-instruct'){console.error('FAIL: service card models is not exactly the 1B default');process.exit(1);} console.log('    models.length 1, only the 1B default');"
echo

echo "== 10. QUOTA: $USER_A has spent 2 SP so far (sections 3-4). Spend 97 more quietly (99 total)..."
for _ in $(seq 1 97); do
  code=$(curl -sS -o /dev/null -w '%{http_code}' -X POST "$BASE/v1/chat/completions" -H 'content-type: application/json' -H "x-lucid-ping-key: $TEST_SECRET" -H "x-lucid-user: $USER_A" -d '{"messages":[{"role":"user","content":"hi"}],"stream":false}')
  [ "$code" = "200" ] || { echo "FAIL: quota spend request returned HTTP $code"; exit 1; }
done
echo "    97 spent, 99 total. 100th request (expect remaining 0):"
curl -sS -D - -X POST "$BASE/v1/chat/completions" -H 'content-type: application/json' -H "x-lucid-ping-key: $TEST_SECRET" -H "x-lucid-user: $USER_A" -d '{"messages":[{"role":"user","content":"hi"}],"stream":false}' -o /tmp/lucid-ping-100th.txt
cat /tmp/lucid-ping-100th.txt
echo; echo

echo "== 11. QUOTA: 101st request as $USER_A  (expect 429 with limit 200, reset (next refill), Retry-After)"
curl -sS -D - -X POST "$BASE/v1/chat/completions" -H 'content-type: application/json' -H "x-lucid-ping-key: $TEST_SECRET" -H "x-lucid-user: $USER_A" -d '{"messages":[{"role":"user","content":"hi"}],"stream":false}' -o /tmp/lucid-ping-101st.txt
cat /tmp/lucid-ping-101st.txt
echo; echo

echo "== 12. QUOTA: 1 request as $USER_B  (expect 200 — a different user is unaffected)"
curl -sS -w '\nHTTP %{http_code}\n' -X POST "$BASE/v1/chat/completions" -H 'content-type: application/json' -H "x-lucid-ping-key: $TEST_SECRET" -H "x-lucid-user: $USER_B" -d '{"messages":[{"role":"user","content":"hi"}],"stream":false}'
echo

echo "== 13. QUOTA: /ping as $USER_A  (expect 200, quota.remaining 0 — /ping is unmetered)"
curl -sS -X POST "$BASE/ping" -H 'content-type: application/json' -H "x-lucid-ping-key: $TEST_SECRET" -H "x-lucid-user: $USER_A" -d '{"message":"hello"}'
echo; echo

echo "== 14. QUOTA: /ping never deducts (fresh $USER_C — registration costs 0 SP)"
echo "    /ping #1 (expect 200, quota.remaining 100 SP, stock_points 100):"
curl -sS -X POST "$BASE/ping" -H 'content-type: application/json' -H "x-lucid-ping-key: $TEST_SECRET" -H "x-lucid-user: $USER_C" -d '{"message":"hello"}' -o /tmp/lucid-ping-c1.json
cat /tmp/lucid-ping-c1.json
grep -q '"remaining": 100' /tmp/lucid-ping-c1.json || { echo "FAIL: first /ping did not report 100 SP"; exit 1; }
grep -q '"stock_points": 100' /tmp/lucid-ping-c1.json || { echo "FAIL: /ping did not report stock_points"; exit 1; }
echo "    /ping #2 (expect 200, still 100 SP — /ping costs 0 SP):"
curl -sS -X POST "$BASE/ping" -H 'content-type: application/json' -H "x-lucid-ping-key: $TEST_SECRET" -H "x-lucid-user: $USER_C" -d '{"message":"hello"}' -o /tmp/lucid-ping-c2.json
grep -q '"remaining": 100' /tmp/lucid-ping-c2.json || { echo "FAIL: second /ping deducted SP"; exit 1; }
echo "    one chat spend (expect x-ratelimit-remaining: 99):"
curl -sS -D /tmp/lucid-ping-c-spend.h -o /dev/null -X POST "$BASE/v1/chat/completions" -H 'content-type: application/json' -H "x-lucid-ping-key: $TEST_SECRET" -H "x-lucid-user: $USER_C" -d '{"messages":[{"role":"user","content":"hi"}],"stream":false}'
grep -qi 'x-ratelimit-remaining: 99' /tmp/lucid-ping-c-spend.h || { echo "FAIL: chat spend did not leave 99 SP"; cat /tmp/lucid-ping-c-spend.h; exit 1; }
echo "    /ping #3 (expect 200, remaining 99 SP):"
curl -sS -X POST "$BASE/ping" -H 'content-type: application/json' -H "x-lucid-ping-key: $TEST_SECRET" -H "x-lucid-user: $USER_C" -d '{"message":"hello"}' -o /tmp/lucid-ping-c3.json
grep -q '"remaining": 99' /tmp/lucid-ping-c3.json || { echo "FAIL: /ping after spend did not report 99 SP"; exit 1; }
echo; echo

echo "== 15. PROGRESS: POST /admin/progress then GET /admin/progress (0 neurons, 0 SP — plain DO read/write)"
echo "    POST a train event (expect 200, ok true, percent 27.6, bar with 27.6%):"
curl -sS -X POST "$BASE/admin/progress" -H 'content-type: application/json' -H "x-lucid-ping-key: $TEST_SECRET" -d '{"stage":"train","status":"running","step":42,"total":152,"percent":27.6,"bar":"[██████░░░░░░░░░░░░░░] 27.6%","loss":1.23,"eta_seconds":540,"run_id":"verify-run","message":"Training step 42/152"}' -o /tmp/lucid-ping-prog-post.json
cat /tmp/lucid-ping-prog-post.json
grep -q '"percent": 27.6' /tmp/lucid-ping-prog-post.json || { echo "FAIL: progress POST did not store percent 27.6"; exit 1; }
grep -q '27.6%' /tmp/lucid-ping-prog-post.json || { echo "FAIL: progress POST did not store the bar"; exit 1; }
echo "    GET (expect 200, same record back — the queryable training-side endpoint):"
curl -sS "$BASE/admin/progress" -H "x-lucid-ping-key: $TEST_SECRET" -o /tmp/lucid-ping-prog-get.json
cat /tmp/lucid-ping-prog-get.json
grep -q '"stage": "train"' /tmp/lucid-ping-prog-get.json || { echo "FAIL: progress GET did not return the train record"; exit 1; }
grep -q '"run_id": "verify-run"' /tmp/lucid-ping-prog-get.json || { echo "FAIL: progress GET did not return the run id"; exit 1; }
echo "    GET with a WRONG key (expect 401):"
curl -sS -w '\nHTTP %{http_code}\n' "$BASE/admin/progress" -H 'x-lucid-ping-key: wrong-key'
echo "    POST with a bad body (expect 400):"
curl -sS -w '\nHTTP %{http_code}\n' -X POST "$BASE/admin/progress" -H 'content-type: application/json' -H "x-lucid-ping-key: $TEST_SECRET" -d '{"step":1}'
echo; echo

echo "== done. wrangler dev log tail:"
tail -5 /tmp/lucid-ping-verify.log
