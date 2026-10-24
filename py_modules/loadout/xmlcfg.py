"""Flat XML config files (<Key>value</Key>), edited in place.

Only the text between the tags changes; every other byte (BOM, encoding, CRLF, comments)
is kept, which a parse-and-reserialize round trip would not guarantee.
"""
from __future__ import annotations

import codecs
import re
import xml.etree.ElementTree as ET

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


def _parse(raw: bytes) -> str:
    try:
        ET.fromstring(raw)
    except ET.ParseError as e:
        raise ValueError(f"malformed XML: {e}") from None
    return _decode(raw)[0]


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
