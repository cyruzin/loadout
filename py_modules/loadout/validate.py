"""Structural + semantic validation of data documents (devices/*.json, games/*.json).

Stdlib only on purpose: no compiled deps to bundle. The same module is meant
to run in the community data repo CI later.
"""
from __future__ import annotations

import re
from typing import Any

from . import inicfg, jsoncfg, lsxcfg, xmlcfg
from .textfile import VALUE
from .paths import ROOT_TOKENS, expand

# No "uncapped" since 0.6.0: without Loadout's FPS cap it was Performance again (Steam's QAM sets the limit).
PROFILES = ("quality", "balanced", "performance")
RESOLUTIONS = ("720p", "800p", "1080p", "1200p", "1440p", "1600p", "2160p")

ENV_ALLOW = re.compile(r"^(DXVK_|VKD3D_|PROTON_|MANGOHUD|WINEDLLOVERRIDES$|SDL_|MESA_|RADV_)")
ENV_DENY = {"LD_PRELOAD", "LD_LIBRARY_PATH", "PATH", "HOME", "SHELL"}
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
DEVICE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
NATIVE = re.compile(r"^[1-9][0-9]{2,4}x[1-9][0-9]{2,4}$")
# Game arguments after %command%: one plain flag each, e.g. "--launcher-skip".
ARG = re.compile(r"^--?[A-Za-z][A-Za-z0-9_-]{0,47}$")
DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
# Config file formats and their key syntax: XML element names, INI "[Section]Key", JSON "/path".
KEY_FORMATS = {"xml": xmlcfg.KEY, "ini": inicfg.KEY, "json": jsoncfg.KEY, "lsx": lsxcfg.KEY}


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


def _path_template(x: Any, where: str) -> str:
    path = _str(x, where, 300)
    if not path.startswith(ROOT_TOKENS) or "\\" in path or any(seg in ("..", ".") for seg in path.split("/")):
        raise ValidationError(f"{where}: must start with {{prefix}}/, {{install_dir}}/ or {{xdg_data}}/, no . or ..")
    try:
        expand(path, {"prefix": "", "install_dir": "", "xdg_data": "", "appid": ""})
    except ValueError as e:
        raise ValidationError(f"{where}: {e}") from None
    return path


def validate_options(x: Any) -> dict[str, dict[str, list[str]]]:
    """Accepted values per key, per config file: {path: {key: [values]}}. Copied from the game."""
    if not isinstance(x, dict) or len(x) > 8:
        raise ValidationError("options: expected object with at most 8 files")
    out = {}
    for path, keys in x.items():
        _path_template(path, "options path")
        if not isinstance(keys, dict) or len(keys) > 64:
            raise ValidationError(f"options[{path}]: expected object with at most 64 keys")
        for k, vals in keys.items():
            if not isinstance(k, str) or not any(fmt.match(k) for fmt in KEY_FORMATS.values()):
                raise ValidationError(f"options: invalid key {k!r}")
            if (not isinstance(vals, list) or not 0 < len(vals) <= 16
                    or not all(isinstance(s, str) and VALUE.match(s) for s in vals)):
                raise ValidationError(f"options.{k}: expected list of 1..16 values")
        out[path] = {k: list(vals) for k, vals in keys.items()}
    return out


def validate_files(x: Any, where: str) -> list[dict[str, Any]]:
    """Shape and meaning of config-file edits. Containment is checked again at apply time."""
    if not isinstance(x, list) or len(x) > 8:
        raise ValidationError(f"{where}: expected list of at most 8")
    out = []
    for i, f in enumerate(x):
        w = f"{where}[{i}]"
        _obj(f, w, {"path", "format", "set"}, {"path", "format", "set"})
        path = _path_template(f["path"], f"{w}.path")
        key_re = KEY_FORMATS.get(f["format"])
        if key_re is None:
            raise ValidationError(f"{w}.format: expected one of {sorted(KEY_FORMATS)}")
        # files.handler picks Larian's parser by extension: the two must agree.
        if (f["format"] == "lsx") != path.endswith(".lsx"):
            raise ValidationError(f"{w}: .lsx files use format lsx, and only them")
        values = f["set"]
        if not isinstance(values, dict) or not 0 < len(values) <= 64:
            raise ValidationError(f"{w}.set: expected 1..64 keys")
        for k, val in values.items():
            if not isinstance(k, str) or not key_re.match(k):
                raise ValidationError(f"{w}.set: invalid {f['format']} key {k!r}")
            # null (lsx only): remove the key, i.e. the game's default, which it doesn't write.
            if not (val is None and f["format"] == "lsx") and (not isinstance(val, str) or not VALUE.match(val)):
                raise ValidationError(f"{w}.set.{k}: invalid value")
        out.append({"path": path, "format": f["format"], "set": dict(values)})
    return out


