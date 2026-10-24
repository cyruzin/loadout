"""Marker-delimited block inside Steam launch options.

    LOADOUT_BEGIN=1 DXVK_FRAME_RATE=40 LOADOUT_END=1 <user's own text>

The markers are plain env assignments, so the line stays valid shell.
"""
from __future__ import annotations

import re
import shlex
from typing import Optional

BEGIN = "LOADOUT_BEGIN=1"
END = "LOADOUT_END=1"
_BLOCK = re.compile(r"LOADOUT_BEGIN=1 (?:.*? )?LOADOUT_END=1 ?")


def build(base: str, env: dict[str, str]) -> str:
    """Prepend the managed block to the user's launch options (`base`, block-free)."""
    if not env:
        return base
    assigns = " ".join(f"{k}={shlex.quote(v)}" for k, v in env.items())
    rest = base.strip()
    if "%command%" not in rest:
        # Plain args like "-novid" are appended by Steam; with %command% they must follow it.
        rest = f"%command% {rest}".strip()
    return f"{BEGIN} {assigns} {END} {rest}"


def strip(current: str) -> Optional[str]:
    """Remove the managed block. None when the markers are corrupted."""
    if BEGIN not in current and END not in current:
        return current
    new, n = _BLOCK.subn("", current, count=1)
    if n != 1 or BEGIN in new or END in new:
        return None
    return new


def restore(current: str, written: Optional[str], original: Optional[str]) -> tuple[str, Optional[str]]:
    """Return (block-free launch options, warning).

    Untouched since we wrote it -> the exact original string. Edited by the user
    -> strip only our block and keep their edits. Corrupted markers -> leave as is.
    """
    if written is not None and original is not None and current == written:
        return original, None
    stripped = strip(current)
    if stripped is None:
        return current, ("Launch options were edited by hand and the Loadout block could not be "
                         "removed safely. Check them in the game's properties.")
    return stripped, None
