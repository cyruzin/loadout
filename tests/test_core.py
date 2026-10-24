import json
import os
import shlex

import pytest

from loadout import devices, games, launch, planner, steam
from loadout.store import JsonStore
from loadout.validate import ValidationError, validate_device_doc, validate_env, validate_game_doc

# --- env -------------------------------------------------------------------


@pytest.mark.parametrize("name", ["DXVK_ASYNC", "VKD3D_FRAME_RATE", "PROTON_NO_ESYNC", "MANGOHUD",
                                  "WINEDLLOVERRIDES", "RADV_PERFTEST"])
def test_env_allowlisted(name):
    assert validate_env({name: "1"}) == {name: "1"}


@pytest.mark.parametrize("name", ["LD_PRELOAD", "LD_LIBRARY_PATH", "PATH", "HOME", "SHELL",
                                  "dxvk_async", "DXVK-ASYNC", "FOO", "WINEDLLOVERRIDES_X", ""])
def test_env_rejected_names(name):
    with pytest.raises(ValidationError):
        validate_env({name: "1"})


@pytest.mark.parametrize("value", ["a\nb", "a\x00b", "x" * 257, "a\rb", 1, "LOADOUT_END=1"])
def test_env_rejected_values(value):
    with pytest.raises(ValidationError):
        validate_env({"DXVK_ASYNC": value})


@pytest.mark.parametrize("value", ["a b", "a;rm -rf ~", "$(reboot)", "'quote\"", "`id`"])
def test_launch_values_are_quoted(value):
    tokens = shlex.split(launch.build("", {"DXVK_HUD": value}))
    # The value stays one shell word: nothing can escape into a command.
    assert tokens == ["LOADOUT_BEGIN=1", f"DXVK_HUD={value}", "LOADOUT_END=1", "%command%"]

# --- launch-option block ---------------------------------------------------


@pytest.mark.parametrize("original", ["", "-novid", "gamemoderun %command% -novid", "  spaced  "])
def test_launch_round_trip_exact(original):
    written = launch.build(original, {"DXVK_FRAME_RATE": "40"})
    assert launch.restore(written, written, original) == (original, None)


def test_launch_user_edit_after_apply_is_preserved():
    written = launch.build("-novid", {"DXVK_FRAME_RATE": "40"})
    edited = written + " -console"
    assert launch.restore(edited, written, "-novid") == ("%command% -novid -console", None)


def test_launch_corrupted_markers_left_alone():
    current = "LOADOUT_BEGIN=1 DXVK_FRAME_RATE=40 %command%"
    text, warning = launch.restore(current, "something else", "")
    assert text == current and warning


def test_launch_lost_state_still_strips_block():
    assert launch.restore("LOADOUT_BEGIN=1 A=1 LOADOUT_END=1 %command% -x", None, None) == ("%command% -x", None)

# --- planner ---------------------------------------------------------------


def _apply(current, entry, profile, fps=40):
    plan = planner.build_plan(480, profile, current, entry, {"fps_limit": fps}, False)
    return plan, {"original": plan.original, "written": plan.launch_options}


def test_switching_profiles_never_stacks_and_default_restores():
    p1, e1 = _apply("-novid", None, "performance", 60)
    p2, e2 = _apply(p1.launch_options, e1, "quality", 30)
    assert p2.launch_options.count("LOADOUT_BEGIN") == 1 and "=30" in p2.launch_options
    assert "=60" not in p2.launch_options
    back, _ = _apply(p2.launch_options, e2, "default")
    assert back.launch_options == "-novid"


def test_apply_twice_is_idempotent():
    p1, e1 = _apply("", None, "quality")
    p2, e2 = _apply(p1.launch_options, e1, "quality")
    assert p2.launch_options == p1.launch_options and e2 == e1 and p2.original == ""


def test_unknown_profile_rejected():
    with pytest.raises(ValueError):
        planner.build_plan(480, "turbo", "", None, {}, False)


