"""Load BeGhost defaults from be_ghost.toml.

Search order:
  1. ./be_ghost.toml
  2. ~/.be_ghost.toml
  3. $BE_GHOST_CONFIG (env var, full path)

Example file:
    [defaults]
    profile = "win11_chrome"
    lite = true
    headless = true
    timeout_ms = 30000
    proxy = "http://user:pass@host:8080"

    [storage]
    state = "state.json"
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib  # type: ignore[import-not-found]
else:
    try:
        import tomli as tomllib  # type: ignore[import-not-found]
    except ImportError:
        tomllib = None  # type: ignore[assignment]


_KEYS = {
    "stealth", "lite", "headless", "profile", "proxy", "timeout_ms",
    "storage_state", "auto_save_storage", "trace", "har_record", "har_replay",
    "max_bytes", "max_seconds",
}


def _candidates() -> list[Path]:
    out: list[Path] = []
    env = os.environ.get("BE_GHOST_CONFIG")
    if env:
        out.append(Path(env))
    out.append(Path.cwd() / "be_ghost.toml")
    out.append(Path.home() / ".be_ghost.toml")
    return out


def load() -> dict:
    """Return a kwargs dict ready to pass to BeGhost(**load())."""
    if tomllib is None:
        return {}
    for path in _candidates():
        if path.exists():
            try:
                with open(path, "rb") as f:
                    data = tomllib.load(f)
            except Exception:
                continue
            defaults = data.get("defaults", {}) if isinstance(data, dict) else {}
            storage = data.get("storage", {}) if isinstance(data, dict) else {}
            out = {k: v for k, v in defaults.items() if k in _KEYS}
            if "state" in storage:
                out["storage_state"] = storage["state"]
            return out
    return {}
