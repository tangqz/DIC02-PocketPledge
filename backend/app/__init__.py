from __future__ import annotations

import os
from pathlib import Path


def _load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE pairs into os.environ without overriding existing values."""
    if not path.exists() or not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


BACKEND_ROOT = Path(__file__).resolve().parents[1]

_load_env_file(BACKEND_ROOT / ".env")
_load_env_file(BACKEND_ROOT.parent / ".env")
