"""Per-key edits of game config files: read-only planning, then an all-or-nothing apply."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, NamedTuple, Optional

from . import inicfg, jsoncfg, xmlcfg
from .paths import safe_path
from .store import atomic_write

MAX_SIZE = 1024 * 1024


class FileChange(NamedTuple):
    path: str
    key: str
    old: str
    new: str


class FilePlan(NamedTuple):
    changes: tuple[FileChange, ...] = ()
    warnings: tuple[str, ...] = ()
    error: Optional[str] = None
    writes: tuple[tuple[str, dict[str, str]], ...] = ()  # (path, {key: value}) to write
    state: Optional[dict[str, dict[str, dict[str, str]]]] = None  # path -> key -> {old, new}


def handler(key: str) -> Any:
    """INI keys are written "[Section]Key", JSON keys "/path"; XML element names can't start with
    either. Validation ties each file's keys to its declared format, so they all pick the same one."""
    if key.startswith("["):
        return inicfg
    return jsoncfg if key.startswith("/") else xmlcfg


def read_nofollow(p: Path) -> bytes:
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as f:
        raw = f.read(MAX_SIZE + 1)
    if len(raw) > MAX_SIZE:
        raise OSError(f"{p.name} is too large")
    return raw


def plan_files(specs: list[dict[str, Any]], ctx: Optional[dict[str, str]],
               previous: dict[str, dict[str, dict[str, str]]]) -> FilePlan:
    """Never writes. `previous` is what Loadout wrote last time (from state); those keys are
    restored to their original value unless the new profile sets them again (no stacking)."""
    if not specs and not previous:
        return FilePlan()
    if ctx is None:
        return FilePlan(error="Game folder not found, so its config files can't be checked.")
    roots = [Path(ctx["prefix"]), Path(ctx["install_dir"])]
    targets: dict[Path, dict[str, str]] = {}
    try:
        for spec in specs:
            targets.setdefault(safe_path(spec["path"], ctx, roots), {}).update(spec["set"])
    except (ValueError, PermissionError) as e:
        return FilePlan(error=f"Unsafe config path rejected: {e}")
    for p in previous:
        path = Path(p)
        if path not in targets and any(path.is_relative_to(r.resolve()) for r in roots):
            targets[path] = {}

    changes: list[FileChange] = []
    warnings = [f"{Path(p).name}: no longer in the game folder, not restored."
                for p in previous if Path(p) not in targets]
    writes: list[tuple[str, dict[str, str]]] = []
    state: dict[str, dict[str, dict[str, str]]] = {}
    for path, want in targets.items():
        prev = previous.get(str(path), {})
        try:
            raw = read_nofollow(path)
        except FileNotFoundError:
            if want:
                return FilePlan(error=f"{path.name} not found. Launch the game once so it creates its "
                                      "settings, then try again.")
            warnings.append(f"{path.name} is gone; nothing to restore.")
            continue
        except OSError as e:
            return FilePlan(error=f"Can't read {path.name}: {e}")
        target: dict[str, str] = {}
        new_state: dict[str, dict[str, str]] = {}
        for key in sorted(set(want) | set(prev)):
            try:
                current = handler(key).read_values(raw, [key])[key]
            except ValueError as e:
                if key in want:
                    return FilePlan(error=f"{path.name}: {e}")
                warnings.append(f"{path.name}: {key} no longer present, not restored.")
                continue
            base = current
            if key in prev:
                if current == prev[key]["new"]:
                    base = prev[key]["old"]
                elif key not in want:
                    warnings.append(f"{path.name}: {key} was changed in game since Loadout set it; keeping it.")
            value = want.get(key, base)
            if key in want:
                new_state[key] = {"old": base, "new": value}
            if value != current:
                target[key] = value
                changes.append(FileChange(str(path), key, current, value))
        if target:
            writes.append((str(path), target))
        if new_state:
            state[str(path)] = new_state
    return FilePlan(tuple(changes), tuple(warnings), None, tuple(writes), state)


def plan_keys(specs: list[dict[str, Any]], ctx: Optional[dict[str, str]],
               previous: dict[str, dict[str, dict[str, str]]]) -> FilePlan:
    """Like plan_files, but only the keys in `specs` change: everything else Loadout set stays as
    it is (the resolution can change without re-applying the profile). Originals are kept."""
    if ctx is None:
        return FilePlan(error="Game folder not found, so its config files can't be checked.")
    roots = [Path(ctx["prefix"]), Path(ctx["install_dir"])]
    try:
        paths = {str(safe_path(s["path"], ctx, roots)) for s in specs}
    except (ValueError, PermissionError) as e:
        return FilePlan(error=f"Unsafe config path rejected: {e}")
    keys = {k for s in specs for k in s["set"]}
    subset = {p: {k: v for k, v in previous.get(p, {}).items() if k in keys} for p in paths}
    plan = plan_files(specs, ctx, {p: ks for p, ks in subset.items() if ks})
    merged = {p: dict(ks) for p, ks in previous.items()}
    for p, ks in (plan.state or {}).items():
        merged.setdefault(p, {}).update(ks)
    return plan._replace(state=merged)


def apply_writes(writes: tuple[tuple[str, dict[str, str]], ...]) -> None:
    """All or nothing: if any file fails, the ones already written get their original bytes back."""
    done: list[tuple[Path, bytes]] = []
    try:
        for path_s, values in writes:
            path = Path(path_s)
            if path.parent.resolve() != path.parent:
                raise PermissionError(f"{path.parent} changed since planning")
            raw = read_nofollow(path)
            atomic_write(path, handler(next(iter(values))).set_values(raw, values))
            done.append((path, raw))
    except BaseException:
        for path, raw in reversed(done):
            atomic_write(path, raw)
        raise
