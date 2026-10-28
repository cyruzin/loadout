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

DEVICES = devices.load_devices()
# Detected once, never asked: an undetected device uses the generic table (targets only; profiles
# are borrowed per game with "Use profiles from"). No manual override: add one if a device turns out
# to be detected wrong (e.g. a Legion Go without a valid product_name).
DEVICE = devices.detect(DEVICES, devices.read_dmi()) or devices.GENERIC


# Intent only (forward-compatible, later the export format). Backups live in STATE.
def _default_settings():
    return {
        "schema_version": 1, "global_profile": None, "games": {},
        # No game has generic profiles, so "verified" would list nothing there.
        "game_filter": "loadout" if DEVICE == devices.GENERIC else "verified",
        "last_game": None,  # last game a profile was applied to: selected when the QAM opens
    }


SETTINGS = JsonStore(Path(decky.DECKY_PLUGIN_SETTINGS_DIR) / "settings.json", _default_settings())
STATE = JsonStore(Path(decky.DECKY_PLUGIN_RUNTIME_DIR) / "state.json", {"schema_version": 1, "games": {}})
GAMES = games.load_games()


def _check_appid(appid):
    if type(appid) is not int or appid <= 0:
        raise ValueError("invalid appid")
    return str(appid)


def _ctx(appid):
    home = Path(decky.DECKY_USER_HOME)
    root = steam.find_steam_root(home)
    paths = steam.app_paths(root, appid) if root else None
    # Native Linux games keep their settings in ~/.local/share (files.allowed keeps Steam's folder out).
    return {**paths, "xdg_data": str(home / ".local/share")} if paths else None


def _level(profile):
    return devices.resolve_level(DEVICES, DEVICE, profile, devices.native_class(DEVICES[DEVICE]))


def _plan(appid, profile, current, profile_device):
    key = _check_appid(appid)
    if not isinstance(current, str) or len(current) > 4096:
        raise ValueError("invalid launch options")
    level, approx = _level(profile)
    # This device's profiles, else the ones borrowed from the device the user picked.
    spec = games.profile_spec(GAMES.get(appid), DEVICE, profile_device, profile)
    entry = STATE.load()["games"].get(key)
    # Keys Loadout wrote before (e.g. a resolution from 0.3.0) and the new profile doesn't set
    # are restored to their originals here.
    file_plan = files.plan_files(spec.get("files", []), _ctx(appid), (entry or {}).get("files", {}))
    return planner.build_plan(appid, profile, current, entry, level, approx, spec.get("env"), file_plan,
                              tuple(spec.get("args", ())))


class Plugin:
    async def get_bootstrap(self):
        return {
            "settings": SETTINGS.load(),
            "device": DEVICE,
            # Each profile's target FPS on this device: shown, the user sets Steam's frame limit.
            "fps_targets": {p: _level(p)[0].get("fps_limit") for p in PROFILES},
            "devices": [{"id": d["device"], "name": d["name"]} for d in DEVICES.values()],
        }

    async def list_games(self):
        root = steam.find_steam_root(Path(decky.DECKY_USER_HOME))
        installed = steam.list_games(root) if root else []
        return games.annotate(installed, GAMES, STATE.load()["games"], DEVICE)

    async def set_game_filter(self, game_filter):
        if game_filter not in GAME_FILTERS:
            raise ValueError("invalid game filter")
        s = SETTINGS.load()
        s["game_filter"] = game_filter
        SETTINGS.save(s)
        return s

    async def reset_settings(self):
        """Back to first run. The frontend applies Default to every game with a profile first;
        backups in STATE stay for any game it couldn't restore."""
        s = _default_settings()
        SETTINGS.save(s)
        decky.logger.info("settings reset")
        return s

    async def plan_profile(self, appid, profile, current, profile_device=None):
        return _plan(appid, profile, current, profile_device).to_dict()

    async def apply_profile(self, appid, profile, current, profile_device=None):
        """Records state and returns the launch options the frontend must write."""
        plan = _plan(appid, profile, current, profile_device)
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
        s["games"].setdefault(key, {"profile": "default"}).update(profile=profile, profile_device=profile_device)
        s["last_game"] = appid
        SETTINGS.save(s)
        decky.logger.info(f"applied {profile} to {appid}")
        return {"launch_options": plan.launch_options, "warnings": list(plan.warnings), "applied": True}

    async def _main(self):
        decky.logger.info("Loadout loaded")

    async def _unload(self):
        pass
