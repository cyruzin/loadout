"""Decky runs plugins on its own PyInstaller-frozen Python, which only ships the stdlib modules
decky_loader itself uses. `xml.etree` was missing on a real device (ModuleNotFoundError at load),
so the backend may only import modules known to be present there."""
import ast
import shlex
from pathlib import Path

import pytest

from loadout import launch

ROOT = Path(__file__).resolve().parent.parent
# Imported by decky_loader itself (backend/*.py), so guaranteed in the frozen build.
DECKY_STDLIB = {"__future__", "codecs", "json", "os", "pathlib", "re", "stat", "sys", "typing"}


def _imports(path):
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            yield from (a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            yield node.module.split(".")[0]


@pytest.mark.parametrize("path", sorted((ROOT / "py_modules/loadout").glob("*.py")) + [ROOT / "main.py"],
                         ids=lambda p: p.name)
def test_backend_only_imports_modules_present_in_decky(path):
    allowed = DECKY_STDLIB | {"decky", "loadout"}
    assert set(_imports(path)) <= allowed, f"{path.name}: {set(_imports(path)) - allowed}"


@pytest.mark.parametrize("s", ["", "40", "a b", "a;rm -rf ~", "$(reboot)", "'quote\"", "`id`", "x=y,z:1/2",
                               "ção", "\t", "it's"])
def test_quote_matches_shlex(s):
    assert launch.quote(s) == shlex.quote(s)
