"""Larian .lsx settings (Baldur's Gate 3's graphicSettings.lsx), edited in place.

One <node id="ConfigEntry"> per setting, keyed by its MapKey:

    <node id="ConfigEntry">
        <attribute id="MapKey" type="FixedString" value="ShadowQuality"/>
        <attribute id="Type" type="int32" value="0"/>
        <attribute id="Value" type="int32" value="2"/>
    </node>

The game leaves a setting out while it's at its default (the highest level, TAA, upscaler off...),
so a key can be absent: reading it gives None, setting None removes its entry, and setting a
missing key adds an int32 entry in MapKey order, like the game writes them. Every other byte is kept.
"""
from __future__ import annotations

import re
from typing import Optional

from .textfile import VALUE, decode, encode
from .xmlcfg import check_well_formed

KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
INT = re.compile(r"^-?[0-9]{1,10}$")
_OPEN = '<node id="ConfigEntry">'
_ENTRY = re.compile(
    r'(?P<indent>[ \t]*)<node id="ConfigEntry">\s*'
    r'<attribute id="MapKey" type="FixedString" value="(?P<key>[A-Za-z0-9_]+)"/>\s*'
    r'<attribute id="Type" type="int32" value="(?P<type>[0-9]+)"/>\s*'
    r'<attribute id="Value" type="(?P<vtype>[A-Za-z0-9]+)" value="(?P<value>[^"<>&]*)"/>\s*'
    r'</node>(?:\r?\n)?')


def _entries(text: str) -> dict[str, re.Match[str]]:
    """Every ConfigEntry must have exactly this layout: anything else is refused, not guessed."""
    found = list(_ENTRY.finditer(text))
    if not found or len(found) != text.count(_OPEN):
        raise ValueError("unexpected .lsx layout")
    keys = [m["key"] for m in found]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicated MapKey")
    return {m["key"]: m for m in found}


def _parse(raw: bytes) -> str:
    text = decode(raw, "LSX")[0]
    check_well_formed(text)
    return text


def read_values(raw: bytes, keys: list[str]) -> dict[str, Optional[str]]:
    entries = _entries(_parse(raw))
    for k in keys:
        if not KEY.match(k):
            raise ValueError(f"invalid key: {k!r}")
    return {k: entries[k]["value"] if k in entries else None for k in keys}


def _set(text: str, key: str, value: Optional[str]) -> str:
    entries = _entries(text)
    m = entries.get(key)
    if value is None:
        return text if m is None else text[:m.start()] + text[m.end():]
    if not VALUE.match(value):
        raise ValueError(f"invalid value for {key}")
    if m is not None:
        return text[:m.start("value")] + value + text[m.end("value"):]
    # Only int32 settings are added (every one a profile sets is): a copy of an existing int32
    # entry, so indentation and line endings match the file.
    if not INT.match(value):
        raise ValueError(f"{key} is missing and only whole numbers can be added")
    tpl = next((e for e in entries.values() if e["vtype"] == "int32" and e["type"] == "0"), None)
    if tpl is None:
        raise ValueError("no int32 entry to copy")
    s = tpl.start()
    new = (text[s:tpl.start("key")] + key + text[tpl.end("key"):tpl.start("value")] + value
           + text[tpl.end("value"):tpl.end()])
    after = [e for k, e in entries.items() if k > key]
    at = min(e.start() for e in after) if after else max(e.end() for e in entries.values())
    return text[:at] + new + text[at:]


def set_values(raw: bytes, values: dict[str, Optional[str]]) -> bytes:
    text = _parse(raw)
    for key, value in values.items():
        if not KEY.match(key):
            raise ValueError(f"invalid key: {key!r}")
        text = _set(text, key, value)
    check_well_formed(text)
    return encode(text, decode(raw, "LSX")[1], raw)
