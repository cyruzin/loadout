"""Pure planning: (current launch options, stored state, level) -> Plan. Never writes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional

from . import launch
from .validate import PROFILES

ALL_PROFILES = ("default",) + PROFILES


@dataclass(frozen=True)
class Change:
    kind: Literal["launch_option", "env"]
    target: str
    key: str
    old: Optional[str]  # None means "absent"
    new: Optional[str]


@dataclass(frozen=True)
class Plan:
    appid: int
    profile: str
    original: str  # user's launch options without our block: what Default returns to
    launch_options: str  # the string to write
    changes: tuple[Change, ...]
    warnings: tuple[str, ...]
    blocked: bool  # markers corrupted: nothing may be applied or restored


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
               game_env: Optional[dict[str, str]] = None) -> Plan:
    """`entry` is this game's state ({"original", "written"}) or None if Loadout never touched it."""
    if profile not in ALL_PROFILES:
        raise ValueError(f"unknown profile: {profile!r}")
    entry = entry or {}
    # Always start from the original: switching Performance -> Quality never stacks (I5).
    base, warning = launch.restore(current, entry.get("written"), entry.get("original"))
    warnings = [warning] if warning else []
    env = {} if profile == "default" else profile_env(level, game_env)
    new = base if warning else launch.build(base, env)
    if approximate and profile != "default":
        warnings.append("No exact values for this device/resolution; using approximate ones.")
    changes = [Change("env", "launch_options", k, None, v) for k, v in env.items()] if not warning else []
    if new != current:
        changes.append(Change("launch_option", "launch_options", "LaunchOptions", current, new))
    return Plan(appid, profile, base, new, tuple(changes), tuple(warnings), warning is not None)
