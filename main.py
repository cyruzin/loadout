"""Thin Decky adapter: wires real paths into the `loadout` core package."""
import os
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "py_modules"))

import decky  # noqa: E402
from loadout import devices, planner, steam  # noqa: E402
from loadout.store import JsonStore  # noqa: E402
from loadout.validate import RESOLUTIONS  # noqa: E402

# Intent only (forward-compatible, later the export format). Backups live in STATE.
SETTINGS = JsonStore(Path(decky.DECKY_PLUGIN_SETTINGS_DIR) / "settings.json", {
    "schema_version": 1, "device": None, "render_resolution": None, "global_profile": None, "games": {},
})
STATE = JsonStore(Path(decky.DECKY_PLUGIN_RUNTIME_DIR) / "state.json", {"schema_version": 1, "games": {}})
DEVICES = devices.load_devices()


def _check_appid(appid):
    if type(appid) is not int or appid <= 0:
        raise ValueError("invalid appid")
    return str(appid)


def _plan(appid, profile, current):
    key = _check_appid(appid)
    if not isinstance(current, str) or len(current) > 4096:
        raise ValueError("invalid launch options")
    s = SETTINGS.load()
    dev = DEVICES.get(s["device"] or "") or DEVICES[devices.GENERIC]
    res = s["games"].get(key, {}).get("resolution") or s["render_resolution"] or devices.native_class(dev)
    level, approx = devices.resolve_level(DEVICES, s["device"], profile, res)
    return planner.build_plan(appid, profile, current, STATE.load()["games"].get(key), level, approx)


class Plugin:
    async def get_bootstrap(self):
        detected = devices.detect(DEVICES, devices.read_dmi())
        return {
            "settings": SETTINGS.load(),
            "detected": detected,
            "devices": [{"id": d["device"], "name": d["name"], "native": devices.native_class(d)}
                        for d in DEVICES.values()],
            "resolutions": list(RESOLUTIONS),
        }

    async def list_games(self):
        root = steam.find_steam_root(Path(decky.DECKY_USER_HOME))
        return steam.list_games(root) if root else []

    async def save_settings(self, device, render_resolution):
        if device not in DEVICES or render_resolution not in RESOLUTIONS:
            raise ValueError("invalid settings")
        s = SETTINGS.load()
        s.update(device=device, render_resolution=render_resolution)
        SETTINGS.save(s)
        return s

    async def set_game_resolution(self, appid, resolution):
        key = _check_appid(appid)
        if resolution is not None and resolution not in RESOLUTIONS:
            raise ValueError("invalid resolution")
        s = SETTINGS.load()
        s["games"].setdefault(key, {"profile": "default", "resolution": None})["resolution"] = resolution
        SETTINGS.save(s)
        return s

    async def plan_profile(self, appid, profile, current):
        return asdict(_plan(appid, profile, current))

    async def apply_profile(self, appid, profile, current):
        """Records state and returns the launch options the frontend must write."""
        plan = _plan(appid, profile, current)
        key = str(appid)
        if plan.blocked:
            return {"launch_options": current, "warnings": list(plan.warnings), "applied": False}
        state = STATE.load()
        if profile == "default":
            state["games"].pop(key, None)
        else:
            state["games"][key] = {"profile": profile, "original": plan.original, "written": plan.launch_options}
        STATE.save(state)
        s = SETTINGS.load()
        s["games"].setdefault(key, {"profile": "default", "resolution": None})["profile"] = profile
        SETTINGS.save(s)
        decky.logger.info(f"applied {profile} to {appid}")
        return {"launch_options": plan.launch_options, "warnings": list(plan.warnings), "applied": True}

    async def _main(self):
        decky.logger.info("Loadout loaded")

    async def _unload(self):
        pass
