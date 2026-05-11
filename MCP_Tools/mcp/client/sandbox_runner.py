"""Sandbox command runner scaffold."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Sequence


ALLOWED_COMMANDS = {"pytest", "python", "python3"}


def run_allowed(command: Sequence[str], cwd: str | Path = ".", timeout_seconds: int = 120) -> dict:
    if not command:
        raise ValueError("Empty command")
    executable = Path(command[0]).name
    if executable not in ALLOWED_COMMANDS:
        raise PermissionError(f"Command not allowed: {executable}")
    proc = subprocess.run(command, cwd=str(cwd), timeout=timeout_seconds, text=True, capture_output=True)
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
        "passed": proc.returncode == 0,
    }
