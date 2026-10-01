"""Synthetic stub (synthetic sample): minimal .env loader.

The original project shares a loader of this name; this stub only supports
KEY=VALUE lines and never overrides variables that are already set.
"""
from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: str | os.PathLike | None = None) -> None:
    env = Path(path) if path else Path.cwd() / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
