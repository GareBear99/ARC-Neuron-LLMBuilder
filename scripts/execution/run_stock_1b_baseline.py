#!/usr/bin/env python3
"""Stock Llama 3.2 1B baseline harness — LLMBuilder (plan §5 Phase 2).

Runs the STOCK (un-fine-tuned) Meta Llama 3.2 1B through the repo's own
168-task benchmark (``benchmarks/``, 17 .jsonl files) and scores it with the
repo's scorer (``scorers/rubric.py``, scorer v2-task-aware) so the fine-tune
can later be judged against a real neural baseline.

Why this exists
---------------
The incumbent's 0.9237 (v10, ``arc_governed_v10_wave4``) is EXEMPLAR
RETRIEVAL (TF-IDF over 669 Q&A records), NOT a neural-network score. A neural
1B cannot honestly be compared against 0.9237 until the stock Llama 3.2 1B is
run through the same 168-task benchmark first. This harness produces that
number. Any claim that a fine-tune "beats v10" without this step is false.

What it reuses (nothing reinvented)
-----------------------------------
- Adapter: ``runtime.model_factory.build_adapter`` with the
  ``openai_compatible`` adapter (``adapters/openai_compatible_adapter.py``).
  It POSTs ``{model, messages, temperature 0.1}`` to the endpoint and reads
  the API key from the environment. This harness never reimplements it.
- Benchmark loading: ``runtime.task_loader.load_jsonl`` /
  ``load_benchmark_index`` — the same loader ``run_model_benchmarks.py`` and
  ``score_benchmark_outputs.py`` use.
- Scoring: ``scorers.rubric.score_record`` — the repo's scoring path. The
  per-benchmark means and the overall score are computed exactly the way
  ``score_benchmark_outputs.py`` computes them (overall = mean of the
  per-benchmark means).
- Record shape: identical to ``scripts/execution/run_model_benchmarks.py``
  (run_id, task_id, benchmark_name, capability, scoring, adapter,
  prompt_profile, model, ok, error, latency_ms, finish_reason, output_text,
  meta, backend_identity), plus ``prompt_tokens`` / ``completion_tokens``
  when the backend reports usage. The raw ``.jsonl`` can therefore be
  re-scored at any time with ``score_benchmark_outputs.py --input <file>``.

HARD RULE (Gary, 2026-11-07): no pollution of external datasets in the
actual training, EVER. This harness is EVALUATION, not training — that is the
correct side of the rule. It runs the repo's own benchmark (not an external
training dataset) and GSM8K / The Stack / any other external dataset never
enters a training path here, because no training path is built here.

Full evaluation path (Gary's design principle, 2026-11-07: testing is
offloaded into a continuous live running system):
  1. Benchmark baseline — THIS harness (stock 1B through the 168 tasks).
  2. Gate v2 on the fine-tune — same 168 tasks + the 10 protected floors
     (``configs/candidates/v2_class_policy.yaml``).
  3. Live continuous A/B in the running system — the fine-tune, once it
     exists, is served as an option on the ping server / in Lucid and
     A/B-tested against the stock 1B on the same prompts, in real use.
     A static benchmark alone never promotes a model.

How to run
----------
Live ping server (default — needs the ping key, see "What blocks it")::

    export OPENAI_COMPATIBLE_API_KEY='<key from the Secure Vault flow>'
    python3 scripts/execution/run_stock_1b_baseline.py
    python3 scripts/execution/run_stock_1b_baseline.py --limit 5   # cheap smoke test (5 SP)

Local backend (llama.cpp server / llamafile serving a local 1B GGUF —
same OpenAI-compatible adapter, no key needed on loopback)::

    python3 scripts/execution/run_stock_1b_baseline.py \\
        --endpoint http://127.0.0.1:8080/v1/chat/completions \\
        --model local-llama-3.2-1b

Dry run (spends NOTHING — validates the benchmark loads and the endpoint
answers, without sending any chat completion)::

    python3 scripts/execution/run_stock_1b_baseline.py --dry-run

Cost of the full run (live ping server, 168 tasks)
-------------------------------------------------
168 chat completions = 168 SP + neurons (2,457 neurons / 1M input tokens,
18,252 / 1M output tokens — a few hundred neurons at benchmark prompt sizes).
Well within the 10,000/day neuron budget, but SP is Gary's account: run the
full baseline ONCE, not repeatedly. Use ``--limit N`` for smoke tests.

What blocks the full live run
-----------------------------
Two blockers (verified 2026-11-07):

1. The ping key (the 64-hex secret) lives in Cloudflare only. It is never
   in any file, log, chat, or memory, and this harness will never fetch it.
   Until Gary provides it (via the Secure Vault flow for the run), or runs
   the harness himself, or the local T4/llamafile route is used, the live
   baseline has NO number — and none is fabricated here. The harness fails
   cleanly without the key (exit 2, names OPENAI_COMPATIBLE_API_KEY).
2. Cloudflare blocks the repo adapter's requests from this VM. The
   ``openai_compatible`` adapter uses Python urllib with its default
   ``Python-urllib/x.y`` User-Agent, and Cloudflare answers HTTP 403 /
   error code 1010 to it — for GET /health AND for POST
   /v1/chat/completions (verified with a dummy key: generate() fails with
   "HTTP 403: error code: 1010", 0 SP spent). A browser User-Agent gets
   through (curl GET / -> HTTP 200; curl POST without a key -> HTTP 401
   "missing or wrong x-lucid-ping-key"). So even WITH the key, a live run
   from this VM would fail at the Cloudflare layer until the adapter sends
   a browser User-Agent (one-line change in
   ``adapters/openai_compatible_adapter.py`` — not made here, it is shared
   repo code) or the run happens from an unblocked host (e.g. the Mac).
   This harness detects the 1010 and aborts (exit 3) before any task runs,
   unless ``--force`` is given.

Live-server quirks the harness already handles: the ping server has NO
``/health`` route (routes are GET /, POST /ping, POST /v1/chat/completions),
so a 404 from the adapter healthcheck is treated as "no such route" (warn
and continue), not a failure. ``GET /`` is the health signal there, and
this harness's own probes send a browser User-Agent so they are not
Cloudflare-blocked.

API key handling
----------------
The key is read ONLY from the ``OPENAI_COMPATIBLE_API_KEY`` environment
variable. It is never hardcoded, never written to a file, and never logged
(including in the receipt, the scored output, or error messages). If the
variable is absent and the endpoint is not local (loopback), the harness
exits with an error naming the variable. Local loopback endpoints
(127.0.0.1 / localhost / ::1) do not need a key — llama.cpp / llamafile
do not authenticate — so they are exempt; use ``--allow-no-key`` to exempt
any other endpoint explicitly.

Outputs (all under ``results/`` by default)
-------------------------------------------
- ``baseline_stock_1b.jsonl`` — raw per-task records (run_model_benchmarks shape).
- ``baseline_stock_1b_scored.json`` — scored payload (same shape as
  ``score_benchmark_outputs.py`` writes) + per-benchmark summary.
- ``baseline_stock_1b_receipt.json`` — run receipt: model, endpoint, run id,
  date, task count, failures, overall score, token usage, SP/neuron cost
  note, and the blocker status when the run could not proceed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.model_factory import build_adapter
from runtime.task_loader import load_benchmark_index, load_jsonl
from scorers.rubric import score_record

DEFAULT_ENDPOINT = "https://lucid-ping-server.admension.workers.dev/v1/chat/completions"
DEFAULT_MODEL = "@cf/meta/llama-3.2-1b-instruct"
DEFAULT_OUTPUT = "results/baseline_stock_1b.jsonl"
KEY_ENV_VAR = "OPENAI_COMPATIBLE_API_KEY"

# Live ping-server pricing (per the live-model dissection): 1 SP per chat
# completion, plus neurons per token. Kept here only for the receipt's cost
# note — the harness never charges anything itself.
SP_PER_COMPLETION = 1
NEURONS_PER_M_INPUT = 2_457
NEURONS_PER_M_OUTPUT = 18_252

SYSTEM_PROMPTS = {
    "full_doctrine": "Think in plans, critique weak points, repair conservatively, calibrate uncertainty.",
    "minimal_doctrine": "Plan, critique, repair, calibrate.",
    "bare_prompt": "",
}


def _is_local_endpoint(endpoint: str) -> bool:
    lowered = endpoint.lower()
    return any(
        host in lowered
        for host in ("127.0.0.1", "localhost", "[::1]", "0.0.0.0")
    )


def _http_get_json(url: str, timeout: float = 15.0) -> dict:
    """GET a URL, return a small report. No auth header is ever sent here.

    Sends a browser User-Agent: the live ping server sits behind Cloudflare,
    which answers HTTP 403 / error code 1010 ("bad browser") to Python
    urllib's default ``Python-urllib/x.y`` User-Agent, while a browser UA
    gets HTTP 200. (Verified 2026-11-07: urllib GET / -> 403/1010, curl
    GET / -> 200 with the full server state.)
    """
    started = time.perf_counter()
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) "
                               "Chrome/126.0 Safari/537.36"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status = getattr(resp, "status", 200)
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return {
            "ok": False,
            "url": url,
            "status": exc.code,
            "error": f"HTTP {exc.code}: {body[:200] or exc.reason}",
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "body_preview": body[:500],
        }
    except Exception as exc:  # URLError, timeout, ...
        return {
            "ok": False,
            "url": url,
            "status": None,
            "error": str(exc),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "body_preview": "",
        }
    return {
        "ok": True,
        "url": url,
        "status": status,
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "body_preview": body[:500],
    }


def _base_url(endpoint: str) -> str:
    """Strip the /v1/chat/completions suffix to get the server root."""
    if endpoint.endswith("/v1/chat/completions"):
        return endpoint[: -len("/v1/chat/completions")]
    return endpoint.rstrip("/")


def _load_tasks(limit: int | None) -> list[dict]:
    """Load the benchmark in run_model_benchmarks.py traversal order."""
    tasks: list[dict] = []
    for bench_file in sorted((ROOT / "benchmarks").rglob("*.jsonl")):
        for task in load_jsonl(bench_file):
            task = dict(task)
            task["_benchmark_name"] = bench_file.parent.name
            task["_source_file"] = str(bench_file)
            tasks.append(task)
            if limit is not None and len(tasks) >= limit:
                return tasks
    return tasks


def _dry_run(endpoint: str, model: str, limit: int | None) -> int:
    """Validate benchmark + endpoint WITHOUT spending SP.

    Sends no chat completion and no authenticated request: only GETs the
    server root (``GET /``) and the adapter healthcheck (``GET /health``),
    both of which cost 0 SP. Exits 0 when the benchmark loads and the
    endpoint answers.
    """
    tasks = _load_tasks(limit)
    index = load_benchmark_index(ROOT / "benchmarks")
    base = _base_url(endpoint)
    root_probe = _http_get_json(base + "/")
    adapter = build_adapter("openai_compatible", endpoint=endpoint, model=model)
    health = adapter.healthcheck()
    # The live ping server has NO /health route (its routes are GET /,
    # POST /ping, POST /v1/chat/completions), so the adapter healthcheck is
    # informational only here — a 404 means "no such route", and a 403/1010
    # means Cloudflare blocked urllib's User-Agent (see _http_get_json).
    # Neither is a dry-run failure: the dry-run gates on the benchmark
    # loading and on GET / answering.
    if not health.get("ok"):
        health["note"] = (
            "Live ping server has no /health route; healthcheck is "
            "informational only in dry-run (see GET / result above)."
        )
    report = {
        "dry_run": True,
        "benchmark_tasks_loaded": len(tasks),
        "benchmark_tasks_total": len(index),
        "benchmark_files": len(list((ROOT / "benchmarks").rglob("*.jsonl"))),
        "endpoint": endpoint,
        "model": model,
        "server_root_get": root_probe,
        "adapter_healthcheck": health,
        "chat_completion_sent": False,
        "sp_spent": 0,
        "ok": len(tasks) > 0 and len(index) == 168 and root_probe["ok"],
    }
    print(json.dumps(report, indent=2))
    if not report["ok"]:
        if len(index) != 168:
            print(
                f"ERROR: expected 168 benchmark tasks, found {len(index)}.",
                file=sys.stderr,
            )
        if not root_probe["ok"]:
            print(
                f"ERROR: GET {base}/ failed: {root_probe.get('error')}",
                file=sys.stderr,
            )
        return 1
    return 0


def _score_records(records: list[dict]) -> dict:
    """Score with the repo's scoring path (same math as score_benchmark_outputs.py)."""
    task_index = load_benchmark_index(ROOT / "benchmarks")
    results: list[dict] = []
    aggregates: dict[str, list[float]] = {}
    failures = 0
    for rec in records:
        task = task_index.get(rec["task_id"])
        score = score_record(rec.get("output_text", ""), task=task)
        scored = dict(rec)
        scored.update(score)
        scored["task_reference"] = task.get("reference") if task else None
        results.append(scored)
        aggregates.setdefault(rec["benchmark_name"], []).append(
            score["normalized_score"]
        )
        if not rec.get("ok"):
            failures += 1
    summary = {k: round(sum(v) / len(v), 4) for k, v in aggregates.items()}
    return {
        "results": results,
        "summary": summary,
        "failure_count": failures,
        "overall_weighted_score": round(
            sum(summary.values()) / max(1, len(summary)), 4
        ),
        "scorer_version": "v2-task-aware",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Baseline the stock Llama 3.2 1B on the repo's 168-task benchmark."
    )
    parser.add_argument(
        "--endpoint", default=DEFAULT_ENDPOINT,
        help="Chat-completions endpoint (default: live ping server). "
        "Point at a local llama.cpp / llamafile server for the local route.",
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL,
        help="Model id to send (default: @cf/meta/llama-3.2-1b-instruct).",
    )
    parser.add_argument(
        "--adapter", default="openai_compatible",
        help="Adapter from runtime/model_factory.py (default: openai_compatible).",
    )
    parser.add_argument(
        "--prompt-profile", default="minimal_doctrine",
        choices=list(SYSTEM_PROMPTS),
        help="System-prompt profile, same as run_model_benchmarks.py.",
    )
    parser.add_argument(
        "--output", default=DEFAULT_OUTPUT,
        help="Raw per-task records (.jsonl).",
    )
    parser.add_argument(
        "--scored-output", default=None,
        help="Scored payload (.json). Default: <output stem>_scored.json.",
    )
    parser.add_argument(
        "--receipt", default=None,
        help="Run receipt (.json). Default: <output stem>_receipt.json.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Run only the first N tasks (cheap smoke test).",
    )
    parser.add_argument(
        "--timeout-seconds", type=float, default=None,
        help="Per-request timeout passed to the adapter.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Validate the benchmark loads + the endpoint answers GET / "
        "without sending any chat completion (0 SP). Never needs the key.",
    )
    parser.add_argument(
        "--allow-no-key", action="store_true",
        help="Allow a run with no API key (only for keyless local endpoints).",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Proceed even if the adapter healthcheck is Cloudflare-blocked "
        "(1010). Without it, a blocked healthcheck aborts before any task.",
    )
    args = parser.parse_args()

    if args.dry_run:
        return _dry_run(args.endpoint, args.model, args.limit)

    # --- API key: env only, never hardcoded, never logged. ---
    api_key = os.environ.get(KEY_ENV_VAR)
    key_required = not (_is_local_endpoint(args.endpoint) or args.allow_no_key)
    if key_required and not api_key:
        print(
            f"ERROR: {KEY_ENV_VAR} is not set in the environment.\n"
            f"The stock-1B baseline against the live ping server needs the ping key.\n"
            f"Set it before running:\n"
            f"  export {KEY_ENV_VAR}='<key>'\n"
            f"Get the key from Gary via the Secure Vault flow (the 64-hex secret lives\n"
            f"in Cloudflare only — it is never in any file, log, chat, or memory).\n"
            f"Or use --dry-run (0 SP, no key needed) to validate the setup, or point\n"
            f"--endpoint at a local llama.cpp / llamafile server (no key needed).",
            file=sys.stderr,
        )
        return 2

    tasks = _load_tasks(args.limit)
    print(f"Loaded {len(tasks)} benchmark task(s) "
          f"({'full 168-task suite' if args.limit is None else f'limit={args.limit}'})")
    if not tasks:
        print("ERROR: no benchmark tasks loaded.", file=sys.stderr)
        return 1

    build_kwargs: dict = {"endpoint": args.endpoint, "model": args.model}
    if args.timeout_seconds is not None:
        build_kwargs["timeout_seconds"] = args.timeout_seconds
    adapter = build_adapter(args.adapter, **build_kwargs)
    health = adapter.healthcheck()
    print(f"Adapter healthcheck: {json.dumps(health)}")
    if not health.get("ok"):
        # Two distinct causes, two different responses:
        # - 404: the endpoint has no /health route (true of the live ping
        #   server — its routes are GET /, POST /ping, POST
        #   /v1/chat/completions). Harmless: warn and continue.
        # - Anything else (403 / error code 1010, connection reset, ...):
        #   probe GET / with a browser User-Agent. If the server answers
        #   there, the server is up but the ADAPTER's requests are being
        #   blocked — Cloudflare rejects urllib's default User-Agent
        #   (verified 2026-11-07: 403/1010, and intermittently a bare
        #   connection reset, on both /health and POST /v1/chat/completions,
        #   while a browser UA gets HTTP 200 / 401). The adapter's POSTs
        #   would hit the same block, so every task would fail — abort
        #   unless --force.
        err = str(health.get("error", ""))
        if "404" in err:
            print(
                "WARNING: endpoint has no /health route "
                "(expected on the live ping server); continuing — "
                "GET / is the health signal there.",
                file=sys.stderr,
            )
        else:
            root_probe = _http_get_json(_base_url(args.endpoint) + "/")
            if root_probe["ok"]:
                print(
                    "ERROR: adapter healthcheck failed but the server answers "
                    f"GET / ({root_probe['status']}) — the adapter's requests "
                    "are being blocked, not the server being down.\n"
                    f"Healthcheck error: {err or health}\n"
                    "Known cause on the live ping server: Cloudflare rejects "
                    "the repo adapter's Python-urllib default User-Agent "
                    "(HTTP 403, error code 1010, or a bare connection reset) "
                    "on /health AND on POST /v1/chat/completions. Until the "
                    "adapter sends a browser User-Agent (one-line change in "
                    "adapters/openai_compatible_adapter.py — shared repo code, "
                    "not changed here) or the run happens from an unblocked "
                    "host (e.g. the Mac), no baseline can be produced from "
                    "this machine.\n"
                    "Use --force to proceed anyway (every task will fail).",
                    file=sys.stderr,
                )
                if not args.force:
                    return 3
            else:
                print(
                    "ERROR: adapter healthcheck failed and GET / also fails — "
                    "endpoint appears down. Not sending chat completions.",
                    file=sys.stderr,
                )
                return 1

    run_id = f"baseline_stock_1b_{uuid4().hex[:12]}"
    system_prompt = SYSTEM_PROMPTS[args.prompt_profile]
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    scored_path = Path(args.scored_output) if args.scored_output else out.with_name(
        out.stem + "_scored.json"
    )
    receipt_path = Path(args.receipt) if args.receipt else out.with_name(
        out.stem + "_receipt.json"
    )

    records: list[dict] = []
    failures = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    usage_reported = False
    with out.open("w", encoding="utf-8") as f:
        for i, task in enumerate(tasks, start=1):
            started = time.perf_counter()
            try:
                response = adapter.generate(
                    task["prompt"], system_prompt=system_prompt, context=task
                )
            except Exception as exc:
                response = None
                error = str(exc)
            else:
                error = response.error
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            record = {
                "run_id": run_id,
                "task_id": task["id"],
                "benchmark_name": task["_benchmark_name"],
                "capability": task.get("capability"),
                "scoring": task.get("scoring"),
                "adapter": args.adapter,
                "prompt_profile": args.prompt_profile,
                "model": args.model,
                "ok": bool(response.ok) if response is not None else False,
                "error": error,
                "latency_ms": response.latency_ms
                if response and response.latency_ms is not None
                else latency_ms,
                "finish_reason": response.finish_reason
                if response is not None
                else "failed",
                "output_text": response.text if response is not None else "",
                "meta": response.meta
                if response is not None
                else {"adapter": args.adapter},
                "backend_identity": response.backend_identity
                if response is not None
                else None,
                "prompt_tokens": response.prompt_tokens
                if response is not None
                else None,
                "completion_tokens": response.completion_tokens
                if response is not None
                else None,
            }
            if response is not None and response.prompt_tokens is not None:
                total_prompt_tokens += response.prompt_tokens
                usage_reported = True
            if response is not None and response.completion_tokens is not None:
                total_completion_tokens += response.completion_tokens
                usage_reported = True
            if not record["ok"]:
                failures += 1
            records.append(record)
            f.write(json.dumps(record) + "\n")
            if i % 25 == 0 or i == len(tasks):
                print(f"  {i}/{len(tasks)} tasks, {failures} failure(s) so far")

    scored = _score_records(records)
    scored_path.parent.mkdir(parents=True, exist_ok=True)
    scored_path.write_text(json.dumps(scored, indent=2), encoding="utf-8")

    ok_count = len(records) - failures
    if usage_reported:
        est_neurons = round(
            total_prompt_tokens * NEURONS_PER_M_INPUT / 1_000_000
            + total_completion_tokens * NEURONS_PER_M_OUTPUT / 1_000_000,
            1,
        )
        neuron_note = (
            f"~{est_neurons} neurons "
            f"({total_prompt_tokens} prompt tokens, "
            f"{total_completion_tokens} completion tokens)"
        )
    else:
        neuron_note = "unknown — backend did not report token usage"
    receipt = {
        "run_id": run_id,
        "date_utc": datetime.now(timezone.utc).isoformat(),
        "kind": "stock_llama_3.2_1b_baseline",
        "model": args.model,
        "endpoint": args.endpoint,
        "adapter": args.adapter,
        "prompt_profile": args.prompt_profile,
        "task_count": len(records),
        "tasks_requested": 168 if args.limit is None else args.limit,
        "full_suite": args.limit is None,
        "failures": failures,
        "ok_count": ok_count,
        "overall_weighted_score": scored["overall_weighted_score"],
        "per_benchmark_summary": scored["summary"],
        "scorer_version": scored["scorer_version"],
        "output": str(out),
        "scored_output": str(scored_path),
        "total_prompt_tokens": total_prompt_tokens if usage_reported else None,
        "total_completion_tokens": total_completion_tokens
        if usage_reported
        else None,
        "cost_note": (
            f"{ok_count} successful chat completion(s) x {SP_PER_COMPLETION} SP = "
            f"{ok_count} SP; neurons: {neuron_note}. "
            f"Full 168-task run = 168 SP + a few hundred neurons "
            f"(well within the 10,000/day neuron budget). Run once, not repeatedly."
        ),
        "baseline_context": (
            "v10's 0.9237 is exemplar retrieval (TF-IDF over 669 Q&A records), "
            "NOT a neural score. This run is the true neural baseline the "
            "fine-tune must be judged against (plan §1)."
        ),
        "evaluation_path": [
            "1. Benchmark baseline (this harness)",
            "2. Gate v2 on the fine-tune (same 168 tasks + 10 protected floors)",
            "3. Live continuous A/B in the running system (fine-tune served as "
            "an option on the ping server / in Lucid, same prompts as stock 1B)",
        ],
        "training_rule": (
            "No external dataset (GSM8K, The Stack, any other) is ever in the "
            "actual training data. This harness is evaluation only; it runs the "
            "repo's own benchmark and builds no training path."
        ),
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    print(json.dumps({
        "ok": failures == 0,
        "run_id": run_id,
        "records": len(records),
        "failures": failures,
        "overall_weighted_score": scored["overall_weighted_score"],
        "output": str(out),
        "scored_output": str(scored_path),
        "receipt": str(receipt_path),
    }, indent=2))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
