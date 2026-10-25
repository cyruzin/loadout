"""Marker-delimited block inside Steam launch options.

    LOADOUT_BEGIN=1 DXVK_FRAME_RATE=40 LOADOUT_END=1 <user's own text>

The markers are plain env assignments, so the line stays valid shell. Game arguments must follow
%command%, outside the block, so the block records them in LOADOUT_ARGS: strip() can then remove
them without any stored state.

    LOADOUT_BEGIN=1 LOADOUT_ARGS=--launcher-skip LOADOUT_END=1 %command% --launcher-skip -novid
"""
from __future__ import annotations

import re
from typing import Optional

BEGIN = "LOADOUT_BEGIN=1"
END = "LOADOUT_END=1"
_BLOCK = re.compile(r"LOADOUT_BEGIN=1 (?:.*? )?LOADOUT_END=1 ?")
_ARGS = re.compile(r"(?:^| )LOADOUT_ARGS=('[^']*'|\S+)")
_UNSAFE = re.compile(r"[^\w@%+=:,./-]", re.ASCII)


def quote(s: str) -> str:
    """Same as shlex.quote (shlex isn't in Decky's frozen Python)."""
    if not s:
        return "''"
    if _UNSAFE.search(s) is None:
        return s
    return "'" + s.replace("'", "'\"'\"'") + "'"


def build(base: str, env: dict[str, str], args: tuple[str, ...] = ()) -> str:
    """Prepend the managed block to the user's launch options (`base`, block-free) and put `args`
    (validated: no spaces or shell characters) right after %command%."""
    if not env and not args:
        return base
    assigns = [f"{k}={quote(v)}" for k, v in env.items()]
    rest = base.strip()
    if "%command%" not in rest:
        # Plain args like "-novid" are appended by Steam; with %command% they must follow it.
        rest = f"%command% {rest}".strip()
    if args:
        joined = " ".join(args)
        assigns.append(f"LOADOUT_ARGS={quote(joined)}")
        rest = rest.replace("%command%", f"%command% {joined}", 1)
    return f"{BEGIN} {' '.join(assigns)} {END} {rest}"


def strip(current: str) -> Optional[str]:
    """Remove the managed block. None when the markers are corrupted."""
    if BEGIN not in current and END not in current:
        return current
    block = _BLOCK.search(current)
    new, n = _BLOCK.subn("", current, count=1)
    if n != 1 or BEGIN in new or END in new:
        return None
    m = _ARGS.search(block.group(0)) if block else None
    if m:
        joined = m.group(1).strip("'")
        new = new.replace(f"%command% {joined}", "%command%", 1)
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
