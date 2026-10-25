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


@pytest.mark.parametrize("original", ["", "-novid", "%command% -novid", "gamemoderun %command% -x"])
def test_launch_args_follow_command_and_round_trip(original):
    written = launch.build(original, {"DXVK_FRAME_RATE": "40"}, ("--launcher-skip", "-skipStartScreen"))
    assert "%command% --launcher-skip -skipStartScreen" in written
    assert launch.restore(written, written, original) == (original, None)
    # State lost: the block alone says which args to remove.
    assert launch.restore(written, None, None)[0] == launch.restore(launch.build(original, {"A": "1"}), None, None)[0]


def test_launch_args_only_and_user_edits_kept():
    written = launch.build("", {}, ("--launcher-skip",))
    assert written == "LOADOUT_BEGIN=1 LOADOUT_ARGS=--launcher-skip LOADOUT_END=1 %command% --launcher-skip"
    assert launch.strip(written + " -console") == "%command% -console"
    # The user removed our arg by hand: nothing else is touched.
    assert launch.strip("LOADOUT_BEGIN=1 LOADOUT_ARGS=--launcher-skip LOADOUT_END=1 %command% -x") == "%command% -x"


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
    assert validate_game_doc(_game())["profiles"] == {"quality": {"env": {"DXVK_ASYNC": "1"}, "args": [], "files": []},
                                                      "uncapped": {"env": {}, "args": [], "files": []}}
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
    {"profiles": {"quality": {"files": [_xml("{prefix}/x.json", fmt="json", values={"Key": "1"})]}}},
    {"profiles": {"quality": {"files": [_xml("{prefix}/x.json", fmt="json", values={"/a/../b": "1"})]}}},
    {"profiles": {"quality": {"files": [_xml("{prefix}/x.json", fmt="json", values={"/a[b=c\"]": "1"})]}}},
    {"profiles": {"quality": {"files": [_xml("{prefix}/x.json", fmt="json", values={"/a": "x\"y"})]}}},
    {"profiles": {"quality": {"files": [_xml("{prefix}/x.xml", values={"/a": "1"})]}}},
    {"profiles": {"quality": {"files": [_xml("{prefix}/x.xml", values={})]}}},
    {"profiles": {"quality": {"files": [_xml("{prefix}/x.xml")] * 9}}},
    {"profiles": {"quality": {"launch": {"env": {"LD_PRELOAD": "/x.so"}}}}},
    {"profiles": {"quality": {"launch": {"cmd": "rm -rf ~"}}}},
    {"profiles": {"quality": {"launch": {"args": "--launcher-skip"}}}},  # must be a list
    {"profiles": {"quality": {"launch": {"args": ["--a b"]}}}},
    {"profiles": {"quality": {"launch": {"args": ["--a;reboot"]}}}},
    {"profiles": {"quality": {"launch": {"args": ["$(reboot)"]}}}},
    {"profiles": {"quality": {"launch": {"args": ["--x=1"]}}}},
    {"profiles": {"quality": {"launch": {"args": ["%command%"]}}}},
    {"profiles": {"quality": {"launch": {"args": ["-x", "-x"]}}}},
    {"profiles": {"quality": {"launch": {"args": ["notaflag"]}}}},
    {"profiles": {"quality": {"launch": {"args": ["-x"] * 9}}}},
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


def test_game_doc_resolution():
    res = [{"path": "{install_dir}/G.ini", "format": "ini", "width": ["[S]X"], "height": ["[S]Y"]}]
    assert validate_game_doc(_game(resolution=res))["resolution"] == [{**res[0], "size": []}]
    assert games.resolution_files(validate_game_doc(_game(resolution=res)), 1280, 720) == [
        {"path": "{install_dir}/G.ini", "format": "ini", "set": {"[S]X": "1280", "[S]Y": "720"}}]
    assert games.resolution_files(None, 1280, 720) == []


def test_game_doc_resolution_in_one_value():
    key = "/data[group_name=/video/display]/options[name=Resolution]/value"
    doc = validate_game_doc(_game(resolution=[{"path": "{prefix}/U.json", "format": "json", "size": [key]}]))
    assert games.resolution_files(doc, 1920, 1080) == [
        {"path": "{prefix}/U.json", "format": "json", "set": {key: "1920x1080"}}]
    assert games.resolution_keys(doc) == {key}


