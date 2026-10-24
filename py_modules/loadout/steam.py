"""Installed games from libraryfolders.vdf + appmanifest_*.acf (no Steam client internals)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])')
_ESCAPE = re.compile(r"\\(.)")
# Rule: Steam tools/runtimes are hidden by name prefix.
TOOL_PREFIXES = ("Proton ", "Proton-", "Steam Linux Runtime", "Steamworks Common Redistributables")


def parse_vdf(text: str) -> dict[str, Any]:
    """Text KeyValues -> nested dicts. Raises ValueError on malformed input."""
    # Ignores // comments and #include, Steam doesn't write them in these files.
    stack: list[dict[str, Any]] = [{}]
    key: Optional[str] = None
    for m in _TOKEN.finditer(text):
        s, brace = m.group(1), m.group(2)
        if brace == "{":
            if key is None:
                raise ValueError("block without key")
            child: dict[str, Any] = {}
            stack[-1][key] = child
            stack.append(child)
            key = None
        elif brace == "}":
            if len(stack) == 1 or key is not None:
                raise ValueError("unbalanced block")
            stack.pop()
        elif key is None:
            key = _ESCAPE.sub(r"\1", s)
        else:
            stack[-1][key] = _ESCAPE.sub(r"\1", s)
            key = None
    if len(stack) != 1 or key is not None:
        raise ValueError("truncated vdf")
    return stack[0]


def _root_block(path: Path) -> dict[str, Any]:
    doc = parse_vdf(path.read_text(encoding="utf-8", errors="replace"))
    if len(doc) != 1 or not isinstance(next(iter(doc.values())), dict):
        raise ValueError(f"unexpected layout in {path}")
    return next(iter(doc.values()))


def find_steam_root(home: Path) -> Optional[Path]:
    for c in (home / ".local/share/Steam", home / ".steam/steam",
              home / ".var/app/com.valvesoftware.Steam/.local/share/Steam"):
        if (c / "steamapps").is_dir():
            return c
    return None


def library_paths(steam_root: Path) -> list[Path]:
    paths = [steam_root]
    try:
        folders = _root_block(steam_root / "steamapps/libraryfolders.vdf")
    except (OSError, ValueError):
        return paths
    for v in folders.values():
        p = v.get("path") if isinstance(v, dict) else v  # new format: dict, old: "1" "/path"
        if isinstance(p, str) and p.startswith("/"):
            paths.append(Path(p))
    seen: set[Path] = set()
    unique = []
    for p in paths:
        r = p.resolve()
        if r not in seen:
            seen.add(r)
            unique.append(p)
    return unique


def list_games(steam_root: Path) -> list[dict[str, Any]]:
    games: dict[int, str] = {}
    for lib in library_paths(steam_root):
        for mf in sorted((lib / "steamapps").glob("appmanifest_*.acf")):
            try:
                app = _root_block(mf)
                appid = int(app["appid"])
                name = app["name"]
            except (OSError, ValueError, KeyError, TypeError):
                continue  # malformed manifests are skipped, never fatal
            if isinstance(name, str) and name and not name.startswith(TOOL_PREFIXES):
                games[appid] = name
    return sorted(({"appid": a, "name": n} for a, n in games.items()), key=lambda g: g["name"].lower())


def app_paths(steam_root: Path, appid: int) -> Optional[dict[str, str]]:
    """Token context for one game: its Proton prefix and install folder, in whichever library holds it."""
    for lib in library_paths(steam_root):
        mf = lib / "steamapps" / f"appmanifest_{appid}.acf"
        try:
            installdir = _root_block(mf)["installdir"]
        except (OSError, ValueError, KeyError):
            continue
        if not isinstance(installdir, str) or not installdir or "/" in installdir or installdir in (".", ".."):
            return None
        return {"prefix": str(lib / "steamapps/compatdata" / str(appid) / "pfx"),
                "install_dir": str(lib / "steamapps/common" / installdir),
                "appid": str(appid)}
    return None
