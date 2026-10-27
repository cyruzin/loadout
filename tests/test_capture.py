import codecs
import importlib.util
import os
from pathlib import Path

from loadout import inicfg, jsoncfg, xmlcfg

_spec = importlib.util.spec_from_file_location(
    "capture", Path(__file__).resolve().parent.parent / "scripts/capture.py")
capture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(capture)

INI = b"[ScalabilityGroups]\r\nsg.ShadowQuality=3\r\nsg.TextureQuality=3\r\n[/Script/Engine.GameUserSettings]\r\nLastConfirmedFullscreenMode=1\r\n"
JSON = (b'{"version": 3, "data": [{"group_name": "/graphics/advanced", "options": ['
        b'{"name": "AmbientOcclusion", "type": "List", "value": "High", "index": 3},'
        b'{"name": "Flag", "type": "Bool", "value": true, "default": null}]}]}')
XML = "<config>\r\n<MotionBlur>HIGH</MotionBlur>\r\n<ScreenMode>FULLSCREEN</ScreenMode>\r\n</config>\r\n"


def _game(tmp_path):
    ctx = {"prefix": str(tmp_path / "pfx"), "install_dir": str(tmp_path / "game"), "appid": "1"}
    cfg = tmp_path / "pfx/drive_c/users/steamuser/AppData/Local/G"
    cfg.mkdir(parents=True)
    (tmp_path / "game").mkdir()
    return ctx, cfg


def _snap(ctx):
    return capture.snapshot([Path(ctx["prefix"]), Path(ctx["install_dir"])])


def test_keys_found_are_readable_by_the_plugin():
    ini, js = capture.ini_keys(INI), capture.json_keys(JSON)
    assert "[ScalabilityGroups]sg.ShadowQuality" in ini
    assert "/data[group_name=/graphics/advanced]/options[name=AmbientOcclusion]/index" in js
    assert not any(k.endswith("/default") for k in js)  # null can't be set
    inicfg.read_values(INI, ini)
    jsoncfg.read_values(JSON, js)
    xml = codecs.BOM_UTF8 + XML.encode()
    xmlcfg.read_values(xml, capture.xml_keys(xml))


def test_utf16_xml_without_bom_is_parsed():
    fmt, values = capture.parse(XML.encode("utf-16-le"), ".xml")
    assert fmt == "xml" and values == {"MotionBlur": "HIGH", "ScreenMode": "FULLSCREEN"}


def test_cfg_tries_each_format_and_junk_is_none():
    assert capture.parse(INI, ".cfg")[0] == "ini"
    crysis = b"-- [Game-Configuration]\r\n\r\nsys_spec = 3\r\nsys_spec_Shadows = 1\r\n"
    assert capture.parse(crysis, ".cfg") == ("ini", {"[]sys_spec": "3", "[]sys_spec_Shadows": "1"})
    assert capture.parse(b"\x00\xff\x13 not a config", ".cfg") == (None, {})
    assert capture.parse(b"<a><b>1</a>", ".xml") == (None, {})


def test_duplicate_ini_key_is_dropped_not_fatal():
    fmt, values = capture.parse(b"[S]\nA=1\nA=2\nB=3\n", ".ini")
    assert fmt == "ini" and values == {"[S]B": "3"}


def test_unsafe_json_names_and_selectors_are_skipped():
    raw = (b'{"a/b": 1, "ok": 1, "list": [{"name": "x]y", "v": 1}, {"name": "z", "v": 2}],'
           b'"same": [{"n": "a", "v": 1}, {"n": "a", "v": 2}]}')
    assert capture.json_keys(raw) == ["/ok"]


def test_draft_lists_changed_keys_in_entry_syntax(tmp_path):
    ctx, cfg = _game(tmp_path)
    (cfg / "GameUserSettings.ini").write_bytes(INI)
    (cfg / "UserSettings.json").write_bytes(JSON)
    (cfg / "Untouched.ini").write_bytes(b"[S]\nA=1\n")
    (cfg / "Options.sav").write_bytes(b"\x00\x01")
    (cfg / "Game.log").write_bytes(b"start")
    before = _snap(ctx)
    (cfg / "GameUserSettings.ini").write_bytes(INI.replace(b"ShadowQuality=3", b"ShadowQuality=0"))
    (cfg / "UserSettings.json").write_bytes(JSON.replace(b'"High", "index": 3', b'"Low", "index": 1'))
    (cfg / "Options.sav").write_bytes(b"\x00\x02\x03")
    (cfg / "Game.log").write_bytes(b"start again")
    draft, notes = capture.build_draft([("high", before), ("low", _snap(ctx))], ctx)

    ini = "{prefix}/drive_c/users/steamuser/AppData/Local/G/GameUserSettings.ini"
    js = "{prefix}/drive_c/users/steamuser/AppData/Local/G/UserSettings.json"
    opt = "/data[group_name=/graphics/advanced]/options[name=AmbientOcclusion]"
    assert draft["options"] == {ini: {"[ScalabilityGroups]sg.ShadowQuality": ["3", "0"]},
                                js: {f"{opt}/index": ["3", "1"], f"{opt}/value": ["High", "Low"]}}
    assert draft["snapshots"]["low"] == [
        {"path": ini, "format": "ini", "set": {"[ScalabilityGroups]sg.ShadowQuality": "0"}},
        {"path": js, "format": "json", "set": {f"{opt}/index": "1", f"{opt}/value": "Low"}}]
    assert notes == ["changed, not a config file Loadout reads (save, registry, cache?): "
                     "{prefix}/drive_c/users/steamuser/AppData/Local/G/Options.sav"]


def test_unwritable_value_and_unreadable_change_are_noted(tmp_path):
    ctx, cfg = _game(tmp_path)
    (cfg / "a.ini").write_bytes(b"[S]\nName=Player\n")
    (cfg / "b.ini").write_bytes(b"[S]\nA=1\nA=2\n")
    before = _snap(ctx)
    (cfg / "a.ini").write_bytes(b"[S]\nName=Pl;ayer\"\n")
    (cfg / "b.ini").write_bytes(b"[S]\nA=1\nA=3\n")
    draft, notes = capture.build_draft([("a", before), ("b", _snap(ctx))], ctx)
    assert draft["options"] == {}
    assert any("won't write" in n and "[S]Name" in n for n in notes)
    assert any("no key Loadout can set" in n and n.endswith("b.ini") for n in notes)


def test_snapshot_skips_symlinks_and_skipped_dirs(tmp_path):
    ctx, cfg = _game(tmp_path)
    outside = tmp_path / "secret.ini"
    outside.write_bytes(b"[S]\nA=1\n")
    os.symlink(outside, cfg / "link.ini")
    win = Path(ctx["prefix"]) / "drive_c/windows"
    win.mkdir()
    (win / "system.ini").write_bytes(b"[S]\nA=1\n")
    (Path(ctx["install_dir"]) / "Engine.ini").write_bytes(b"[S]\nA=1\n")
    snap = capture.snapshot([Path(ctx["prefix"]), Path(ctx["install_dir"])], {win})
    assert [capture.token_path(p, ctx) for p in snap] == ["{install_dir}/Engine.ini"]
