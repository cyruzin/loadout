"""Thin Decky adapter: wires real paths into the `loadout` core package."""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "py_modules"))

import decky  # noqa: E402
from loadout import devices, files, games, planner, steam  # noqa: E402
from loadout.store import JsonStore  # noqa: E402
from loadout.games import GAME_FILTERS  # noqa: E402
from loadout.validate import PROFILES  # noqa: E402

# Intent only (forward-compatible, later the export format). Backups live in STATE.
SETTINGS = JsonStore(Path(decky.DECKY_PLUGIN_SETTINGS_DIR) / "settings.json", {
    "schema_version": 1, "device": None, "global_profile": None, "games": {},
    "game_filter": "verified",
    "last_game": None,  # last game a profile was applied to: selected when the QAM opens
})
STATE = JsonStore(Path(decky.DECKY_PLUGIN_RUNTIME_DIR) / "state.json", {"schema_version": 1, "games": {}})
DEVICES = devices.load_devices()
GAMES = games.load_games()


def _check_appid(appid):
    if type(appid) is not int or appid <= 0:
        raise ValueError("invalid appid")
    return str(appid)


def _ctx(appid):
    root = steam.find_steam_root(Path(decky.DECKY_USER_HOME))
    return steam.app_paths(root, appid) if root else None


def _level(device, profile):
    dev = DEVICES.get(device or "") or DEVICES[devices.GENERIC]
    return devices.resolve_level(DEVICES, device, profile, devices.native_class(dev))


def _plan(appid, profile, current, fps_cap):
    key = _check_appid(appid)
    if not isinstance(current, str) or len(current) > 4096:
        raise ValueError("invalid launch options")
    if type(fps_cap) is not bool:
        raise ValueError("invalid fps_cap")
    level, approx = _level(SETTINGS.load()["device"], profile)
    spec = GAMES.get(appid, {}).get("profiles", {}).get(profile, {})
    entry = STATE.load()["games"].get(key)
    # Keys Loadout wrote before (e.g. a resolution from 0.3.0) and the new profile doesn't set
    # are restored to their originals here.
    file_plan = files.plan_files(spec.get("files", []), _ctx(appid), (entry or {}).get("files", {}))
    return planner.build_plan(appid, profile, current, entry, level, approx, spec.get("env"), file_plan,
                              tuple(spec.get("args", ())), fps_cap)


class Plugin:
    async def get_bootstrap(self):
        detected = devices.detect(DEVICES, devices.read_dmi())
        s = SETTINGS.load()
        return {
            "settings": s,
            # Each profile's FPS cap on the configured device, for the cap switch's label.
            "fps_limits": {p: _level(s["device"], p)[0].get("fps_limit") for p in PROFILES},
            "detected": detected,
            "devices": [{"id": d["device"], "name": d["name"], "native": devices.native_class(d)}
                        for d in DEVICES.values()],
        }

    async def list_games(self):
        root = steam.find_steam_root(Path(decky.DECKY_USER_HOME))
        installed = steam.list_games(root) if root else []
        return games.annotate(installed, GAMES, STATE.load()["games"], SETTINGS.load()["device"])

    async def set_game_filter(self, game_filter):
        if game_filter not in GAME_FILTERS:
            raise ValueError("invalid game filter")
        s = SETTINGS.load()
        s["game_filter"] = game_filter
        SETTINGS.save(s)
        return s

    async def save_settings(self, device):
        if device not in DEVICES:
            raise ValueError("invalid device")
        s = SETTINGS.load()
        s["device"] = device
        SETTINGS.save(s)
        return s

    async def plan_profile(self, appid, profile, current, fps_cap=True):
        return _plan(appid, profile, current, fps_cap).to_dict()

    async def apply_profile(self, appid, profile, current, fps_cap=True):
        """Records state and returns the launch options the frontend must write."""
        plan = _plan(appid, profile, current, fps_cap)
        key = str(appid)
        if plan.blocked:
            return {"launch_options": current, "warnings": list(plan.warnings), "applied": False}
        files.apply_writes(plan.file_writes)  # raises (after rolling back) on failure
        state = STATE.load()
        if profile == "default":
            state["games"].pop(key, None)
        else:
            state["games"][key] = {"profile": profile, "original": plan.original, "written": plan.launch_options,
                                   "files": plan.file_state}
        STATE.save(state)
        s = SETTINGS.load()
        s["games"].setdefault(key, {"profile": "default"}).update(profile=profile, fps_cap=fps_cap)
        s["last_game"] = appid
        SETTINGS.save(s)
        decky.logger.info(f"applied {profile} to {appid}")
        return {"launch_options": plan.launch_options, "warnings": list(plan.warnings), "applied": True}

    async def _main(self):
        decky.logger.info("Loadout loaded")

    async def _unload(self):
        pass
