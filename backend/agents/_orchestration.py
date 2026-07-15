"""Shared, side-effect-free helpers for LedgerGuard Layer 2 agents."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def read_directive(filename: str) -> str:
    """Read a directive at runtime so orchestration follows the current SOP."""
    return (PROJECT_ROOT / "directives" / filename).read_text(encoding="utf-8")


def call_execution(script_name: str, arguments: Sequence[str]) -> dict[str, Any]:
    """Invoke a deterministic execution script without a shell and parse its JSON output."""
    completed = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "execution" / script_name), *arguments],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Execution script failed: {script_name}")
    payload = json.loads(completed.stdout)
    if not isinstance(payload, Mapping):
        raise ValueError(f"Execution script returned a non-object payload: {script_name}")
    return dict(payload)


def short_evidence(items: object) -> list[dict[str, Any]]:
    """Keep citations structured and short; raw document text never becomes agent logic."""
    if not isinstance(items, list):
        return []
    return [dict(item) for item in items if isinstance(item, Mapping)]
