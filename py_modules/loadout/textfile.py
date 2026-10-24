"""Decode/encode config files so they can be written back byte-for-byte in their own encoding."""
from __future__ import annotations

import codecs
import re

# Values Loadout may write into any config file: plain words and numbers, nothing that could
# change the file's structure (no <, >, &, =, ;, quotes or newlines).
VALUE = re.compile(r"^[A-Za-z0-9_. -]{0,64}$")


def decode(raw: bytes, what: str) -> tuple[str, str]:
    """(text, codec). UTF-8 or UTF-16, with or without BOM."""
    try:
        if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
            return raw.decode("utf-16"), "utf-16"
        if raw.startswith(codecs.BOM_UTF8):
            return raw.decode("utf-8-sig"), "utf-8-sig"
        # UTF-16 without a BOM (ELDEN RING's XML): one byte of the first ASCII character is NUL.
        # Decoding it as UTF-8 "works" (NUL is valid) but nothing would ever match.
        if len(raw) >= 2 and raw[0] != 0 and raw[1] == 0:
            return raw.decode("utf-16-le"), "utf-16-le"
        if len(raw) >= 2 and raw[0] == 0 and raw[1] != 0:
            return raw.decode("utf-16-be"), "utf-16-be"
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        raise ValueError(f"malformed {what}: bad encoding") from None


def encode(text: str, codec: str, original: bytes) -> bytes:
    out = text.encode(codec)
    if codec == "utf-16" and not original.startswith(out[:2]):
        out = codecs.BOM_UTF16_BE + text.encode("utf-16-be")  # keep the original byte order
    return out
