#!/usr/bin/env python3
"""Shows which config keys a game changes when you change its settings, as a draft entry.

Run it on the device, with the game closed (launch it once before, so its config exists):

    python3 scripts/capture.py <appid> > draft.json

It snapshots the game's Proton prefix and install folder and asks for a label for the current
settings. Then, each round: change the settings in the game, quit it (many games only write on
exit), type a label for what you picked (e.g. low) and press Enter. An empty label ends.

The draft (stdout) has every key that changed and Loadout can set, in the entry's own syntax:
`options` with the values seen, in snapshot order (reorder them lowest to highest), and
`snapshots` with each round's values, ready for a profile's `files`. Notes go to stderr: files
that changed but can't be set (binary saves, registry, caches), keys with values Loadout won't
write. It only shows what the game writes, not what it reads: check that in the game
(CONTRIBUTING.md, section 2).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "py_modules"))

from loadout import inicfg, jsoncfg, steam, xmlcfg  # noqa: E402
from loadout.textfile import VALUE, decode  # noqa: E402

MAX_SIZE = 1 << 20  # config files are small; paks and saves are only stat'ed
PARSERS = {"xml": xmlcfg, "json": jsoncfg, "ini": inicfg}
FORMATS = {".xml": ["xml"], ".json": ["json"], ".ini": ["ini"], ".cfg": ["json", "xml", "ini"],
           ".config": ["json", "xml", "ini"]}
LABEL = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
_XML_ELEMENT = re.compile(r"<([A-Za-z_][A-Za-z0-9_.-]{0,63})>[^<]*</\1>")
_JSON_NAME = re.compile(r"^[A-Za-z0-9_]{1,64}$")
_JSON_PICK = re.compile(r"^[A-Za-z0-9_./ -]{1,100}$")


def ini_keys(raw: bytes) -> list[str]:
    inicfg.read_values(raw, [])  # raises unless the whole file is valid INI
    section, keys = "", []  # keys before the first header are "[]Key"
    for line in decode(raw, "INI")[0].splitlines():
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            section = s[1:-1]
        elif "=" in s and not s.startswith(inicfg.COMMENTS):
            keys.append(f"[{section}]{s.split('=', 1)[0].strip()}")
    return [k for k in keys if inicfg.KEY.match(k)]


def xml_keys(raw: bytes) -> list[str]:
    xmlcfg.read_values(raw, [])
    return _XML_ELEMENT.findall(decode(raw, "XML")[0])


def _selector(items: list) -> str | None:
    """A field whose value tells the objects of an array apart (Cyberpunk: name, group_name)."""
    if not items or not all(isinstance(e, dict) for e in items):
        return None
    for field in items[0]:
        picks = [e.get(field) for e in items]
        if (_JSON_NAME.match(field) and len(set(map(str, picks))) == len(picks)
                and all(isinstance(p, str) and _JSON_PICK.match(p) for p in picks)):
            return field
    return None


def _json_paths(node: object, path: str, out: list[str]) -> None:
    if not isinstance(node, dict):
        return
    for name, v in node.items():
        if not _JSON_NAME.match(name):
            continue
        p = f"{path}/{name}"
        if isinstance(v, list):
            field = _selector(v)
            for e in v if field else []:
                _json_paths(e, f"{p}[{field}={e[field]}]", out)
        elif isinstance(v, dict):
            _json_paths(v, p, out)
        elif v is not None:
            out.append(p)


def json_keys(raw: bytes) -> list[str]:
    jsoncfg.read_values(raw, [])
    out: list[str] = []
    _json_paths(json.loads(decode(raw, "JSON")[0]), "", out)
    return [k for k in out if jsoncfg.KEY.match(k)]


KEYS = {"xml": xml_keys, "json": json_keys, "ini": ini_keys}


def parse(raw: bytes, suffix: str) -> tuple[str | None, dict[str, str]]:
    """(format, {key: value}) for every key the plugin could set, or (None, {})."""
    for fmt in FORMATS.get(suffix, []):
        try:
            keys = list(dict.fromkeys(KEYS[fmt](raw)))
        except ValueError:
            continue
        try:
            return fmt, PARSERS[fmt].read_values(raw, keys)
        except ValueError:  # e.g. a duplicated INI key: drop the keys that can't be read
            values = {}
            for k in keys:
                try:
                    values.update(PARSERS[fmt].read_values(raw, [k]))
                except ValueError:
                    pass
            return fmt, values
    return None, {}


def snapshot(roots: list[Path], skip: set[Path] = frozenset()) -> dict[str, tuple]:
    """{path: (fingerprint, bytes or None)}. Keys are only parsed later, for files that changed:
    parsing every JSON of a big game (Cyberpunk: launcher locales, save metadata) takes ~30 s.
    Symlinks aren't followed."""
    out = {}
    for root in roots:
        for d, dirs, names in os.walk(root):
            dirs[:] = [x for x in dirs if Path(d, x) not in skip]
            for n in names:
                p = os.path.join(d, n)
                try:
                    st = os.lstat(p)
                    if not stat.S_ISREG(st.st_mode):
                        continue
                    if Path(n).suffix.lower() not in FORMATS or st.st_size > MAX_SIZE:
                        out[p] = ((st.st_size, st.st_mtime_ns), None)
                        continue
                    with open(p, "rb") as f:
                        raw = f.read()
                except OSError:
                    continue  # vanished or unreadable mid-scan
                out[p] = (hashlib.sha256(raw).hexdigest(), raw)
    return out