def test_plan_blocked_on_corrupted_markers():
    plan = planner.build_plan(480, "quality", "LOADOUT_END=1 %command%", None, {"fps_limit": 30}, False)
    assert plan.blocked and plan.launch_options == "LOADOUT_END=1 %command%"

def test_game_env_merges_and_overrides_device_env():
    level = {"fps_limit": 30, "env": {"DXVK_ASYNC": "1", "MESA_VK_WSI_PRESENT_MODE": "fifo"}}
    game_env = {"MESA_VK_WSI_PRESENT_MODE": "immediate", "VKD3D_FRAME_RATE": "25"}
    plan = planner.build_plan(1245620, "quality", "", None, level, False, game_env)
    tokens = shlex.split(plan.launch_options)
    assert "MESA_VK_WSI_PRESENT_MODE=immediate" in tokens and "DXVK_ASYNC=1" in tokens
    assert "VKD3D_FRAME_RATE=25" in tokens and "DXVK_FRAME_RATE=30" in tokens
    assert planner.build_plan(1245620, "default", "", None, level, False, game_env).launch_options == ""

# --- validation ------------------------------------------------------------


def _device(**over):
    doc = {"schema_version": 1, "device": "x", "name": "X", "match": {"product_name": ["X1"]},
           "native": "1280x800", "levels": {"quality": {"any": {"fps_limit": 30}}}}
    doc.update(over)
    return doc


def test_device_doc_valid():
    assert validate_device_doc(_device())["levels"]["quality"]["any"] == {"fps_limit": 30}


@pytest.mark.parametrize("over", [
    {"extra": 1},
    {"schema_version": 2},
    {"device": "../etc"},
    {"native": "big"},
    {"levels": {"turbo": {}}},
    {"levels": {"battery": {}}},  # removed profile
    {"levels": {"quality": {"4k": {}}}},
    {"levels": {"quality": {"any": {"fps_limit": 5}}}},
    {"levels": {"quality": {"any": {"fps_limit": True}}}},
    {"levels": {"quality": {"any": {"env": {"LD_PRELOAD": "/x.so"}}}}},
    {"levels": {"quality": {"any": {"cmd": "rm -rf"}}}},
    {"match": {"product_name": ["x"] * 17}},
    {"name": "n" * 61},
])
def test_device_doc_rejected(over):
    with pytest.raises(ValidationError):
        validate_device_doc(_device(**over))


def test_device_doc_missing_field():
    doc = _device()
    del doc["levels"]
    with pytest.raises(ValidationError):
        validate_device_doc(doc)

def _xml(path, fmt="xml", values=None):
    return {"path": path, "format": fmt, "set": {"A": "1"} if values is None else values}


def _game(**over):
    doc = {"schema_version": 1, "appid": 480, "name": "Spacewar",
           "source": "https://example.com/post",
           "verified": [{"proton": "default", "device": "steam-deck-lcd", "date": "2026-10-24"}],
           "profiles": {"quality": {"launch": {"env": {"DXVK_ASYNC": "1"}}}, "uncapped": {}}}
    doc.update(over)
    return doc


def test_game_doc_valid():
    assert validate_game_doc(_game())["profiles"] == {"quality": {"env": {"DXVK_ASYNC": "1"}, "files": []},
                                                      "uncapped": {"env": {}, "files": []}}
    bare = _game()
    del bare["verified"], bare["source"]
    assert validate_game_doc(bare)["verified"] == [] and validate_game_doc(bare)["source"] is None


