"""Device table, DMI detection and the level fallback chain."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from .validate import validate_device_doc

DATA_DIR = Path(__file__).parent / "data" / "devices"
GENERIC = "generic"


def load_devices(directory: Path = DATA_DIR) -> dict[str, dict[str, Any]]:
    out = {}
    for f in sorted(directory.glob("*.json")):
        doc = validate_device_doc(json.loads(f.read_text(encoding="utf-8")))
        out[doc["device"]] = doc
    if GENERIC not in out:
        raise ValueError("generic device table missing")
    return out


def read_dmi(root: Path = Path("/sys/class/dmi/id")) -> str:
    """product_name only: a plain read, no privileges."""
    try:
        return (root / "product_name").read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


# Built-in panels; anything else connected (HDMI, DP, USB-C) is an external display.
_INTERNAL = ("eDP", "LVDS", "DSI")
_MODE = re.compile(r"^([1-9][0-9]{2,4})x([1-9][0-9]{2,4})")


def read_display(root: Path = Path("/sys/class/drm")) -> Optional[tuple[str, bool]]:
    """("WIDTHxHEIGHT", external) of the screen in use: a connected external display wins over the
    built-in panel (docked). Plain sysfs reads; the first listed mode is the preferred one."""
    found: dict[bool, str] = {}
    for conn in sorted(root.glob("card*-*")):
        try:
            if (conn / "status").read_text().strip() != "connected":
                continue
            m = _MODE.match((conn / "modes").read_text().split("\n", 1)[0])
        except OSError:
            continue
        external = not any(t in conn.name for t in _INTERNAL)
        if m and external not in found:
            found[external] = f"{m.group(1)}x{m.group(2)}"
    for external in (True, False):
        if external in found:
            return found[external], external
    return None


def clamp_resolution(resolution: Optional[str], native: str) -> str:
    """The game's resolution class: its own pick, never above the screen's native height."""
    native_class = native.split("x")[1] + "p"
    if resolution is None or int(resolution.rstrip("p")) > int(native_class.rstrip("p")):
        return native_class
    return resolution


def detect(devices: dict[str, dict[str, Any]], product_name: str) -> Optional[str]:
    """Substring match: some vendors append per-unit suffixes (e.g. "ROG Ally RC71L_Action")."""
    for dev_id, doc in devices.items():
        if any(m in product_name for m in doc["match"]):
            return dev_id
    return None


def native_class(doc: dict[str, Any]) -> str:
    return doc["native"].split("x")[1] + "p"


def resolution_size(resolution: str, native: str) -> tuple[int, int]:
    """"720p" on a device whose panel is `native` ("1920x1080") -> (1280, 720): the panel's aspect
    ratio at that height, width rounded to an even number (16:10 Deck: 720p -> 1152x720)."""
    nw, nh = (int(n) for n in native.split("x"))
    height = int(resolution.rstrip("p"))
    return 2 * round(height * nw / nh / 2), height


def resolve_level(devices: dict[str, dict[str, Any]], device_id: Optional[str],
                  profile: str, resolution: str) -> tuple[dict[str, Any], bool]:
    """(level, approximate). Chain: device+resolution, device any, generic+resolution, generic any."""
    # No GPU-based device "class" step; add it when a second handheld family ships.
    dev = devices.get(device_id or "") or devices[GENERIC]
    gen = devices[GENERIC]
    for i, (doc, res) in enumerate(((dev, resolution), (dev, "any"), (gen, resolution), (gen, "any"))):
        level = doc["levels"].get(profile, {}).get(res)
        if level is not None:
            # "any" on the user's own device is deliberate data, not a guess.
            return level, device_id not in devices or i >= 2
    return {}, True
