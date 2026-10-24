"""Structural + semantic validation of data documents (devices/*.json, games/*.json).

Stdlib only on purpose: no compiled deps to bundle. The same module is meant
to run in the community data repo CI later.
"""
from __future__ import annotations

import re
from typing import Any

PROFILES = ("quality", "balanced", "performance", "uncapped")
RESOLUTIONS = ("720p", "800p", "1080p", "1200p", "1440p", "1600p", "2160p")

ENV_ALLOW = re.compile(r"^(DXVK_|VKD3D_|PROTON_|MANGOHUD|WINEDLLOVERRIDES$|SDL_|MESA_|RADV_)")
ENV_DENY = {"LD_PRELOAD", "LD_LIBRARY_PATH", "PATH", "HOME", "SHELL"}
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
DEVICE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
NATIVE = re.compile(r"^[1-9][0-9]{2,4}x[1-9][0-9]{2,4}$")
DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


class ValidationError(ValueError):
    pass


def _obj(x: Any, where: str, allowed: set[str], required: set[str] = set()) -> dict[str, Any]:
    if not isinstance(x, dict):
        raise ValidationError(f"{where}: expected object")
    extra = set(x) - allowed
    if extra:
        raise ValidationError(f"{where}: unknown fields {sorted(extra)}")
    missing = required - set(x)
    if missing:
        raise ValidationError(f"{where}: missing fields {sorted(missing)}")
    return x


def _str(x: Any, where: str, max_len: int) -> str:
    if not isinstance(x, str) or not x or len(x) > max_len:
        raise ValidationError(f"{where}: expected string of 1..{max_len} chars")
    return x


def validate_env(env: Any) -> dict[str, str]:
    if not isinstance(env, dict) or len(env) > 16:
        raise ValidationError("env: expected object with at most 16 entries")
    for k, v in env.items():
        if not isinstance(k, str) or not ENV_NAME.match(k) or k in ENV_DENY or not ENV_ALLOW.match(k):
            raise ValidationError(f"variable not allowed: {k!r}")
        # LOADOUT_ is reserved for the launch-option markers (see launch.py).
        if not isinstance(v, str) or len(v) > 256 or any(ord(c) < 32 for c in v) or "LOADOUT_" in v:
            raise ValidationError(f"invalid value in {k}")
    return dict(env)


def validate_level(x: Any, where: str) -> dict[str, Any]:
    _obj(x, where, {"fps_limit", "env"})
    out: dict[str, Any] = {}
    if "fps_limit" in x:
        fps = x["fps_limit"]
        if type(fps) is not int or not 10 <= fps <= 240:
            raise ValidationError(f"{where}.fps_limit: expected integer 10..240")
        out["fps_limit"] = fps
    if "env" in x:
        out["env"] = validate_env(x["env"])
    return out


def validate_device_doc(doc: Any) -> dict[str, Any]:
    """Returns a clean copy or raises ValidationError. Level keys are resolution classes or "any"."""
    _obj(doc, "device", {"schema_version", "device", "name", "match", "native", "levels"},
         {"schema_version", "device", "name", "match", "native", "levels"})
    if doc["schema_version"] != 1:
        raise ValidationError("unsupported schema_version")
    if not isinstance(doc["device"], str) or not DEVICE_ID.match(doc["device"]):
        raise ValidationError("device: invalid id")
    name = _str(doc["name"], "name", 60)
    match = _obj(doc["match"], "match", {"product_name"}, {"product_name"})
    names = match["product_name"]
    if not isinstance(names, list) or len(names) > 16:
        raise ValidationError("match.product_name: expected list of at most 16")
    names = [_str(n, "match.product_name[]", 64) for n in names]
    if not isinstance(doc["native"], str) or not NATIVE.match(doc["native"]):
        raise ValidationError("native: expected WIDTHxHEIGHT")
    levels = _obj(doc["levels"], "levels", set(PROFILES))
    clean_levels = {}
    for profile, by_res in levels.items():
        _obj(by_res, f"levels.{profile}", set(RESOLUTIONS) | {"any"})
        clean_levels[profile] = {r: validate_level(v, f"levels.{profile}.{r}") for r, v in by_res.items()}
    return {"device": doc["device"], "name": name, "match": names,
            "native": doc["native"], "levels": clean_levels}


def validate_game_doc(doc: Any) -> dict[str, Any]:
    """Device-independent per-game data. Returns {appid, name, source, verified: [...], profiles: {p: {env}}}."""
    _obj(doc, "game", {"schema_version", "appid", "name", "source", "verified", "profiles"},
         {"schema_version", "appid", "name", "profiles"})
    if doc["schema_version"] != 1:
        raise ValidationError("unsupported schema_version")
    appid = doc["appid"]
    if type(appid) is not int or not 0 < appid < 2**32:
        raise ValidationError("appid: expected positive integer")
    name = _str(doc["name"], "name", 120)
    source = None
    if "source" in doc:
        source = _str(doc["source"], "source", 300)
        if not source.startswith("https://"):
            raise ValidationError("source: expected https URL")
    raw = doc.get("verified", [])
    if not isinstance(raw, list) or len(raw) > 16:
        raise ValidationError("verified: expected list of at most 16")
    verified = []
    for v in raw:
        _obj(v, "verified[]", {"proton", "device", "date"}, {"proton", "device", "date"})
        if not isinstance(v["device"], str) or not DEVICE_ID.match(v["device"]):
            raise ValidationError("verified.device: invalid id")
        if not isinstance(v["date"], str) or not DATE.match(v["date"]):
            raise ValidationError("verified.date: expected YYYY-MM-DD")
        verified.append({"proton": _str(v["proton"], "verified.proton", 40), "device": v["device"], "date": v["date"]})
    profiles = _obj(doc["profiles"], "profiles", set(PROFILES))
    clean = {}
    for profile, body in profiles.items():
        _obj(body, f"profiles.{profile}", {"launch"})
        env: dict[str, str] = {}
        if "launch" in body:
            env = validate_env(_obj(body["launch"], f"profiles.{profile}.launch", {"env"}, {"env"})["env"])
        clean[profile] = {"env": env}
    return {"appid": appid, "name": name, "source": source, "verified": verified, "profiles": clean}