@pytest.mark.parametrize("over", [
    {"extra": 1},
    {"schema_version": 2},
    {"appid": 0},
    {"appid": "480"},
    {"name": ""},
    {"verified": {"proton": "x", "device": "x", "date": "2026-10-24"}},  # must be a list
    {"verified": [{"proton": "x", "device": "../x", "date": "2026-10-24"}]},
    {"verified": [{"proton": "x", "device": "x", "date": "yesterday"}]},
    {"verified": [{"proton": "x", "device": "x"}]},
    {"verified": [{"proton": "x", "device": "x", "date": "2026-10-24"}] * 17},
    {"source": "http://example.com"},
    {"source": "javascript:alert(1)"},
    {"profiles": {"battery": {}}},
    {"profiles": {"quality": {"files": {}}}},
    {"profiles": {"quality": {"files": [_xml("/etc/passwd")]}}},
    {"profiles": {"quality": {"files": [_xml("{home}/.bashrc")]}}},
    {"profiles": {"quality": {"files": [_xml("{prefix}/../../.bashrc")]}}},
    {"profiles": {"quality": {"files": [_xml("{prefix}/./x.xml")]}}},
    {"profiles": {"quality": {"files": [_xml("{prefix}/a\\b.xml")]}}},
    {"profiles": {"quality": {"files": [_xml("{prefix}/{pre{prefix}fix}.xml")]}}},
    {"profiles": {"quality": {"files": [_xml("{prefix}/x.xml", fmt="ini")]}}},
    {"profiles": {"quality": {"files": [_xml("{prefix}/x.xml", values={"A": "<b>"})]}}},
    {"profiles": {"quality": {"files": [_xml("{prefix}/x.xml", values={"A": "x&y"})]}}},
    {"profiles": {"quality": {"files": [_xml("{prefix}/x.xml", values={"a b": "1"})]}}},
    {"profiles": {"quality": {"files": [_xml("{prefix}/x.ini", fmt="ini", values={"sg.Shadow": "1"})]}}},
    {"profiles": {"quality": {"files": [_xml("{prefix}/x.xml", values={"[S]Key": "1"})]}}},
    {"profiles": {"quality": {"files": [_xml("{prefix}/x.xml", values={})]}}},
    {"profiles": {"quality": {"files": [_xml("{prefix}/x.xml")] * 9}}},
    {"profiles": {"quality": {"launch": {"env": {"LD_PRELOAD": "/x.so"}}}}},
    {"profiles": {"quality": {"launch": {"cmd": "rm -rf ~"}}}},
])
def test_game_doc_rejected(over):
    with pytest.raises(ValidationError):
        validate_game_doc(_game(**over))


def test_game_options_restrict_values():
    files = {"quality": {"files": [_xml("{prefix}/x.xml", values={"Grass": "LOW", "Other": "ANY"})]}}
    with pytest.raises(ValidationError):
        validate_game_doc(_game(profiles=files, options={"{prefix}/x.xml": {"Grass": ["MEDIUM", "HIGH", "MAX"]}}))
    ok = {"quality": {"files": [_xml("{prefix}/x.xml", values={"Grass": "MAX", "Other": "ANY"})]}}
    validate_game_doc(_game(profiles=ok, options={"{prefix}/x.xml": {"Grass": ["MEDIUM", "HIGH", "MAX"]}}))


@pytest.mark.parametrize("options", [
    [], {"/etc/x.xml": {}}, {"{prefix}/x.xml": {"a b": ["X"]}}, {"{prefix}/x.xml": {"A": []}},
    {"{prefix}/x.xml": {"A": "X"}}, {"{prefix}/x.xml": {"A": ["<x>"]}},
])
def test_game_options_rejected(options):
    with pytest.raises(ValidationError):
        validate_game_doc(_game(options=options))


def test_game_doc_ini_files():
    ok = {"quality": {"files": [_xml("{install_dir}/G.ini", fmt="ini", values={"[/Script/X.Y]sg.A": "1"})]}}
    assert validate_game_doc(_game(profiles=ok))["profiles"]["quality"]["files"][0]["format"] == "ini"


def test_game_file_name_must_match_appid(tmp_path):
    (tmp_path / "123.json").write_text(json.dumps(_game()))
    with pytest.raises(ValidationError):
        games.load_games(tmp_path)


