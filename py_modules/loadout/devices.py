"""Device table, DMI detection and the level fallback chain."""
from __future__ import annotations

import json
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


def detect(devices: dict[str, dict[str, Any]], product_name: str) -> Optional[str]:
    """Substring match: some vendors append per-unit suffixes (e.g. "ROG Ally RC71L_Action")."""
    for dev_id, doc in devices.items():
        if any(m in product_name for m in doc["match"]):
            return dev_id
    return None


def native_class(doc: dict[str, Any]) -> str:
    return doc["native"].split("x")[1] + "p"


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
