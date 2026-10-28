"""INI config files (e.g. Unreal Engine's GameUserSettings.ini), edited in place.

Keys are written "[Section]Key" because both parts can contain dots and slashes
("[/Script/ProjectP.LGameUserSettings]FSR3Mode", "[ScalabilityGroups]sg.ShadowQuality").
Keys before any section header are written "[]Key": CryEngine's game.cfg (Crysis 3 Remastered)
has no sections and "--" comments. Only the value after "=" changes; every other byte (encoding,
CRLF, comments, order) is kept.

Some games omit a key that's at its default (The Witcher 3's dx12user.settings: each preset has its
own set of [Rendering] keys), so a key can be absent: reading it gives None, setting None removes its
line, and setting an absent key adds "Key=value" after the last line of its section. The section
must already be in the file: a new one is refused. A section whose only key is at its default goes
too (The Witcher 3: [Rendering/DRS], [Streaming/Textures]): entries leave such keys out.
"""
from __future__ import annotations

import re
from typing import Optional

from .textfile import VALUE, decode, encode

KEY = re.compile(r"^\[([A-Za-z0-9_./ -]{0,100})\]([A-Za-z0-9_.]{1,64})$")
COMMENTS = (";", "#", "--")
_LINE = re.compile(r"^(?P<key>[^=;#\[\s][^=]*?)(?P<sep>\s*=\s*)(?P<value>[^\r\n]*?)(?P<end>[ \t]*\r?\n?)$")


def _lines(raw: bytes) -> tuple[list[str], str]:
    text, codec = decode(raw, "INI")
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        s = line.strip()
        if not s or s.startswith(COMMENTS) or (s.startswith("[") and s.endswith("]")) or _LINE.match(line):
            continue
        raise ValueError(f"malformed INI: line {i + 1}")
    return lines, codec


def _find(lines: list[str], key: str) -> tuple[Optional[tuple[int, re.Match[str]]], Optional[int]]:
    """(the line holding `key` or None if absent, the last non-blank line of its section or None if
    the section isn't in the file). Duplicated keys (UE repeats some) are refused."""
    k = KEY.match(key)
    if k is None:
        raise ValueError(f"invalid key: {key!r}")
    section, name = k.groups()
    current = ""  # keys before the first header
    hits = []
    last = -1 if section == "" else None  # sectionless keys go first, even with none there yet
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            current = s[1:-1]
            if current == section:
                last = i
            continue
        if current == section and s:
            last = i
        m = None if s.startswith(COMMENTS) else _LINE.match(line)
        if m and current == section and m.group("key") == name:
            hits.append((i, m))
    if len(hits) > 1:
        raise ValueError(f"key {key!r} appears more than once")
    return (hits[0] if hits else None), last


def read_values(raw: bytes, keys: list[str]) -> dict[str, Optional[str]]:
    lines, _ = _lines(raw)
    out: dict[str, Optional[str]] = {}
    for k in keys:
        hit, _ = _find(lines, k)
        out[k] = hit[1].group("value") if hit else None
    return out


def set_values(raw: bytes, values: dict[str, Optional[str]]) -> bytes:
    lines, codec = _lines(raw)
    newline = next((ln[len(ln.rstrip("\r\n")):] for ln in lines if ln.endswith("\n")), "\n")
    for key, value in values.items():
        if value is not None and not VALUE.match(value):
            raise ValueError(f"invalid value for {key}")
        hit, last = _find(lines, key)
        if hit:
            i, m = hit
            if value is None:
                del lines[i]
            else:
                lines[i] = m.group("key") + m.group("sep") + value + m.group("end")
        elif value is not None:
            if last is None:
                raise ValueError(f"section of {key!r} not in the file")
            if last >= 0 and not lines[last].endswith("\n"):
                lines[last] += newline
            lines.insert(last + 1, KEY.match(key).group(2) + "=" + value + newline)
    return encode("".join(lines), codec, raw)
