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


GAME_FILTERS = ("verified", "loadout")  # cumulative: the second one shows more games


def annotate(installed: list[dict[str, Any]], docs: dict[int, dict[str, Any]],
             applied: dict[str, dict[str, Any]], device: Optional[str]) -> list[dict[str, Any]]:
    """Per installed game: has a Loadout entry (`supported`), the entry has profiles for this
    device (`verified`), the devices it has profiles for (`devices`, to borrow from), each
    device's profiles with their recommended resolution (`profiles`: {device: {profile: "WxH" or
    None}}; a profile a device doesn't have is hidden), and which profile is applied right now
    (`profile`, None if none)."""
    out = []
    for g in installed:
        doc = docs.get(g["appid"])
        devs = sorted(doc["devices"]) if doc else []
        entry = applied.get(str(g["appid"]))
        profiles = {d: {p: body["resolution"] for p, body in e["profiles"].items()}
                    for d, e in doc["devices"].items()} if doc else {}
        out.append({**g, "supported": doc is not None, "verified": device in devs, "devices": devs,
                    "profiles": profiles, "profile": entry.get("profile") if entry else None})
    return out


def profiles_for(doc: Optional[dict[str, Any]], device: Optional[str],
                 profile_device: Optional[str]) -> dict[str, Any]:
    """This device's profiles, else those of the device the user picked to borrow from, else none
    (nothing to set). A picked device the entry no longer has also means none."""
    if profile_device is not None and (type(profile_device) is not str or not DEVICE_ID.match(profile_device)):
        raise ValueError("invalid profile device")
    devs = doc["devices"] if doc else {}
    entry = devs.get(device or "") or devs.get(profile_device or "")
    return entry["profiles"] if entry else {}


def profile_spec(doc: Optional[dict[str, Any]], device: Optional[str], profile_device: Optional[str],
                 profile: str) -> dict[str, Any]:
    """What `profile` sets ({} for Default). A profile the device's (or borrowed) block leaves out,
    e.g. one it can't hold the target FPS with, is hidden in the panel and refused here."""
    profiles = profiles_for(doc, device, profile_device)
    if profile == "default":
        return {}
    if profile not in profiles:
        raise ValueError(f"no {profile} profile for this game on this device")
    return profiles[profile]