def _profiles(x: Any, options: dict[str, dict[str, list[str]]], where: str) -> dict[str, Any]:
    profiles = _obj(x, where, set(PROFILES))
    clean = {}
    for profile, body in profiles.items():
        w = f"{where}.{profile}"
        # resolution: what the profile was tested/is meant for, shown to the user. Never written.
        _obj(body, w, {"resolution", "launch", "files"})
        resolution = body.get("resolution")
        if "resolution" in body and (not isinstance(resolution, str) or not NATIVE.match(resolution)):
            raise ValidationError(f"{w}.resolution: expected WIDTHxHEIGHT")
        env: dict[str, str] = {}
        args: list[str] = []
        if "launch" in body:
            launch = _obj(body["launch"], f"{w}.launch", {"env", "args"})
            env = validate_env(launch.get("env", {}))
            args = launch.get("args", [])
            if (not isinstance(args, list) or len(args) > 8 or len(set(args)) != len(args)
                    or not all(isinstance(a, str) and ARG.match(a) for a in args)):
                raise ValidationError(f"{w}.launch.args: expected up to 8 plain flags")
        clean[profile] = {"resolution": resolution, "env": env, "args": list(args),
                          "files": validate_files(body.get("files", []), f"{w}.files")}
        for f in clean[profile]["files"]:
            for k, val in f["set"].items():
                allowed = options.get(f["path"], {}).get(k)
                if allowed is not None and val is not None and val not in allowed:
                    raise ValidationError(f"{w}: {k}={val} not in {allowed}")
    return clean


def _device_entry(x: Any, options: dict[str, dict[str, list[str]]], where: str) -> dict[str, Any]:
    """One device's profiles, tested on that device (`verified`) and where they came from (`source`)."""
    _obj(x, where, {"source", "verified", "profiles"}, {"verified", "profiles"})
    source = None
    if "source" in x:
        source = _str(x["source"], f"{where}.source", 300)
        if not source.startswith("https://"):
            raise ValidationError(f"{where}.source: expected https URL")
    v = _obj(x["verified"], f"{where}.verified", {"proton", "date"}, {"proton", "date"})
    if not isinstance(v["date"], str) or not DATE.match(v["date"]):
        raise ValidationError(f"{where}.verified.date: expected YYYY-MM-DD")
    verified = {"proton": _str(v["proton"], f"{where}.verified.proton", 40), "date": v["date"]}
    return {"source": source, "verified": verified, "profiles": _profiles(x["profiles"], options, f"{where}.profiles")}


def validate_game_doc(doc: Any) -> dict[str, Any]:
    """Per-game data, profiles per device: each device's block can be tuned (or added) on its own.
    Returns {appid, name, options, devices: {device_id: {source, verified, profiles: {p: {env, args, files}}}}}."""
    _obj(doc, "game", {"schema_version", "appid", "name", "options", "devices"},
         {"schema_version", "appid", "name", "devices"})
    if doc["schema_version"] != 2:
        raise ValidationError("unsupported schema_version")
    appid = doc["appid"]
    if type(appid) is not int or not 0 < appid < 2**32:
        raise ValidationError("appid: expected positive integer")
    name = _str(doc["name"], "name", 120)
    options = validate_options(doc.get("options", {}))
    devs = doc["devices"]
    if not isinstance(devs, dict) or not 0 < len(devs) <= 32:
        raise ValidationError("devices: expected object with 1..32 devices")
    clean = {}
    for dev_id, entry in devs.items():
        if not isinstance(dev_id, str) or not DEVICE_ID.match(dev_id):
            raise ValidationError(f"devices: invalid id {dev_id!r}")
        clean[dev_id] = _device_entry(entry, options, f"devices.{dev_id}")
    return {"appid": appid, "name": name, "options": options, "devices": clean}