def test_annotate_marks_supported_verified_and_profile():
    installed = [{"appid": 1245620, "name": "ELDEN RING"}, {"appid": 1, "name": "Crysis 3"},
                 {"appid": 2, "name": "Lies of P"}]
    docs = {1245620: {"verified": [{"device": "rog-xbox-ally"}]}, 2: {"verified": []}}
    applied = {"1": {"profile": "performance"}}
    rows = lambda device: [(g["supported"], g["verified"], g["profile"])
                           for g in games.annotate(installed, docs, applied, device)]
    assert rows("rog-xbox-ally") == [(True, True, None), (False, False, "performance"), (True, False, None)]
    # Verified is per device: the same entry is untested on a Legion Go.
    assert rows("legion-go")[0] == (True, False, None)
    assert rows(None)[0] == (True, False, None)


def test_elden_ring_performance_and_uncapped_use_lowest_settings():
    doc = json.loads((games.DATA_DIR / "1245620.json").read_text())
    (path, options), = doc["options"].items()
    for profile in ("performance", "uncapped"):
        values = doc["profiles"][profile]["files"][0]["set"]
        for key, accepted in options.items():
            assert values[key] == accepted[0], (profile, key)  # option lists go lowest -> highest


def test_lies_of_p_profiles_match_the_tested_presets():
    profiles = {p: body["files"][0]["set"] for p, body in games.load_games()[1627720]["profiles"].items()}
    sg = lambda p, name: profiles[p][f"[ScalabilityGroups]sg.{name}Quality"]
    for p in profiles:
        # Every profile: anisotropic at max, texture at medium, game's own FPS limit off.
        assert sg(p, "Anisotropy") == "3" and sg(p, "Texture") == "1"
        assert profiles[p]["[/Script/ProjectP.LGameUserSettings]FrameRateLimit"] == "0.000000"
    assert profiles["performance"] == profiles["uncapped"]
    assert sg("performance", "Shadow") == "0" and sg("balanced", "ViewDistance") == "1"
    assert sg("balanced", "Shadow") == "0" and sg("quality", "Shadow") == "1"


def test_bundled_games_load():
    er = games.load_games()[1245620]
    # Every bundled device except the generic fallback (which isn't a device anyone can verify on).
    for doc in games.load_games().values():
        assert {v["device"] for v in doc["verified"]} == set(devices.load_devices()) - {devices.GENERIC}
    for profile in ("quality", "balanced", "performance", "uncapped"):
        assert er["profiles"][profile]["env"] == {"MESA_VK_WSI_PRESENT_MODE": "immediate"}, profile

# --- devices ---------------------------------------------------------------


def test_bundled_devices_load_and_detect():
    devs = devices.load_devices()
    assert devices.detect(devs, "Jupiter") == "steam-deck-lcd"
    assert devices.detect(devs, "Galileo") == "steam-deck-oled"
    # Ally product names carry per-unit suffixes, so matching is by substring.
    for name, dev in (("ROG Ally RC71L_Action", "rog-ally"), ("ROG Ally RC71L_RC71L", "rog-ally"),
                      ("ROG Ally X RC72LA_RC72LA_000123206", "rog-ally-x"),
                      ("ROG Xbox Ally RC73YA_RC73YA", "rog-xbox-ally"),
                      ("ROG Xbox Ally X RC73XA_RC73XA", "rog-xbox-ally-x"),
                      ("ROG XBOX Ally X RC74XA RC74XA", "rog-xbox-ally-x20")):
        assert devices.detect(devs, name) == dev, name
    assert devices.native_class(devs["rog-ally"]) == "1080p"
    # Lenovo reports the bare model code.
    for name, dev in (("83E1", "legion-go"), ("83N0", "legion-go-2"), ("83N1", "legion-go-2"),
                      ("83L3", "legion-go-s"), ("83N6", "legion-go-s"), ("83Q2", "legion-go-s"), ("83Q3", "legion-go-s")):
        assert devices.detect(devs, name) == dev, name
    assert devices.native_class(devs["legion-go"]) == "1600p"
    assert devices.native_class(devs["legion-go-s"]) == "1200p"
    assert devices.detect(devs, "Unknown PC") is None
    assert devices.detect(devs, "") is None
    assert devices.native_class(devs["steam-deck-oled"]) == "800p"


