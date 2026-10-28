"""Bundled per-game data (data/games/<appid>.json)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .validate import DEVICE_ID, ValidationError, validate_game_doc

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
    """Per installed game: has a Loadout entry (`supported`), the entry has profiles for this
    device (`verified`), the devices it has profiles for (`devices`, to borrow from), and which
    profile is applied right now (`profile`, None if none)."""
    out = []
    for g in installed:
        doc = docs.get(g["appid"])
        devs = sorted(doc["devices"]) if doc else []
        entry = applied.get(str(g["appid"]))
        out.append({**g, "supported": doc is not None, "verified": device in devs, "devices": devs,
                    "profile": entry.get("profile") if entry else None})
    return out


def profiles_for(doc: Optional[dict[str, Any]], device: Optional[str],
                 profile_device: Optional[str]) -> dict[str, Any]:
    """This device's profiles, else those of the device the user picked to borrow from, else none
    (the FPS cap only). A picked device the entry no longer has also means none."""
    if profile_device is not None and (type(profile_device) is not str or not DEVICE_ID.match(profile_device)):
        raise ValueError("invalid profile device")
    devs = doc["devices"] if doc else {}
    entry = devs.get(device or "") or devs.get(profile_device or "")
    return entry["profiles"] if entry else {}
