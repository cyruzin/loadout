"""Pure planning: (current launch options, stored state, level) -> Plan. Never writes."""
from __future__ import annotations

from typing import Any, Literal, NamedTuple, Optional

from . import launch
from .files import FilePlan
from .validate import PROFILES

ALL_PROFILES = ("default",) + PROFILES


# NamedTuple, not dataclasses: Decky's frozen Python only ships the stdlib modules it uses itself.
class Change(NamedTuple):
    kind: Literal["launch_option", "env", "arg", "file_key"]
    target: str
    key: str
    old: Optional[str]  # None means "absent"
    new: Optional[str]


class Plan(NamedTuple):
    appid: int
    profile: str
    original: str  # user's launch options without our block: what Default returns to
    launch_options: str  # the string to write
    changes: tuple[Change, ...]
    warnings: tuple[str, ...]
    blocked: bool  # markers corrupted or a file problem: nothing may be applied or restored
    file_writes: tuple[tuple[str, dict[str, str]], ...]
    file_state: dict[str, dict[str, dict[str, str]]]

    def to_dict(self) -> dict[str, Any]:
        return {**self._asdict(), "changes": [c._asdict() for c in self.changes]}


def profile_env(level: dict[str, Any], game_env: Optional[dict[str, str]] = None) -> dict[str, str]:
    """Device level env, then per-game env (wins on conflict), then the FPS cap if not already set."""
    env = {**level.get("env", {}), **(game_env or {})}
    fps = level.get("fps_limit")
    if fps:
        # FPS cap via DXVK/VKD3D limiters (D3D games under Proton). A gamescope-level
        # cap needs Steam internals that aren't a public API yet.
        env.setdefault("DXVK_FRAME_RATE", str(fps))
        env.setdefault("VKD3D_FRAME_RATE", str(fps))
    return env


def build_plan(appid: int, profile: str, current: str, entry: Optional[dict[str, Any]],
               level: dict[str, Any], approximate: bool,
               game_env: Optional[dict[str, str]] = None, file_plan: Optional[FilePlan] = None,
               game_args: tuple[str, ...] = ()) -> Plan:
    """`entry` is this game's state ({"original", "written"}) or None if Loadout never touched it."""
    if profile not in ALL_PROFILES:
        raise ValueError(f"unknown profile: {profile!r}")
    entry = entry or {}
    # Always start from the original: switching Performance -> Quality never stacks (I5).
    base, warning = launch.restore(current, entry.get("written"), entry.get("original"))
    warnings = [warning] if warning else []
    env = {} if profile == "default" else profile_env(level, game_env)
    args = () if profile == "default" else tuple(game_args)
    new = base if warning else launch.build(base, env, args)
    if approximate and profile != "default":
        warnings.append("No exact values for this device/resolution; using approximate ones.")
    changes = [Change("env", "launch_options", k, None, v) for k, v in env.items()] if not warning else []
    changes += [Change("arg", "launch_options", a, None, a) for a in args] if not warning else []
    if new != current:
        changes.append(Change("launch_option", "launch_options", "LaunchOptions", current, new))
    fp = file_plan or FilePlan()
    warnings += list(fp.warnings) + ([fp.error] if fp.error else [])
    changes += [Change("file_key", c.path, c.key, c.old, c.new) for c in fp.changes]
    return Plan(appid, profile, base, new, tuple(changes), tuple(warnings),
                warning is not None or fp.error is not None, fp.writes, dict(fp.state or {}))
