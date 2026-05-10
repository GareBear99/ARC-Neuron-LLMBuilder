#!/usr/bin/env python3
"""Run ARC-Neuron production-candidate verification in deterministic stages.

The repository's default pytest invocation can be noisy in some plugin-heavy
runners, so this script executes the same suite by test module and records the
exact stage that fails or times out. It does not promote a model or mutate the
scoreboard.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "production_audit" / "production_verify_latest.json"
TEST_MODULES = [
    "tests/test_arc_core_fixes.py",
    "tests/test_artifact_and_ingestion.py",
    "tests/test_audit_remediation.py",
    "tests/test_doctor_and_prompt_files.py",
    "tests/test_execution_flow.py",
    "tests/test_functioning_model.py",
    "tests/test_no_server_command_adapter.py",
    "tests/test_omnibinary_pipeline_promotion.py",
    "tests/test_phase2_phase4.py",
    "tests/test_runtime_receipts.py",
    "tests/test_smoke.py",
    "tests/test_user_flow_scripts.py",
]


def run_stage(name: str, cmd: list[str], timeout: int = 120) -> dict:
    print(f"[arc-verify] {name}: {' '.join(cmd)}", flush=True)
    proc = subprocess.Popen(
        cmd,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        # Kill the whole process group so a timed-out pytest/training helper
        # cannot keep running after public verification reports the failure.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
            proc.kill()
        stdout, stderr = proc.communicate()
        print(f"[arc-verify] TIMEOUT: {name} after {timeout}s", file=sys.stderr, flush=True)
        return {
            "name": name,
            "ok": False,
            "timeout_seconds": timeout,
            "stdout_tail": (stdout or "")[-2000:],
            "stderr_tail": (stderr or "")[-2000:],
        }

    ok = proc.returncode == 0
    if stdout:
        print(stdout, end="" if stdout.endswith("\n") else "\n")
    if stderr:
        print(stderr, file=sys.stderr, end="" if stderr.endswith("\n") else "\n")
    return {
        "name": name,
        "ok": ok,
        "returncode": proc.returncode,
        "stdout_tail": (stdout or "")[-2000:],
        "stderr_tail": (stderr or "")[-2000:],
    }


def main() -> int:
    stages = []
    compile_targets = [
        "adapters",
        "arc_core",
        "arc_neuron_small",
        "arc_neuron_tokenizer",
        "arc_tiny",
        "runtime",
        "scripts",
        "scorers",
        "tests",
        "cognition_lab.py",
        "rubric.py",
    ]
    # Compile the source/test surface instead of the entire checkout. Full-tree
    # compile can be noisy or slow when generated bundles, caches, embedded
    # ecosystem snapshots, or release artifacts are present. This public verify
    # target intentionally validates the source that reviewers are expected to
    # run.
    stages.append(run_stage("compile", [sys.executable, "-m", "compileall", "-q", *compile_targets], 180))
    stages.append(run_stage("validator", [sys.executable, "scripts/validate_repo.py"], 180))
    for module in TEST_MODULES:
        stages.append(run_stage(f"pytest:{module}", [sys.executable, "-m", "pytest", module, "-q"], 180))
    ok = all(stage["ok"] for stage in stages)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ok": ok,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "tests_expected": 136,
        "benchmark_tasks_expected": 168,
        "stages": stages,
    }
    REPORT.write_text(json.dumps(payload, indent=2))
    print(json.dumps({"ok": ok, "report": str(REPORT.relative_to(ROOT))}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