def test_read_dmi(tmp_path):
    (tmp_path / "product_name").write_text("Galileo\n")
    assert devices.read_dmi(tmp_path) == "Galileo"
    assert devices.read_dmi(tmp_path / "missing") == ""


def test_level_fallback_chain():
    devs = {d["device"]: d for d in (
        validate_device_doc(_device(levels={"quality": {"720p": {"fps_limit": 30}, "any": {"fps_limit": 25}}})),
        validate_device_doc(_device(device="generic", match={"product_name": []},
                                    levels={"quality": {"any": {"fps_limit": 20}}, "uncapped": {"any": {}}})),
    )}
    assert devices.resolve_level(devs, "x", "quality", "720p") == ({"fps_limit": 30}, False)
    assert devices.resolve_level(devs, "x", "quality", "1080p") == ({"fps_limit": 25}, False)
    assert devices.resolve_level(devs, "x", "uncapped", "720p") == ({}, True)
    assert devices.resolve_level(devs, "nope", "quality", "720p") == ({"fps_limit": 20}, True)
    assert devices.resolve_level(devs, "generic", "quality", "720p") == ({"fps_limit": 20}, False)
    assert devices.resolve_level(devs, "x", "performance", "720p") == ({}, True)

# --- steam library ---------------------------------------------------------


def _manifest(lib, appid, name):
    d = lib / "steamapps"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"appmanifest_{appid}.acf").write_text(
        f'"AppState"\n{{\n\t"appid"\t\t"{appid}"\n\t"name"\t\t"{name}"\n}}\n')


def test_list_games_multiple_libraries(tmp_path):
    root, sd = tmp_path / "Steam", tmp_path / "sd"
    _manifest(root, 480, "Spacewar")
    _manifest(root, 1493710, "Proton Experimental")
    _manifest(root, 1628350, "Steam Linux Runtime 3.0 (sniper)")
    _manifest(sd, 70, "Half-Life")
    (root / "steamapps/appmanifest_1.acf").write_text('"AppState" { "appid" "1"')  # truncated
    (root / "steamapps/appmanifest_2.acf").write_text('"AppState" { "name" "No id" }')
    (root / "steamapps/libraryfolders.vdf").write_text(
        f'"libraryfolders"\n{{\n"0" {{ "path" "{root}" }}\n"1" {{ "path" "{sd}" "apps" {{ "70" "1" }} }}\n}}')
    assert steam.list_games(root) == [{"appid": 70, "name": "Half-Life"}, {"appid": 480, "name": "Spacewar"}]
    assert steam.find_steam_root(tmp_path) is None


def test_list_games_without_libraryfolders(tmp_path):
    _manifest(tmp_path, 480, "Spacewar")
    assert steam.list_games(tmp_path) == [{"appid": 480, "name": "Spacewar"}]


@pytest.mark.parametrize("text", ['"a" {', '"a" }', '{ }', '"a" "b" "c"'])
def test_parse_vdf_malformed(text):
    with pytest.raises(ValueError):
        steam.parse_vdf(text)


def test_parse_vdf_escapes():
    assert steam.parse_vdf(r'"k" { "p" "a\"b\\c" }') == {"k": {"p": 'a"b\\c'}}

# --- store -----------------------------------------------------------------


def test_store_atomic_write_failure_keeps_original(tmp_path, monkeypatch):
    store = JsonStore(tmp_path / "s.json", {"games": {}})
    store.save({"games": {"480": 1}})

    def boom(src, dst):
        raise OSError("disk error")
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        store.save({"games": {}})
    assert json.loads((tmp_path / "s.json").read_text()) == {"games": {"480": 1}}
    assert os.listdir(tmp_path) == ["s.json"]  # temp file cleaned up


def test_store_corrupt_file_is_kept_aside(tmp_path):
    (tmp_path / "s.json").write_text("{nope")
    assert JsonStore(tmp_path / "s.json", {"a": 1}).load() == {"a": 1}
    assert (tmp_path / "s.corrupt.json").exists()
