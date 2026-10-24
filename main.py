"""Thin Decky adapter: wires real paths into the `loadout` core package."""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "py_modules"))

import decky  # noqa: E402
from loadout import devices, files, games, planner, steam  # noqa: E402
from loadout.store import JsonStore  # noqa: E402
from loadout.games import GAME_FILTERS  # noqa: E402
from loadout.validate import RESOLUTIONS  # noqa: E402

# Intent only (forward-compatible, later the export format). Backups live in STATE.
SETTINGS = JsonStore(Path(decky.DECKY_PLUGIN_SETTINGS_DIR) / "settings.json", {
    "schema_version": 1, "device": None, "global_profile": None, "games": {},
    "game_filter": "verified",
    "last_game": None,  # last game a profile or resolution was applied to: selected when the QAM opens
})
STATE = JsonStore(Path(decky.DECKY_PLUGIN_RUNTIME_DIR) / "state.json", {"schema_version": 1, "games": {}})
DEVICES = devices.load_devices()
GAMES = games.load_games()


def _check_appid(appid):
    if type(appid) is not int or appid <= 0:
        raise ValueError("invalid appid")
    return str(appid)


def _display(s):
    """(native "WxH", external) of the screen in use right now, else the device's own panel."""
    dev = DEVICES.get(s["device"] or "") or DEVICES[devices.GENERIC]
    return devices.read_display() or (dev["native"], False)


def _resolution(appid, s, native=None):
    """(resolution class or None, file edits that write it) for this game. Loadout only writes a
    resolution the user picked for the game (capped to the screen in use); with no pick the game
    and Steam's own resolution setting decide, so nothing is written."""
    pick = s["games"].get(str(appid), {}).get("resolution")
    if pick is None:
        return None, []
    native = native or _display(s)[0]
    res = devices.clamp_resolution(pick, native)
    return res, games.resolution_files(GAMES.get(appid), *devices.resolution_size(res, native))


def _ctx(appid):
    root = steam.find_steam_root(Path(decky.DECKY_USER_HOME))
    return steam.app_paths(root, appid) if root else None


def _plan(appid, profile, current):
    key = _check_appid(appid)
    if not isinstance(current, str) or len(current) > 4096:
        raise ValueError("invalid launch options")
    s = SETTINGS.load()
    res, res_files = _resolution(appid, s)
    native = _display(s)[0]
    level, approx = devices.resolve_level(DEVICES, s["device"], profile, res or devices.clamp_resolution(None, native))
    spec = GAMES.get(appid, {}).get("profiles", {}).get(profile, {})
    specs = list(spec.get("files", []))
    if profile != "default":  # Default restores the original resolution with everything else
        specs += res_files
    entry = STATE.load()["games"].get(key)
    file_plan = files.plan_files(specs, _ctx(appid), (entry or {}).get("files", {}))
    return planner.build_plan(appid, profile, current, entry, level, approx, spec.get("env"), file_plan)


class Plugin:
    async def get_bootstrap(self):
        detected = devices.detect(DEVICES, devices.read_dmi())
        s = SETTINGS.load()
        native, external = _display(s)
        # Games whose written resolution belongs to another screen (docked <-> handheld).
        stale = [int(key) for key, entry in STATE.load()["games"].items()
                 if games.resolution_stale(entry.get("files", {}), _resolution(int(key), s, native)[1])]
        return {
            "settings": s,
            "display": {"native": native, "resolution": devices.clamp_resolution(None, native), "external": external},
            "stale": stale,
            "detected": detected,
            "devices": [{"id": d["device"], "name": d["name"], "native": devices.native_class(d)}
                        for d in DEVICES.values()],
            "resolutions": list(RESOLUTIONS),
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

    async def set_game_resolution(self, appid, resolution):
        key = _check_appid(appid)
        if resolution is not None and resolution not in RESOLUTIONS:
            raise ValueError("invalid resolution")
        s = SETTINGS.load()
        s["games"].setdefault(key, {"profile": "default", "resolution": None})["resolution"] = resolution
        SETTINGS.save(s)
        return s

    async def apply_resolution(self, appid):
        """Write only this game's resolution, keeping whatever profile is applied. With no pick
        ("keep the game's setting"), put back the original resolution if Loadout had changed it."""
        key = _check_appid(appid)
        res, res_files = _resolution(appid, SETTINGS.load())
        keys = games.resolution_keys(GAMES.get(appid))
        if not keys:
            return {"applied": False, "warnings": ["Loadout can't set this game's resolution."]}
        state = STATE.load()
        entry = state["games"].get(key, {})
        written = entry.get("files", {})
        if res_files:
            plan = files.plan_keys(res_files, _ctx(appid), written)
            new_files = plan.state
        else:
            ours = {p: {k: v for k, v in ks.items() if k in keys} for p, ks in written.items()}
            ours = {p: ks for p, ks in ours.items() if ks}
            if not ours:
                return {"applied": True, "warnings": [], "resolution": None}  # never changed it
            plan = files.plan_files([], _ctx(appid), ours)  # restores them; keeps in-game edits
            new_files = {p: {k: v for k, v in ks.items() if k not in keys} for p, ks in written.items()}
            new_files = {p: ks for p, ks in new_files.items() if ks}
        if plan.error:
            return {"applied": False, "warnings": [plan.error]}
        files.apply_writes(plan.writes)  # raises (after rolling back) on failure
        # The originals stay recorded, so Default still restores the resolution with everything else.
        state["games"][key] = {**entry, "files": new_files}
        STATE.save(state)
        s = SETTINGS.load()
        s["last_game"] = appid
        SETTINGS.save(s)
        decky.logger.info(f"applied resolution {res} to {appid}")
        return {"applied": True, "warnings": list(plan.warnings), "resolution": res}

    async def plan_profile(self, appid, profile, current):
        return _plan(appid, profile, current).to_dict()

    async def apply_profile(self, appid, profile, current):
        """Records state and returns the launch options the frontend must write."""
        plan = _plan(appid, profile, current)
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
        s["games"].setdefault(key, {"profile": "default", "resolution": None})["profile"] = profile
        s["last_game"] = appid
        SETTINGS.save(s)
        decky.logger.info(f"applied {profile} to {appid}")
        return {"launch_options": plan.launch_options, "warnings": list(plan.warnings), "applied": True}

    async def _main(self):
        decky.logger.info("Loadout loaded")

    async def _unload(self):
        pass
