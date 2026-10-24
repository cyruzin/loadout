"""Atomic file writes and the JSON settings/state files built on them."""
from __future__ import annotations

import copy
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any


def atomic_write(path: Path, data: bytes) -> None:
    """Temp file in the same folder + os.replace; keeps the existing file's permissions."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.chmod(tmp, stat.S_IMODE(os.stat(path).st_mode))
        except FileNotFoundError:
            pass
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


class JsonStore:
    def __init__(self, path: Path, default: dict[str, Any]):
        self.path = path
        self.default = default

    def load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return copy.deepcopy(self.default)
        except ValueError:
            # Keep the corrupt file for inspection instead of silently losing backups.
            os.replace(self.path, self.path.with_suffix(".corrupt.json"))
            return copy.deepcopy(self.default)
        if not isinstance(data, dict):
            return copy.deepcopy(self.default)
        return {**copy.deepcopy(self.default), **data}

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(self.path, json.dumps(data, indent=2, sort_keys=True).encode("utf-8"))