@pytest.mark.parametrize("res", [
    {}, [{"path": "/etc/x", "format": "ini", "width": ["[S]X"], "height": ["[S]Y"]}],
    [{"path": "{prefix}/x", "format": "json", "width": ["[S]X"], "height": ["[S]Y"]}],
    [{"path": "{prefix}/x", "format": "ini", "width": ["X"], "height": ["[S]Y"]}],
    [{"path": "{prefix}/x", "format": "ini", "width": [], "height": ["[S]Y"]}],
    [{"path": "{prefix}/x", "format": "ini", "width": ["[S]X"]}],
    [{"path": "{prefix}/x", "format": "ini"}],
    [{"path": "{prefix}/x", "format": "ini", "size": []}],
    [{"path": "{prefix}/x", "format": "json", "size": ["[S]X"]}],
    [{"path": "{prefix}/x", "format": "json", "size": ["/a"] * 5}],
])
def test_game_doc_resolution_rejected(res):
    with pytest.raises(ValidationError):
        validate_game_doc(_game(resolution=res))


def test_game_doc_ini_files():
    ok = {"quality": {"files": [_xml("{install_dir}/G.ini", fmt="ini", values={"[/Script/X.Y]sg.A": "1"})]}}
    assert validate_game_doc(_game(profiles=ok))["profiles"]["quality"]["files"][0]["format"] == "ini"


def test_game_doc_json_files():
    key = "/data[group_name=/graphics/advanced]/options[name=AmbientOcclusion]/value"
    ok = {"quality": {"files": [_xml("{prefix}/U.json", fmt="json", values={key: "Low"})]}}
    assert validate_game_doc(_game(profiles=ok))["profiles"]["quality"]["files"][0]["set"] == {key: "Low"}


def test_game_file_name_must_match_appid(tmp_path):
    (tmp_path / "123.json").write_text(json.dumps(_game()))
    with pytest.raises(ValidationError):
        games.load_games(tmp_path)


def test_annotate_marks_supported_verified_and_profile():
    installed = [{"appid": 1245620, "name": "ELDEN RING"}, {"appid": 1, "name": "Crysis 3"},
                 {"appid": 2, "name": "Lies of P"}]
    docs = {1245620: {"verified": [{"device": "rog-xbox-ally"}], "resolution": [{"path": "x"}]},
            2: {"verified": [], "resolution": []}}
    applied = {"1": {"profile": "performance"}}
    rows = lambda device: [(g["supported"], g["verified"], g["resolution"], g["profile"])
                           for g in games.annotate(installed, docs, applied, device)]
    assert rows("rog-xbox-ally") == [(True, True, True, None), (False, False, False, "performance"),
                                     (True, False, False, None)]
    # Verified is per device: the same entry is untested on a Legion Go.
    assert rows("legion-go")[0] == (True, False, True, None)
    assert rows(None)[0] == (True, False, True, None)


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


def test_resolution_keys():
    doc = {"resolution": [{"width": ["[S]X", "[S]X2"], "height": ["[S]Y"]}]}
    assert games.resolution_keys(doc) == {"[S]X", "[S]X2", "[S]Y"}
    assert games.resolution_keys(None) == set() and games.resolution_keys({}) == set()


def test_resolution_stale():
    res_1080 = [{"path": "p", "format": "ini", "set": {"[S]X": "1920", "[S]Y": "1080"}}]
    written = lambda x, y: {"/g.ini": {"[S]X": {"old": "1280", "new": x}, "[S]Y": {"old": "720", "new": y},
                                       "[S]sg.Shadow": {"old": "1", "new": "0"}}}
    assert games.resolution_stale(written("3840", "2160"), res_1080)  # written docked, now handheld
    assert not games.resolution_stale(written("1920", "1080"), res_1080)
    assert not games.resolution_stale({"/g.ini": {"[S]sg.Shadow": {"old": "1", "new": "0"}}}, res_1080)  # never wrote it
    assert not games.resolution_stale({}, res_1080) and not games.resolution_stale(written("3840", "2160"), [])


