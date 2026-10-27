"""INI config files (e.g. Unreal Engine's GameUserSettings.ini), edited in place.

Keys are written "[Section]Key" because both parts can contain dots and slashes
("[/Script/ProjectP.LGameUserSettings]FSR3Mode", "[ScalabilityGroups]sg.ShadowQuality").
Keys before any section header are written "[]Key": CryEngine's game.cfg (Crysis 3 Remastered)
has no sections and "--" comments. Only the value after "=" changes; every other byte (encoding,
CRLF, comments, order) is kept.
"""
from __future__ import annotations

import re

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


def _find(lines: list[str], key: str) -> tuple[int, re.Match[str]]:
    """The one line holding `key`; duplicates (UE repeats some keys) are refused."""
    k = KEY.match(key)
    if k is None:
        raise ValueError(f"invalid key: {key!r}")
    section, name = k.groups()
    current = ""  # keys before the first header
    hits = []
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            current = s[1:-1]
            continue
        m = None if s.startswith(COMMENTS) else _LINE.match(line)
        if m and current == section and m.group("key") == name:
            hits.append((i, m))
    if len(hits) != 1:
        raise ValueError(f"key {key!r} must appear exactly once")
    return hits[0]


def read_values(raw: bytes, keys: list[str]) -> dict[str, str]:
    lines, _ = _lines(raw)
    return {k: _find(lines, k)[1].group("value") for k in keys}


def set_values(raw: bytes, values: dict[str, str]) -> bytes:
    lines, codec = _lines(raw)
    for key, value in values.items():
        if not VALUE.match(value):
            raise ValueError(f"invalid value for {key}")
        i, m = _find(lines, key)
        lines[i] = m.group("key") + m.group("sep") + value + m.group("end")
    return encode("".join(lines), codec, raw)
