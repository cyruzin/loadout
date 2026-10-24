"""Bundled per-game data (data/games/<appid>.json)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

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


GAME_FILTERS = ("verified", "loadout", "all")  # cumulative: each one shows more games


def annotate(installed: list[dict[str, Any]], docs: dict[int, dict[str, Any]],
             applied: dict[str, dict[str, Any]], device: Optional[str]) -> list[dict[str, Any]]:
    """Per installed game: has a Loadout entry (`supported`), that entry was verified on this
    device (`verified`), and which profile is applied right now (`profile`, None if none)."""
    out = []
    for g in installed:
        doc = docs.get(g["appid"])
        verified = doc is not None and any(v["device"] == device for v in doc["verified"])
        entry = applied.get(str(g["appid"]))
        out.append({**g, "supported": doc is not None, "verified": verified,
                    "profile": entry.get("profile") if entry else None})
    return out
