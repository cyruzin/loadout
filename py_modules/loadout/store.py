"""JSON files written atomically (temp file in the same folder + os.replace)."""
from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path
from typing import Any


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
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=f".{self.path.name}.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            os.unlink(tmp)
            raise