def token_path(path: str, ctx: dict[str, str]) -> str:
    for t in ("prefix", "install_dir"):
        if path.startswith(ctx[t] + "/"):
            return "{" + t + "}" + path[len(ctx[t]):]
    return path


def build_draft(snaps: list[tuple[str, dict]], ctx: dict[str, str]) -> tuple[dict, list[str]]:
    options: dict[str, dict[str, list[str]]] = {}
    rounds: dict[str, list] = {label: [] for label, _ in snaps}
    notes, unsupported = [], []
    for p in sorted(set().union(*(s for _, s in snaps))):
        seen = [(label, s.get(p)) for label, s in snaps]
        if len({e[0] if e else None for _, e in seen}) == 1:
            continue  # same bytes (or same size and mtime) in every snapshot
        name = token_path(p, ctx)
        suffix = Path(p).suffix.lower()
        parsed = [(label, *parse(e[1], suffix)) for label, e in seen if e and e[1] is not None]
        parsed = [x for x in parsed if x[1]]
        if not parsed:
            if not name.endswith(".log"):  # games log every launch
                unsupported.append(name)
            continue
        fmt = parsed[0][1]
        keys = sorted(set().union(*(v for _, _, v in parsed)))
        changed = [k for k in keys if len({v.get(k) for _, _, v in parsed}) > 1]
        bad = [k for k in changed if not all(VALUE.match(v.get(k, "")) for _, _, v in parsed)]
        for k in bad:
            notes.append(f"Loadout won't write this value: {name} {k}")
        changed = [k for k in changed if k not in bad]
        if not changed:
            notes.append(f"changed, but no key Loadout can set differs: {name}")
            continue
        options[name] = {k: list(dict.fromkeys(v[k] for _, _, v in parsed if k in v)) for k in changed}
        for label, _, v in parsed:
            rounds[label].append({"path": name, "format": fmt,
                                  "set": {k: v[k] for k in changed if k in v}})
    for name in unsupported[:30]:
        notes.append(f"changed, not a config file Loadout reads (save, registry, cache?): {name}")
    if len(unsupported) > 30:
        notes.append(f"... and {len(unsupported) - 30} more changed files")
    return {"options": options, "snapshots": rounds}, notes


def ask(prompt: str, used: set[str]) -> str:
    while True:
        print(prompt, end="", file=sys.stderr, flush=True)
        label = sys.stdin.readline().strip()
        if not label or (LABEL.match(label) and label not in used):
            return label
        print("Up to 32 letters, digits, - or _, not used yet.", file=sys.stderr)


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not argv[1].isdigit():
        print(__doc__, file=sys.stderr)
        return 2
    root = steam.find_steam_root(Path.home())
    ctx = steam.app_paths(root, int(argv[1])) if root else None
    if ctx is None:
        print(f"app {argv[1]} isn't installed in any Steam library", file=sys.stderr)
        return 1
    roots = [Path(ctx["prefix"]), Path(ctx["install_dir"])]
    # Wine's and Proton's own files (Proton refreshes its Steam/VR stubs on every launch)
    skip = {roots[0] / d for d in ("drive_c/windows", "drive_c/Program Files (x86)/Steam", "drive_c/vrclient")}
    snaps: list[tuple[str, dict]] = []
    prompt = "Game closed. Label for its current settings (e.g. original), empty to quit: "
    while label := ask(prompt, {lb for lb, _ in snaps}):
        snaps.append((label, snapshot(roots, skip)))
        print(f"  {len(snaps[-1][1])} files", file=sys.stderr)
        prompt = "Change settings in the game, quit it, then a label (e.g. low), empty to finish: "
    if len(snaps) < 2:
        print("need at least two snapshots to compare", file=sys.stderr)
        return 1
    draft, notes = build_draft(snaps, ctx)
    for n in notes:
        print(n, file=sys.stderr)
    print(json.dumps({"appid": int(argv[1]), **draft}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