def test_bundled_games_load():
    er = games.load_games()[1245620]
    real = set(devices.load_devices()) - {devices.GENERIC}  # nobody can verify on the fallback
    for doc in games.load_games().values():
        assert {v["device"] for v in doc["verified"]} <= real
    for appid in (1245620, 1627720, 1091500):  # ELDEN RING, Lies of P, Cyberpunk 2077
        assert {v["device"] for v in games.load_games()[appid]["verified"]} == real
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


@pytest.mark.parametrize("res, native, size", [
    ("720p", "1920x1080", (1280, 720)), ("1080p", "1920x1080", (1920, 1080)),
    ("720p", "1280x800", (1152, 720)), ("800p", "1280x800", (1280, 800)),
    ("1080p", "1920x1200", (1728, 1080)), ("1600p", "2560x1600", (2560, 1600)),
])
def test_resolution_size_keeps_the_panel_aspect(res, native, size):
    assert devices.resolution_size(res, native) == size


def _connector(root, name, status, modes=""):
    d = root / name
    d.mkdir()
    (d / "status").write_text(status + "\n")
    (d / "modes").write_text(modes)


def test_read_display_builtin_panel(tmp_path):
    _connector(tmp_path, "card1-eDP-1", "connected", "1920x1080\n1280x720\n")
    _connector(tmp_path, "card1-DP-1", "disconnected")
    assert devices.read_display(tmp_path) == ("1920x1080", False)


def test_read_display_docked_prefers_external(tmp_path):
    _connector(tmp_path, "card1-eDP-1", "connected", "1920x1080\n")
    _connector(tmp_path, "card1-HDMI-A-1", "connected", "3840x2160\n2560x1440\n1920x1080\n")
    assert devices.read_display(tmp_path) == ("3840x2160", True)


@pytest.mark.parametrize("modes", ["", "garbage\n", "0x0\n"])
def test_read_display_ignores_bad_modes(tmp_path, modes):
    _connector(tmp_path, "card1-DP-1", "connected", modes)
    _connector(tmp_path, "card1-eDP-1", "connected", "1280x800\n")
    assert devices.read_display(tmp_path) == ("1280x800", False)


def test_read_display_nothing(tmp_path):
    assert devices.read_display(tmp_path) is None
    assert devices.read_display(tmp_path / "missing") is None


@pytest.mark.parametrize("pick, native, expected", [
    (None, "1920x1080", "1080p"), ("720p", "1920x1080", "720p"),
    ("1440p", "1920x1080", "1080p"),  # never above the screen (undocked after picking a TV resolution)
    ("1440p", "3840x2160", "1440p"), (None, "1280x800", "800p"),
])
def test_clamp_resolution(pick, native, expected):
    assert devices.clamp_resolution(pick, native) == expected


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


def test_plan_game_args_and_default_removes_them():
    level = {"fps_limit": 30}
    plan = planner.build_plan(1091500, "quality", "-novid", None, level, False, game_args=("--launcher-skip",))
    assert plan.launch_options.endswith("%command% --launcher-skip -novid")
    assert ("arg", "--launcher-skip") in {(c.kind, c.key) for c in plan.changes}
    entry = {"original": plan.original, "written": plan.launch_options}
    back = planner.build_plan(1091500, "default", plan.launch_options, entry, level, False,
                              game_args=("--launcher-skip",))
    assert back.launch_options == "-novid" and not [c for c in back.changes if c.kind == "arg"]


def test_bundled_cyberpunk_sets_index_with_every_list_value():
    """Cyberpunk reads a fixed list's "index", not its "value" (seen on a device: only the
    value changed and the game kept the old setting). Both must be set, and agree."""
    doc = json.loads((games.DATA_DIR / "1091500.json").read_text())
    options = next(iter(doc["options"].values()))
    lists = {k: v for k, v in options.items() if k.endswith("/value") and v != ["false", "true"]}
    assert len(lists) == 20
    for name, profile in doc["profiles"].items():
        values = profile["files"][0]["set"]
        for key, accepted in lists.items():
            assert values[key.replace("/value", "/index")] == str(accepted.index(values[key])), (name, key)


def test_bundled_cyberpunk_skips_launcher_on_every_profile():
    for name, profile in games.load_games()[1091500]["profiles"].items():
        assert profile["args"] == ["--launcher-skip"], name
