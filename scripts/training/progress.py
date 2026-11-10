#!/usr/bin/env python3
"""Progress reporter for the LLMBuilder training chain.

A chain step (train, merge, gguf, gate, r2, manifest, client) reports
its progress to the ping server, where an admin (or Lucid, as a thin
client) pulls it on demand with GET /admin/progress.

Event-driven (Gary, 2026-11-10): an update is PUSHED only when an
event happens — a training step/milestone completes, a chain step
finishes, a status changes. There is NO polling loop here: nothing
checks on a timer. Callers report on their own events (the trainer
reports from its log callback; a shell step reports once when it
finishes). The admin pull is a single on-demand GET, not a poll.

The correct split (Gary, 2026-11-10 — correction): the GPU training
side is where the heavy work lives, and it is the queryable source
of truth for its own progress. This reporter (the GPU/training
side) COMPUTES the progress — percent, ETA, and the ASCII bar —
before it sends anything. The neuron side (ping server) only
stores and serves what was reported: a plain pass-through, never
computing progress, never training, never doing inference for
progress. Lucid is a thin client: one lightweight GET, the neuron
side passes the stored progress back.

Zero neurons, zero SP: the ping server's progress endpoints are plain
Durable Object reads/writes. They never call Workers AI, never go
through the chat-completions path, and never touch the SP bucket.
Reporting costs 0 SP and 0 neurons.

Fire-and-forget: reporting NEVER fails the caller. The POST has a
short timeout and every error (no key, no network, server error) is
swallowed — the training or chain step carries on. If no key is
configured, reporting is silently disabled (a no-op).

Configuration (in priority order):
  * CLI flags: --url, --key
  * Env vars: LUCID_PING_URL, LUCID_PING_KEY
  * Default URL: https://lucid-ping-server.admension.workers.dev
The key is the ping server shared secret (x-lucid-ping-key) — the
same key as /ping and /v1/chat/completions. It is never printed or
logged. In Colab, set LUCID_PING_KEY from a Colab secret (never
hardcode it in a cell).

Usage as a module (trainer + chain scripts):
    from progress import ProgressReporter
    reporter = ProgressReporter.from_env(run_id="lora-1b-20261110")
    reporter.report(stage="train", step=42, total=152, loss=1.23,
                    eta_seconds=540, message="Training step 42/152")
    reporter.report(stage="train", status="completed", step=152,
                    total=152, message="Training complete")

Usage as a CLI (shell / Colab cells, for merge/gguf/gate steps):
    python scripts/training/progress.py --stage merge --step 1 --total 3 \\
        --status completed --message "Adapter merged"
    python scripts/training/progress.py --stage gguf --step 0 --total 1 \\
        --message "GGUF convert started"

Stdlib only (urllib) — no new dependency.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_PING_URL = "https://lucid-ping-server.admension.workers.dev"
PROGRESS_PATH = "/admin/progress"

# A progress POST must never stall the caller: 2 seconds is enough
# for an edge round-trip, and a slow server is not worth waiting for.
POST_TIMEOUT_SECONDS = 2.0

# ASCII progress bar width (characters). The bar is computed here,
# on the training side, and sent with the report — the neuron side
# stores and serves it verbatim, it never renders it.
BAR_WIDTH = 20


def compute_percent(step: int | None, total: int | None,
                    explicit: float | None = None) -> float | None:
    """Percent complete, computed on the training side.

    Derived from step/total when a total is known; an explicit
    percent is only used when there is no total. Clamped to
    [0, 100], rounded to one decimal. None when there is no basis
    for a percentage.
    """
    if total is not None and total > 0 and step is not None:
        return round(min(100.0, max(0.0, (step / total) * 100.0)), 1)
    if explicit is not None:
        try:
            return round(min(100.0, max(0.0, float(explicit))), 1)
        except (TypeError, ValueError):
            return None
    return None


def render_bar(percent: float | None) -> str:
    """Render an ASCII progress bar from a percent, e.g.
    [██████████░░░░░░░░░░] 50.0%. Computed on the training side.
    '' when percent is None (no percentage to show).
    """
    if percent is None:
        return ""
    p = min(100.0, max(0.0, float(percent)))
    filled = round((p / 100.0) * BAR_WIDTH)
    return f"[{'█' * filled}{'░' * (BAR_WIDTH - filled)}] {p:.1f}%"


class ProgressReporter:
    """Fire-and-forget progress POSTs to the ping server.

    Construct with a base URL and the shared secret (key). If the key
    is missing/empty, the reporter is disabled and every report() is
    a silent no-op — the caller never has to check. report() never
    raises: any transport or server error is swallowed.
    """

    def __init__(self, url: str | None = None, key: str | None = None,
                 run_id: str | None = None):
        self.url = (url or os.environ.get("LUCID_PING_URL") or DEFAULT_PING_URL).rstrip("/")
        self.key = key if key is not None else os.environ.get("LUCID_PING_KEY", "")
        self.key = (self.key or "").strip()
        self.run_id = (run_id or "").strip() or None
        self.enabled = bool(self.key)

    @classmethod
    def from_env(cls, run_id: str | None = None) -> "ProgressReporter":
        return cls(run_id=run_id)

    def report(self, stage: str, status: str = "running",
               step: int | None = None, total: int | None = None,
               loss: float | None = None, eta_seconds: float | None = None,
               run_id: str | None = None, message: str | None = None,
               percent: float | None = None) -> bool:
        """POST one progress event. Returns True if the server stored it.

        The percent and the ASCII bar are COMPUTED HERE, on the
        training side, and sent with the report — the neuron side
        stores and serves them verbatim and never computes progress.
        A completed status forces 100% here (not on the server).
        Never raises. Returns False when disabled, unreachable, or the
        server rejects the update — the caller carries on regardless.
        """
        if not self.enabled:
            return False
        computed_percent = compute_percent(step, total, percent)
        if status == "completed":
            computed_percent = 100.0
        payload: dict = {
            "stage": stage,
            "status": status,
            "percent": computed_percent,
            "bar": render_bar(computed_percent),
        }
        if step is not None:
            payload["step"] = step
        if total is not None:
            payload["total"] = total
        if loss is not None:
            payload["loss"] = loss
        if eta_seconds is not None:
            payload["eta_seconds"] = eta_seconds
        payload["run_id"] = run_id or self.run_id
        if message:
            payload["message"] = message
        try:
            req = urllib.request.Request(
                self.url + PROGRESS_PATH,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "content-type": "application/json",
                    "x-lucid-ping-key": self.key,
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=POST_TIMEOUT_SECONDS) as res:
                body = json.loads(res.read().decode("utf-8"))
                return bool(res.status == 200 and body.get("ok"))
        except Exception:
            # Fire-and-forget: a failed report must never fail the caller.
            return False


def report_progress(stage: str, status: str = "running",
                    step: int | None = None, total: int | None = None,
                    loss: float | None = None, eta_seconds: float | None = None,
                    run_id: str | None = None, message: str | None = None,
                    percent: float | None = None,
                    url: str | None = None, key: str | None = None) -> bool:
    """One-shot convenience wrapper: build a reporter and post once."""
    return ProgressReporter(url=url, key=key, run_id=run_id).report(
        stage=stage, status=status, step=step, total=total,
        loss=loss, eta_seconds=eta_seconds, run_id=run_id, message=message,
        percent=percent,
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Report one chain-progress event to the ping server "
                    "(POST /admin/progress). Fire-and-forget: exit 0 even "
                    "when reporting is disabled or the server is unreachable.",
        epilog="Auth: --key or LUCID_PING_KEY (the ping shared secret). "
               "URL: --url or LUCID_PING_URL (default: the live worker). "
               "The key is never printed.",
    )
    p.add_argument("--url", default=None,
                   help="Ping server base URL (default: env LUCID_PING_URL or "
                        "the live worker).")
    p.add_argument("--key", default=None,
                   help="Ping shared secret (default: env LUCID_PING_KEY).")
    p.add_argument("--stage", required=True,
                   help="Chain stage: train, merge, gguf, gate, r2, manifest, client.")
    p.add_argument("--status", default="running",
                   choices=["running", "completed", "failed", "idle"],
                   help="Status (default: running).")
    p.add_argument("--step", type=int, default=None, help="Current step (e.g. 42).")
    p.add_argument("--total", type=int, default=None, help="Total steps (e.g. 152).")
    p.add_argument("--percent", type=float, default=None,
                   help="Explicit percent (only used when --total is not given; "
                        "otherwise percent is computed from step/total).")
    p.add_argument("--loss", type=float, default=None, help="Current loss, if any.")
    p.add_argument("--eta-seconds", type=float, default=None,
                   help="Estimated seconds remaining, if known.")
    p.add_argument("--run-id", default=None, help="Run id, e.g. lora-1b-20261110.")
    p.add_argument("--message", default=None, help="Short human message.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ok = report_progress(
        stage=args.stage, status=args.status, step=args.step, total=args.total,
        loss=args.loss, eta_seconds=args.eta_seconds, run_id=args.run_id,
        message=args.message, percent=args.percent, url=args.url, key=args.key,
    )
    # Exit 0 either way: reporting is best-effort and must never fail
    # the chain step that called it. Print a one-line outcome for the
    # caller's log (without the key).
    print(json.dumps({
        "ok": ok,
        "stage": args.stage,
        "status": args.status,
        "step": args.step,
        "total": args.total,
        "reported": ok,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
