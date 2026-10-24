"""Flat XML config files (<Key>value</Key>), edited in place.

Only the text between the tags changes; every other byte (BOM, encoding, CRLF, comments)
is kept, which a parse-and-reserialize round trip would not guarantee.
"""
from __future__ import annotations

import codecs
import re

KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,63}$")
VALUE = re.compile(r"^[A-Za-z0-9_. -]{0,64}$")


def _decode(raw: bytes) -> tuple[str, str]:
    if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return raw.decode("utf-16"), "utf-16"
    if raw.startswith(codecs.BOM_UTF8):
        return raw.decode("utf-8-sig"), "utf-8-sig"
    return raw.decode("utf-8"), "utf-8"


def _element(text: str, key: str) -> re.Match[str]:
    if not KEY.match(key):
        raise ValueError(f"invalid key: {key!r}")
    k = re.escape(key)
    if len(re.findall(rf"<{k}[\s/>]", text)) != 1:
        raise ValueError(f"key {key!r} must appear exactly once")
    m = re.search(rf"<{k}>([^<]*)</{k}>", text)
    if m is None:
        raise ValueError(f"key {key!r} is not a simple text element")
    return m


_SPECIAL = re.compile(r"<\?.*?\?>|<!--.*?-->|<!\[CDATA\[.*?\]\]>|<!DOCTYPE[^>]*>", re.S)
_TAG = re.compile(r"<(/?)([A-Za-z_][\w.:-]*)(?:\s[^<>]*?)?(/?)>")


def check_well_formed(text: str) -> None:
    """Balanced tags, one root, no stray '<'. Stand-in for a real parser: xml.etree isn't in
    Decky's frozen Python. Enough to reject truncated or corrupted config files."""
    body = _SPECIAL.sub("", text)
    stack: list[str] = []
    roots = pos = 0
    for m in _TAG.finditer(body):
        between = body[pos:m.start()]
        if "<" in between or (not stack and between.strip()):
            raise ValueError("malformed XML: unexpected text or '<'")
        closing, name, self_closing = m.groups()
        if closing:
            if self_closing or not stack or stack.pop() != name:
                raise ValueError(f"malformed XML: unexpected </{name}>")
        else:
            roots += not stack
            if not self_closing:
                stack.append(name)
        pos = m.end()
    if stack or roots != 1 or body[pos:].strip():
        raise ValueError("malformed XML: unclosed tags or not exactly one root")


def _parse(raw: bytes) -> str:
    try:
        text = _decode(raw)[0]
    except UnicodeDecodeError:
        raise ValueError("malformed XML: bad encoding") from None
    check_well_formed(text)
    return text


def read_values(raw: bytes, keys: list[str]) -> dict[str, str]:
    text = _parse(raw)
    return {k: _element(text, k).group(1) for k in keys}


def set_values(raw: bytes, values: dict[str, str]) -> bytes:
    text = _parse(raw)
    codec = _decode(raw)[1]
    for key, value in values.items():
        if not VALUE.match(value):
            raise ValueError(f"invalid value for {key}")
        m = _element(text, key)
        text = text[:m.start(1)] + value + text[m.end(1):]
    out = text.encode(codec)
    if codec == "utf-16" and not raw.startswith(out[:2]):
        out = codecs.BOM_UTF16_BE + text.encode("utf-16-be")  # keep the original byte order
    return out
