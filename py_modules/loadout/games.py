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


def resolution_files(doc: Optional[dict[str, Any]], width: int, height: int) -> list[dict[str, Any]]:
    """File edits that set the game's resolution, in the same shape as a profile's `files`."""
    return [{"path": r["path"], "format": r["format"],
             "set": {**dict.fromkeys(r["width"], str(width)), **dict.fromkeys(r["height"], str(height))}}
            for r in (doc or {}).get("resolution", [])]


def resolution_keys(doc: Optional[dict[str, Any]]) -> set[str]:
    return {k for r in (doc or {}).get("resolution", []) for k in r["width"] + r["height"]}


def resolution_stale(written: dict[str, dict[str, dict[str, str]]], res_files: list[dict[str, Any]]) -> bool:
    """Loadout wrote a resolution for this game that differs from what it would write now (e.g.
    "Native" written while docked, now handheld). In-game changes don't count: only what Loadout
    itself wrote (`written`, the state's per-key {"old", "new"}) is compared."""
    ours = {k: v["new"] for keys in written.values() for k, v in keys.items()}
    return any(k in ours and ours[k] != value for f in res_files for k, value in f["set"].items())


GAME_FILTERS = ("verified", "loadout", "all")  # cumulative: each one shows more games


def annotate(installed: list[dict[str, Any]], docs: dict[int, dict[str, Any]],
             applied: dict[str, dict[str, Any]], device: Optional[str]) -> list[dict[str, Any]]:
    """Per installed game: has a Loadout entry (`supported`), that entry was verified on this
    device (`verified`), Loadout can set its resolution (`resolution`), and which profile is
    applied right now (`profile`, None if none)."""
    out = []
    for g in installed:
        doc = docs.get(g["appid"])
        verified = doc is not None and any(v["device"] == device for v in doc["verified"])
        entry = applied.get(str(g["appid"]))
        out.append({**g, "supported": doc is not None, "verified": verified,
                    "resolution": bool(doc and doc.get("resolution")),
                    "profile": entry.get("profile") if entry else None})
    return out
