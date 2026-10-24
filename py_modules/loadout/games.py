"""Bundled per-game data (data/games/<appid>.json)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .validate import ValidationError, validate_game_doc

DATA_DIR = Path(__file__).parent / "data" / "games"


def load_games(directory: Path = DATA_DIR) -> dict[int, dict[str, Any]]:
    out = {}
    for f in sorted(directory.glob("*.json")):
        doc = validate_game_doc(json.loads(f.read_text(encoding="utf-8")))
        if f.stem != str(doc["appid"]):
            raise ValidationError(f"{f.name}: file name must be <appid>.json")
        out[doc["appid"]] = doc
    return out


def annotate(installed: list[dict[str, Any]], supported: set[int], active: set[str]) -> list[dict[str, Any]]:
    """Mark which installed games have Loadout data and which have a profile applied right now
    (those must stay visible, or Default couldn't be restored from the UI)."""
    return [{**g, "supported": g["appid"] in supported, "active": str(g["appid"]) in active} for g in installed]
