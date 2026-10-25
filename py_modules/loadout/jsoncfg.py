"""JSON config files (e.g. Cyberpunk 2077's UserSettings.json), edited in place.

Keys are paths of object members, each starting with "/". A member that is an array of objects
can pick its one element whose field equals a value: "name[field=value]". Cyberpunk keeps
settings as {"data": [{"group_name": ..., "options": [{"name": ..., "value": ...}]}]}, so:

    /data[group_name=/graphics/advanced]/options[name=AmbientOcclusion]/value

Only the value token changes, and it keeps its JSON type (string, number or true/false);
every other byte (indentation, order, missing final newline) is kept.
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterator

from .textfile import VALUE, decode, encode

_SEG = r"/([A-Za-z0-9_]{1,64})(?:\[([A-Za-z0-9_]{1,64})=([A-Za-z0-9_./ -]{1,100})\])?"
KEY = re.compile(rf"^(?:{_SEG}){{1,8}}$")
_SEGS = re.compile(_SEG)
_WS = re.compile(r"[ \t\r\n]*")
_NUMBER = re.compile(r"^-?(?:0|[1-9][0-9]{0,15})(?:\.[0-9]{1,16})?$")
_scan = json.JSONDecoder().scan_once


def _ws(text: str, i: int) -> int:
    return _WS.match(text, i).end()


def _members(text: str, i: int) -> Iterator[tuple[str, int, int]]:
    """(name, start, end) of each member of the object at `i`."""
    i = _ws(text, i + 1)
    if text[i] == "}":
        return
    while True:
        name, i = json.decoder.scanstring(text, i + 1)
        i = _ws(text, _ws(text, i) + 1)  # past ":"
        _, end = _scan(text, i)
        yield name, i, end
        i = _ws(text, end)
        if text[i] == "}":
            return
        i = _ws(text, i + 1)


def _elements(text: str, i: int) -> Iterator[tuple[Any, int, int]]:
    """(value, start, end) of each element of the array at `i`."""
    i = _ws(text, i + 1)
    if text[i] == "]":
        return
    while True:
        value, end = _scan(text, i)
        yield value, i, end
        i = _ws(text, end)
        if text[i] == "]":
            return
        i = _ws(text, i + 1)


def _parse(raw: bytes) -> tuple[str, str]:
    text, codec = decode(raw, "JSON")
    try:
        json.loads(text)
    except ValueError:
        raise ValueError("malformed JSON") from None
    return text, codec


def _find(text: str, key: str) -> tuple[int, int]:
    """Span of the one plain value (string, number, true/false) at `key`."""
    if not KEY.match(key):
        raise ValueError(f"invalid key: {key!r}")
    i, end = _ws(text, 0), len(text)
    for name, field, want in _SEGS.findall(key):
        hits = [(s, e) for n, s, e in _members(text, i) if n == name] if text[i] == "{" else []
        if field and len(hits) == 1 and text[hits[0][0]] == "[":
            hits = [(s, e) for v, s, e in _elements(text, hits[0][0])
                    if isinstance(v, dict) and v.get(field) == want]
        elif field:
            hits = []
        if len(hits) != 1:
            raise ValueError(f"key {key!r} must appear exactly once")
        i, end = hits[0]
    if text[i] in "{[n":
        raise ValueError(f"key {key!r} is not a plain value")
    return i, end


def _value(token: str) -> str:
    return json.loads(token) if token.startswith('"') else token


def read_values(raw: bytes, keys: list[str]) -> dict[str, str]:
    text, _ = _parse(raw)
    out = {}
    for k in keys:
        s, e = _find(text, k)
        out[k] = _value(text[s:e])
    return out


def set_values(raw: bytes, values: dict[str, str]) -> bytes:
    text, codec = _parse(raw)
    edits = []
    for key, value in values.items():
        if not VALUE.match(value):
            raise ValueError(f"invalid value for {key}")
        s, e = _find(text, key)
        old = text[s:e]
        if old.startswith('"'):
            new = f'"{value}"'  # VALUE has no quotes, backslashes or control characters
        elif old in ("true", "false"):
            if value not in ("true", "false"):
                raise ValueError(f"{key} expects true or false")
            new = value
        elif _NUMBER.match(value):
            new = value
        else:
            raise ValueError(f"{key} expects a number")
        edits.append((s, e, new))
    edits.sort(reverse=True)
    for (s, e, new), nxt in zip(edits, edits[1:] + [None]):
        if nxt is not None and nxt[1] > s:
            raise ValueError("two keys point at the same value")
        text = text[:s] + new + text[e:]
    return encode(text, codec, raw)
