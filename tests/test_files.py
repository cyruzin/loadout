import re
import codecs
import os
import tempfile
from pathlib import Path

import pytest

from loadout import files, steam, xmlcfg
from loadout.paths import safe_path

CONFIG = (b"<config>\r\n<ScreenMode>BORDERLESS</ScreenMode>\r\n<MotionBlur>HIGH</MotionBlur>\r\n"
          b"<!-- keep me -->\r\n<GrassQuality>MEDIUM</GrassQuality>\r\n</config>\r\n")


def ctx_for(tmp_path):
    prefix, install = tmp_path / "pfx", tmp_path / "game"
    prefix.mkdir()
    install.mkdir()
    return {"prefix": str(prefix), "install_dir": str(install), "appid": "1245620"}


def roots(ctx):
    return [Path(ctx["prefix"]), Path(ctx["install_dir"])]

# --- paths -----------------------------------------------------------------


def test_safe_path_accepts_normal_path(tmp_path):
    ctx = ctx_for(tmp_path)
    assert safe_path("{prefix}/drive_c/x.xml", ctx, roots(ctx)) == (tmp_path / "pfx/drive_c/x.xml").resolve()


@pytest.mark.parametrize("template, exc", [
    ("{prefix}/../../etc/passwd", PermissionError),
    ("/etc/passwd", PermissionError),
    ("{home}/.bashrc", ValueError),
    ("{prefix}/{x", ValueError),
    ("{prefix}/a}", ValueError),
    ("{prefix}/a\x00b", ValueError),
])
def test_safe_path_rejects(tmp_path, template, exc):
    ctx = ctx_for(tmp_path)
    with pytest.raises(exc):
        safe_path(template, ctx, roots(ctx))


def test_safe_path_rejects_symlink_pointing_outside(tmp_path):
    ctx = ctx_for(tmp_path)
    (tmp_path / "outside.xml").write_text("x")
    (tmp_path / "pfx/link.xml").symlink_to(tmp_path / "outside.xml")
    with pytest.raises(PermissionError):
        safe_path("{prefix}/link.xml", ctx, roots(ctx))


def test_safe_path_handles_roots_that_are_symlinks(tmp_path):
    real = tmp_path / "real_pfx"
    real.mkdir()
    (tmp_path / "pfx").symlink_to(real)
    ctx = {"prefix": str(tmp_path / "pfx"), "install_dir": str(real), "appid": "1"}
    assert safe_path("{prefix}/a.xml", ctx, [tmp_path / "pfx"]) == (real / "a.xml").resolve()


@pytest.mark.parametrize("raw", ["../x", "a/../../b", "..", "a/b", "/abs", "x" * 60, "\\..\\x", "%2e%2e/x"])
def test_safe_path_never_escapes_roots(raw):
    with tempfile.TemporaryDirectory() as d:
        root = Path(d) / "pfx"
        root.mkdir()
        try:
            p = safe_path("{prefix}/" + raw, {"prefix": str(root), "install_dir": str(root), "appid": "1"}, [root])
        except (ValueError, PermissionError):
            return
        assert p.is_relative_to(root.resolve())

# --- xml handler -----------------------------------------------------------


def test_xml_set_preserves_every_other_byte():
    out = xmlcfg.set_values(CONFIG, {"MotionBlur": "DISABLE"})
    assert out == CONFIG.replace(b"<MotionBlur>HIGH<", b"<MotionBlur>DISABLE<")


@pytest.mark.parametrize("bom, codec", [(codecs.BOM_UTF8, "utf-8"), (codecs.BOM_UTF16_LE, "utf-16-le"),
                                        (codecs.BOM_UTF16_BE, "utf-16-be"),
                                        (b"", "utf-16-le"), (b"", "utf-16-be")])  # BOM-less UTF-16
def test_xml_preserves_bom_and_encoding(bom, codec):
    raw = bom + CONFIG.decode().encode(codec)
    out = xmlcfg.set_values(raw, {"MotionBlur": "LOW"})
    assert out == bom + CONFIG.decode().replace(">HIGH<", ">LOW<").encode(codec)
    assert xmlcfg.read_values(out, ["MotionBlur"]) == {"MotionBlur": "LOW"}


@pytest.mark.parametrize("raw, key", [
    (b"<config><A>1</A>", "A"),  # malformed
    (b"<config><A>1</A><A>2</A></config>", "A"),  # duplicate
    (b"<config><B>1</B></config>", "A"),  # missing
    (b"<config><A><C>1</C></A></config>", "A"),  # not a text element
    (b"<config><A>1</A></config>", "A>|<B"),  # key injection
])
def test_xml_errors(raw, key):
    with pytest.raises(ValueError):
        xmlcfg.read_values(raw, [key])


@pytest.mark.parametrize("text", [
    "<config><A>1</A></config>",
    '<?xml version="1.0" encoding="utf-8"?>\r\n<config>\r\n<!-- <x> -->\r\n<A>1</A><B/></config>\r\n',
    '<config a="1"><A b="x">1</A><![CDATA[ <not a tag> ]]></config>',
])
def test_well_formed_accepts(text):
    xmlcfg.check_well_formed(text)


@pytest.mark.parametrize("text", [
    "", "   ", "<config>", "<config><A>1</B></config>", "<config></config><other/>",
    "<config><A>1</A></config>trailing", "junk<config/>", "<config><A>1<</A></config>",
    "<config><!-- unterminated </config>", "</config>", "<config><A>1</A></config></config>",
])
def test_well_formed_rejects(text):
    with pytest.raises(ValueError):
        xmlcfg.check_well_formed(text)


def test_xml_rejects_bad_encoding():
    with pytest.raises(ValueError):
        xmlcfg.read_values(b"<config><A>\xff</A></config>", ["A"])


def test_xml_rejects_unsafe_values():
    with pytest.raises(ValueError):
        xmlcfg.set_values(CONFIG, {"MotionBlur": "</MotionBlur><X>"})

# --- plan + apply ----------------------------------------------------------


SPEC = [{"path": "{prefix}/drive_c/GraphicsConfig.xml", "format": "xml",
         "set": {"MotionBlur": "DISABLE", "GrassQuality": "LOW"}}]


def setup_game(tmp_path, content=CONFIG):
    ctx = ctx_for(tmp_path)
    cfg = tmp_path / "pfx/drive_c/GraphicsConfig.xml"
    cfg.parent.mkdir()
    cfg.write_bytes(content)
    return ctx, cfg


def apply(spec, ctx, previous):
    plan = files.plan_files(spec, ctx, previous)
    assert plan.error is None, plan.error
    files.apply_writes(plan.writes)
    return plan


def test_plan_is_read_only(tmp_path):
    ctx, cfg = setup_game(tmp_path)
    before = sorted((p, p.stat().st_mtime_ns) for p in tmp_path.rglob("*"))
    plan = files.plan_files(SPEC, ctx, {})
    assert {(c.key, c.old, c.new) for c in plan.changes} == {("MotionBlur", "HIGH", "DISABLE"),
                                                            ("GrassQuality", "MEDIUM", "LOW")}
    assert sorted((p, p.stat().st_mtime_ns) for p in tmp_path.rglob("*")) == before


def test_apply_then_restore_is_identity(tmp_path):
    ctx, cfg = setup_game(tmp_path)
    plan = apply(SPEC, ctx, {})
    assert b"<MotionBlur>DISABLE<" in cfg.read_bytes()
    apply([], ctx, plan.state)  # Default (original)
    assert cfg.read_bytes() == CONFIG


def test_apply_twice_is_idempotent(tmp_path):
    ctx, cfg = setup_game(tmp_path)
    first = apply(SPEC, ctx, {})
    second = files.plan_files(SPEC, ctx, first.state)
    assert second.writes == () and second.state == first.state


def test_switching_restores_original_first(tmp_path):
    ctx, cfg = setup_game(tmp_path)
    first = apply(SPEC, ctx, {})
    other = [{"path": SPEC[0]["path"], "format": "xml", "set": {"ScreenMode": "FULLSCREEN"}}]
    second = apply(other, ctx, first.state)
    raw = cfg.read_bytes()
    assert b"<MotionBlur>HIGH<" in raw and b"<GrassQuality>MEDIUM<" in raw and b"FULLSCREEN" in raw
    apply([], ctx, second.state)
    assert cfg.read_bytes() == CONFIG


def test_value_changed_in_game_is_reported_not_clobbered(tmp_path):
    ctx, cfg = setup_game(tmp_path)
    first = apply(SPEC, ctx, {})
    cfg.write_bytes(cfg.read_bytes().replace(b">DISABLE<", b">LOW<"))
    plan = apply([], ctx, first.state)
    assert any("MotionBlur" in w for w in plan.warnings)
    raw = cfg.read_bytes()
    assert b"<MotionBlur>LOW<" in raw and b"<GrassQuality>MEDIUM<" in raw


def test_missing_file_blocks(tmp_path):
    ctx = ctx_for(tmp_path)
    plan = files.plan_files(SPEC, ctx, {})
    assert plan.error and "Launch the game once" in plan.error


def test_missing_key_blocks(tmp_path):
    ctx, _ = setup_game(tmp_path, b"<config><MotionBlur>HIGH</MotionBlur></config>")
    assert files.plan_files(SPEC, ctx, {}).error


def test_malformed_file_blocks_and_is_untouched(tmp_path):
    ctx, cfg = setup_game(tmp_path, b"<config><MotionBlur>HIGH</MotionBlur>")
    assert files.plan_files(SPEC, ctx, {}).error
    assert cfg.read_bytes() == b"<config><MotionBlur>HIGH</MotionBlur>"


def test_symlinked_config_outside_roots_blocks(tmp_path):
    ctx = ctx_for(tmp_path)
    (tmp_path / "pfx/drive_c").mkdir()
    (tmp_path / "victim.xml").write_bytes(CONFIG)
    (tmp_path / "pfx/drive_c/GraphicsConfig.xml").symlink_to(tmp_path / "victim.xml")
    assert files.plan_files(SPEC, ctx, {}).error
    assert (tmp_path / "victim.xml").read_bytes() == CONFIG


def test_no_game_folder_blocks_only_when_files_are_involved():
    assert files.plan_files(SPEC, None, {}).error
    assert files.plan_files([], None, {}) == files.FilePlan()


def test_apply_is_all_or_nothing(tmp_path, monkeypatch):
    ctx, a = setup_game(tmp_path)
    b = tmp_path / "game/b.xml"
    b.write_bytes(CONFIG)
    spec = SPEC + [{"path": "{install_dir}/b.xml", "format": "xml", "set": {"MotionBlur": "LOW"}}]
    plan = files.plan_files(spec, ctx, {})
    real_replace, calls = os.replace, {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("disk error")
        return real_replace(src, dst)
    monkeypatch.setattr(os, "replace", flaky)
    with pytest.raises(OSError):
        files.apply_writes(plan.writes)
    assert a.read_bytes() == CONFIG and b.read_bytes() == CONFIG  # first file rolled back
    assert sorted(p.name for p in a.parent.iterdir()) == ["GraphicsConfig.xml"]  # no temp files left


def test_apply_keeps_file_permissions(tmp_path):
    ctx, cfg = setup_game(tmp_path)
    cfg.chmod(0o640)
    apply(SPEC, ctx, {})
    assert cfg.stat().st_mode & 0o777 == 0o640

# --- steam app paths -------------------------------------------------------


def test_app_paths(tmp_path):
    (tmp_path / "steamapps").mkdir()
    (tmp_path / "steamapps/appmanifest_1245620.acf").write_text(
        '"AppState" { "appid" "1245620" "name" "ELDEN RING" "installdir" "ELDEN RING" }')
    (tmp_path / "steamapps/appmanifest_2.acf").write_text('"AppState" { "appid" "2" "installdir" "../x" }')
    assert steam.app_paths(tmp_path, 1245620) == {
        "prefix": str(tmp_path / "steamapps/compatdata/1245620/pfx"),
        "install_dir": str(tmp_path / "steamapps/common/ELDEN RING"), "appid": "1245620"}
    assert steam.app_paths(tmp_path, 2) is None
    assert steam.app_paths(tmp_path, 3) is None

# --- real-world fixture ----------------------------------------------------

# ELDEN RING's GraphicsConfig.xml exactly as found on a device: UTF-16 LE *without* BOM,
# XML declaration, CRLF. Decoding it as UTF-8 "worked" and then matched no tag at all.
ELDEN_RING = ("""<?xml version="1.0" encoding="UTF-16"?>
<config>
<ScreenMode>BORDERLESS</ScreenMode>
<Resolution-WindowScreenWidth>1280</Resolution-WindowScreenWidth>
<Resolution-WindowScreenHeight>720</Resolution-WindowScreenHeight>
<Resolution-FullScreenWidth>1280</Resolution-FullScreenWidth>
<Resolution-FullScreenHeight>720</Resolution-FullScreenHeight>
<Resolution-BorderlessScreenWidth>1280</Resolution-BorderlessScreenWidth>
<Resolution-BorderlessScreenHeight>720</Resolution-BorderlessScreenHeight>
<Auto-detectBestRenderingSettings>OFF</Auto-detectBestRenderingSettings>
<QualitySetting>CUSTOM</QualitySetting>
<TextureQuality>HIGH</TextureQuality>
<Antialiasing>HIGH</Antialiasing>
<SSAO>DISABLE</SSAO>
<DepthOfField>DISABLE</DepthOfField>
<MotionBlur>HIGH</MotionBlur>
<ShadowQuality>LOW</ShadowQuality>
<LightingQuality>MEDIUM</LightingQuality>
<EffectsQuality>MEDIUM</EffectsQuality>
<ReflectionQuality>LOW</ReflectionQuality>
<WaterSurfaceQuality>HIGH</WaterSurfaceQuality>
<ShadeQuality>LOW</ShadeQuality>
<VolumetricEffectQuality>MEDIUM</VolumetricEffectQuality>
<RaytracingQuality>DISABLE</RaytracingQuality>
<GIDataQuality>LOW</GIDataQuality>
<GrassQuality>MEDIUM</GrassQuality>
</config>
""").replace("\n", "\r\n").encode("utf-16-le")


def test_elden_ring_real_file_quality_round_trip(tmp_path):
    from loadout import games
    assert ELDEN_RING[:4] == b"<\x00?\x00"  # same first bytes as the device's xxd
    spec = games.load_games()[1245620]["devices"]["rog-xbox-ally"]["profiles"]["quality"]["files"]
    ctx = ctx_for(tmp_path)
    cfg = tmp_path / "pfx/drive_c/users/steamuser/AppData/Roaming/EldenRing/GraphicsConfig.xml"
    cfg.parent.mkdir(parents=True)
    cfg.write_bytes(ELDEN_RING)

    plan = apply(spec, ctx, {})
    assert [(c.key, c.old, c.new) for c in plan.changes] == [("MotionBlur", "HIGH", "DISABLE")]
    assert cfg.read_bytes() == ELDEN_RING.decode("utf-16-le").replace(
        "<MotionBlur>HIGH<", "<MotionBlur>DISABLE<").encode("utf-16-le")  # still no BOM, still CRLF
    apply([], ctx, plan.state)
    assert cfg.read_bytes() == ELDEN_RING

# --- INI handler -----------------------------------------------------------

from loadout import inicfg  # noqa: E402

INI = (b"; comment\r\n[ScalabilityGroups]\r\nsg.ShadowQuality=1\r\nsg.TextureQuality = 2  \r\n\r\n"
       b"[/Script/Game.Settings]\r\nFSR3Mode=Quality\r\nSteps=1.0\r\nSteps=2.0\r\nShadowQuality=9\r\n")


def test_ini_set_preserves_every_other_byte():
    out = inicfg.set_values(INI, {"[ScalabilityGroups]sg.ShadowQuality": "0",
                                  "[ScalabilityGroups]sg.TextureQuality": "3"})
    assert out == INI.replace(b"sg.ShadowQuality=1", b"sg.ShadowQuality=0").replace(
        b"sg.TextureQuality = 2  ", b"sg.TextureQuality = 3  ")


def test_ini_keys_are_scoped_to_their_section():
    assert inicfg.read_values(INI, ["[ScalabilityGroups]sg.ShadowQuality", "[/Script/Game.Settings]ShadowQuality"]) \
        == {"[ScalabilityGroups]sg.ShadowQuality": "1", "[/Script/Game.Settings]ShadowQuality": "9"}


@pytest.mark.parametrize("key", [
    "[/Script/Game.Settings]Steps",  # duplicated (UE repeats benchmark keys)
    "sg.ShadowQuality", "[ScalabilityGroups]a=b", "[A]]x",
])
def test_ini_key_errors(key):
    with pytest.raises(ValueError):
        inicfg.read_values(INI, [key])


def test_ini_absent_key_reads_none():
    assert inicfg.read_values(INI, ["[ScalabilityGroups]sg.Missing", "[Nope]sg.ShadowQuality"]) == {
        "[ScalabilityGroups]sg.Missing": None, "[Nope]sg.ShadowQuality": None}


def test_ini_none_removes_the_line_and_adding_it_back_restores_the_bytes():
    out = inicfg.set_values(INI, {"[ScalabilityGroups]sg.ShadowQuality": None})
    assert out == INI.replace(b"sg.ShadowQuality=1\r\n", b"")
    assert inicfg.read_values(out, ["[ScalabilityGroups]sg.ShadowQuality"]) == {
        "[ScalabilityGroups]sg.ShadowQuality": None}
    # Added after the section's last line (blank lines stay after it), with the file's CRLF.
    back = inicfg.set_values(out, {"[ScalabilityGroups]sg.ShadowQuality": "1"})
    assert back == INI.replace(b"sg.ShadowQuality=1\r\nsg.TextureQuality = 2  \r\n",
                               b"sg.TextureQuality = 2  \r\nsg.ShadowQuality=1\r\n")
    assert inicfg.set_values(INI, {"[ScalabilityGroups]sg.Missing": None}) == INI  # absent stays absent


def test_ini_adds_to_the_last_section_without_a_final_newline():
    out = inicfg.set_values(b"[A]\nx=1\n[B]\ny=2", {"[B]z": "3", "[A]w": "4"})
    assert out == b"[A]\nx=1\nw=4\n[B]\ny=2\nz=3\n"


def test_ini_adds_sectionless_keys_before_the_first_header():
    assert inicfg.set_values(b"[S]\r\nb=2\r\n", {"[]a": "1"}) == b"a=1\r\n[S]\r\nb=2\r\n"
    assert inicfg.set_values(b"-- c\r\na = 1\r\n", {"[]b": "2"}) == b"-- c\r\na = 1\r\nb=2\r\n"


@pytest.mark.parametrize("values", [
    {"[Nope]a": "1"},  # a new section is refused
    {"[ScalabilityGroups]sg.New": "1\r\n[Injected]"},
    {"[ScalabilityGroups]sg.New": "x;y"},
    {"[ScalabilityGroups]sg.New=1\r\nX": "1"},
    {"[/Script/Game.Settings]Steps": None},  # duplicated: neither set nor removed
])
def test_ini_add_and_remove_refusals(values):
    with pytest.raises(ValueError):
        inicfg.set_values(INI, values)


@pytest.mark.parametrize("raw", [b"[S]\r\nnot a key value line\r\n", b"[S]\r\n=novalue\r\n", b"\xff\xfe\xff"])
def test_ini_malformed(raw):
    with pytest.raises(ValueError):
        inicfg.read_values(raw, ["[S]a"])


@pytest.mark.parametrize("value", ["1\r\nInjected=1", "x;y", "[S]", "a=b"])
def test_ini_rejects_unsafe_values(value):
    with pytest.raises(ValueError):
        inicfg.set_values(INI, {"[ScalabilityGroups]sg.ShadowQuality": value})


@pytest.mark.parametrize("codec", ["utf-16-le", "utf-16-be"])
def test_ini_bomless_utf16_round_trip(codec):
    raw = INI.decode().encode(codec)
    out = inicfg.set_values(raw, {"[ScalabilityGroups]sg.ShadowQuality": "3"})
    assert out == INI.decode().replace("sg.ShadowQuality=1", "sg.ShadowQuality=3").encode(codec)


# Crysis 3 Remastered's game.cfg as found on a device (ASCII, CRLF, "--" comments, no sections).
CRYSIS = (b"-- [Game-Configuration]\r\n-- Attention: This file is re-generated by the system! Editing is "
          b"not recommended! \r\n\r\nr_AntialiasingMode = 2\r\nr_Flares = 0\r\nr_MotionBlur = 2\r\n"
          b"r_MotionBlurShutterSpeed = 0\r\nr_TexMaxAnisotropy = 1\r\nr_TexMinAnisotropy = 1\r\n"
          b"sys_spec = 3\r\nsys_spec_dlss = 1\r\nsys_spec_GameEffects = 3\r\nsys_spec_ObjectDetail = 3\r\n"
          b"sys_spec_Particles = 3\r\nsys_spec_PostProcessing = 3\r\nsys_spec_raytracing = 3\r\n"
          b"sys_spec_Shading = 3\r\nsys_spec_Shadows = 3\r\nsys_spec_TextureResolution = 3\r\n"
          b"sys_spec_Water = 3\r\nr_Width = 1280\r\nr_Height = 720\r\nr_DisplayFreq = 120\r\n"
          b"r_WindowState = 1\r\nr_vSync = 1\r\n")


def test_ini_keys_before_any_section_and_dash_comments():
    assert inicfg.read_values(CRYSIS, ["[]sys_spec_Shadows", "[]r_vSync"]) == {
        "[]sys_spec_Shadows": "3", "[]r_vSync": "1"}
    out = inicfg.set_values(CRYSIS, {"[]sys_spec_Shadows": "1"})
    assert out == CRYSIS.replace(b"sys_spec_Shadows = 3", b"sys_spec_Shadows = 1")


@pytest.mark.parametrize("key", ["[]-- [Game-Configuration]", "[]--x"])
def test_ini_dash_comment_lines_are_never_keys(key):
    raw = CRYSIS + b"--x = 1\r\n"
    with pytest.raises(ValueError):
        inicfg.read_values(raw, [key])
    # A "-- [Header]" comment is no section either.
    assert inicfg.read_values(raw, ["[Game-Configuration]r_vSync"]) == {"[Game-Configuration]r_vSync": None}
    with pytest.raises(ValueError):
        inicfg.set_values(raw, {"[Game-Configuration]r_vSync": "0"})


def test_ini_keys_after_a_header_are_not_sectionless():
    raw = b"a = 1\r\n[S]\r\nb = 2\r\n"
    assert inicfg.read_values(raw, ["[]a", "[S]b", "[]b"]) == {"[]a": "1", "[S]b": "2", "[]b": None}


# Lies of P's GameUserSettings.ini as found on a device (ASCII, CRLF, lives in the install dir).
LIES_OF_P = ("""[ScalabilityGroups]
sg.ResolutionQuality=100.000000
sg.ViewDistanceQuality=1
sg.AntiAliasingQuality=1
sg.ShadowQuality=1
sg.PostProcessQuality=1
sg.TextureQuality=1
sg.EffectsQuality=1
sg.FoliageQuality=1
sg.ShadingQuality=1
sg.AnisotropyQuality=3
sg.AtmosphereQuality=1
sg.AmbientOcclusionQuality=1
sg.ReflectionQuality=1

[/Script/ProjectP.LGameUserSettings]
IsInitedGraphic=True
LastResolution=(X=0,Y=0)
bPrevVSync=False
CACAOEnabled=True
DLSSMode=Off
FSR2Mode=Off
FSR3Mode=Quality
FSR3Sharpness=0.700000
FSR3FrameInterpolation=False
bUseVSync=False
ResolutionSizeX=1920
ResolutionSizeY=1080
LastUserConfirmedResolutionSizeX=1920
LastUserConfirmedResolutionSizeY=1080
DesiredScreenWidth=1280
DesiredScreenHeight=720
FrameRateLimit=30.000000
LastCPUBenchmarkSteps=158.467346
LastCPUBenchmarkSteps=135.435577

[/Script/Engine.GameUserSettings]
bUseDesiredScreenHeight=False

[ShaderPipelineCache.CacheFile]
LastOpened=LiesofP
""").replace("\n", "\r\n").encode("ascii")


def test_lies_of_p_real_file_profiles_round_trip(tmp_path):
    from loadout import games
    profiles = games.load_games()[1627720]["devices"]["rog-xbox-ally"]["profiles"]
    ctx = ctx_for(tmp_path)
    cfg = tmp_path / "game/LiesofP/Saved/Config/WindowsNoEditor/GameUserSettings.ini"
    cfg.parent.mkdir(parents=True)
    cfg.write_bytes(LIES_OF_P)

    perf = apply(profiles["performance"]["files"], ctx, {})
    text = cfg.read_bytes().decode("ascii")
    assert "sg.ShadowQuality=0\r\n" in text and "sg.TextureQuality=1\r\n" in text  # texture stays Medium
    assert "sg.AnisotropyQuality=3\r\n" in text and "FrameRateLimit=0.000000\r\n" in text
    assert "sg.ResolutionQuality=100.000000\r\n" in text and "ResolutionSizeX=1920\r\n" in text  # untouched
    assert text.count("LastCPUBenchmarkSteps=") == 2  # duplicated keys left alone

    balanced = apply(profiles["balanced"]["files"], ctx, perf.state)  # switch: no stacking
    text = cfg.read_bytes().decode("ascii")
    assert "sg.ViewDistanceQuality=1\r\n" in text and "sg.ShadowQuality=0\r\n" in text
    apply([], ctx, balanced.state)  # Default (original)
    assert cfg.read_bytes() == LIES_OF_P


# Hogwarts Legacy's GameUserSettings.ini as found on a device (ASCII, CRLF, in the prefix), trimmed
# to whole lines of the real file. The game copies its [/Script/Phoenix...] values (upscaler,
# resolution) from its save on launch, so only [ScalabilityGroups] is Loadout's.
HOGWARTS = ("""[/Script/Phoenix.PhoenixGameSettings]
FrameRateLimit=-1.000000
bUseVSync=False
bIsUpscaleModeModified=True
UpscaleMode=AMD_FSR3_Balanced
UpscaleSoftness=0.703749
ResolutionSizeX=1280
ResolutionSizeY=720
FullscreenMode=2
FrameGeneration=(Mode=Off,NumFramesInterpolated=0,LocStr="Off")
r.ChosenFrameGenProvider=None

[SystemSettings]
r.GPULUIDLow=1010
r.GPULUIDHigh=0

[ScalabilityGroups]
sg.ResolutionQuality=100.000000
sg.ViewDistanceQuality=0
sg.AntiAliasingQuality=3
sg.ShadowQuality=0
sg.PostProcessQuality=0
sg.TextureQuality=0
sg.EffectsQuality=0
sg.FoliageQuality=0
sg.ShadingQuality=0
sg.VolumetricsQuality=0
sg.SkyQuality=0
sg.PopulationQuality=0
sg.RaytracingQuality=3
sg.RaytracingReflectionsQuality=3
sg.RaytracingShadowsQuality=3

[/Script/Engine.GameUserSettings]
bUseDesiredScreenHeight=False

[ShaderPipelineCache.CacheFile]
LastOpened=Phoenix

""").replace("\n", "\r\n").encode("ascii")


def test_hogwarts_real_file_profiles_round_trip(tmp_path):
    from loadout import games
    profiles = games.load_games()[990080]["devices"]["rog-xbox-ally"]["profiles"]
    ctx = ctx_for(tmp_path)
    cfg = tmp_path / "pfx/drive_c/users/steamuser/AppData/Local/Hogwarts Legacy/Saved/Config/WindowsNoEditor/GameUserSettings.ini"
    cfg.parent.mkdir(parents=True)
    cfg.write_bytes(HOGWARTS)

    quality = apply(profiles["quality"]["files"], ctx, {})
    text = cfg.read_bytes().decode("ascii")
    assert "sg.ShadingQuality=2\r\n" in text and "sg.TextureQuality=1\r\n" in text
    assert "UpscaleMode=AMD_FSR3_Balanced\r\n" in text and "ResolutionSizeX=1280\r\n" in text  # the game's

    perf = apply(profiles["performance"]["files"], ctx, quality.state)  # switch: no stacking
    assert cfg.read_bytes() == HOGWARTS  # the device's file was saved on these (all Low) settings
    apply([], ctx, perf.state)  # Default (original)
    assert cfg.read_bytes() == HOGWARTS


# --- JSON handler ----------------------------------------------------------

from loadout import jsoncfg  # noqa: E402

# Same shape and bytes as Cyberpunk 2077's UserSettings.json on a device: UTF-8 without BOM,
# LF, 4-space indent, no final newline.
CP_JSON = b"""{
    "version": 152,
    "data": [
        {
            "group_name": "/graphics/advanced",
            "options": [
                {
                    "name": "AmbientOcclusion",
                    "type": "string_list",
                    "value": "Medium",
                    "default_value": "High",
                    "values": [
                        "Off",
                        "Low",
                        "Medium",
                        "High"
                    ]
                },
                {
                    "name": "Anisotropy",
                    "type": "int_list",
                    "value": 16,
                    "default_value": 16,
                    "values": [1, 4, 8, 16]
                }
            ]
        },
        {
            "group_name": "/graphics/basic",
            "options": [
                {
                    "name": "FilmGrain",
                    "type": "bool",
                    "value": false,
                    "default_value": true
                },
                {
                    "name": "FieldOfView",
                    "type": "float",
                    "value": 80.0,
                    "default_value": 80.0
                },
                {
                    "name": "Dup",
                    "value": 1
                },
                {
                    "name": "Dup",
                    "value": 2
                }
            ]
        }
    ]
}"""
AO = "/data[group_name=/graphics/advanced]/options[name=AmbientOcclusion]/value"
ANISO = "/data[group_name=/graphics/advanced]/options[name=Anisotropy]/value"
GRAIN = "/data[group_name=/graphics/basic]/options[name=FilmGrain]/value"
FOV = "/data[group_name=/graphics/basic]/options[name=FieldOfView]/value"


def test_json_reads_typed_values_as_text():
    assert jsoncfg.read_values(CP_JSON, [AO, ANISO, GRAIN, FOV, "/version"]) == {
        AO: "Medium", ANISO: "16", GRAIN: "false", FOV: "80.0", "/version": "152"}


def test_json_set_preserves_every_other_byte_and_type():
    out = jsoncfg.set_values(CP_JSON, {AO: "Low", ANISO: "8", GRAIN: "true", FOV: "90.5"})
    assert out == (CP_JSON.replace(b'"value": "Medium"', b'"value": "Low"')
                   .replace(b'"value": 16,', b'"value": 8,')
                   .replace(b'"value": false', b'"value": true')
                   .replace(b'"value": 80.0', b'"value": 90.5'))
    assert jsoncfg.set_values(out, {AO: "Medium", ANISO: "16", GRAIN: "false", FOV: "80.0"}) == CP_JSON


@pytest.mark.parametrize("key", [
    "/data[group_name=/graphics/basic]/options[name=Dup]/value",  # two elements match
    "/data[group_name=/graphics/nope]/options[name=FilmGrain]/value",
    "/data[group_name=/graphics/basic]/options[name=FilmGrain]/missing",
    "/data[group_name=/graphics/basic]/options",  # an array, not a plain value
    "/data[group_name=/graphics/basic]",  # an object
    "/version[a=b]",  # selector on a number
    "/data/options",  # member of an array
    "data", "/a/../b", "/a[b=c]]", "/" + "a/" * 9 + "a",
])
def test_json_key_errors(key):
    with pytest.raises(ValueError):
        jsoncfg.read_values(CP_JSON, [key])


@pytest.mark.parametrize("raw", [b'{"a": 1', b'{"a": 1}}', b"", b'{"a": NaN', b"\xff\xfe\xff"])
def test_json_malformed(raw):
    with pytest.raises(ValueError):
        jsoncfg.read_values(raw, ["/a"])


def test_json_null_and_duplicate_members_refused():
    with pytest.raises(ValueError):
        jsoncfg.read_values(b'{"a": null}', ["/a"])
    with pytest.raises(ValueError):
        jsoncfg.read_values(b'{"a": 1, "a": 2}', ["/a"])


@pytest.mark.parametrize("key,value", [
    (AO, 'x", "injected": "1'), (AO, "a\\u0022b"), (AO, "a\nb"),
    (GRAIN, "yes"), (GRAIN, "1"), (ANISO, "x"), (ANISO, "1e9"), (ANISO, "true"), (ANISO, "0x10"),
])
def test_json_rejects_unsafe_or_mistyped_values(key, value):
    with pytest.raises(ValueError):
        jsoncfg.set_values(CP_JSON, {key: value})


def test_json_two_keys_for_one_value_refused():
    raw = b'{"o": [{"n": "a", "m": "b", "value": 1}]}'
    with pytest.raises(ValueError):
        jsoncfg.set_values(raw, {"/o[n=a]/value": "2", "/o[m=b]/value": "3"})


def test_json_plan_apply_restore_through_files(tmp_path):
    ctx = ctx_for(tmp_path)
    cfg = tmp_path / "pfx/drive_c/users/steamuser/AppData/Local/CD Projekt Red/Cyberpunk 2077/UserSettings.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_bytes(CP_JSON)
    spec = [{"path": "{prefix}/drive_c/users/steamuser/AppData/Local/CD Projekt Red/Cyberpunk 2077/"
                     "UserSettings.json", "format": "json", "set": {AO: "Off", GRAIN: "false"}}]
    plan = apply(spec, ctx, {})
    assert [(c.key, c.old, c.new) for c in plan.changes] == [(AO, "Medium", "Off")]
    assert b'"value": "Off"' in cfg.read_bytes()
    apply([], ctx, plan.state)
    assert cfg.read_bytes() == CP_JSON


def _cyberpunk_file(values):
    """UserSettings.json shaped like the device's (4-space indent, LF, no final newline), holding
    the entry's keys with typed values."""
    import json
    groups: dict = {}
    for key, value in values.items():
        group, name, field = re.match(r"^/data\[group_name=(.+)\]/options\[name=(\w+)\]/(\w+)$", key).groups()
        typed = {"true": True, "false": False}.get(value, value)
        if re.fullmatch(r"[0-9.]+", value):
            typed = float(value) if "." in value else int(value)
        groups.setdefault(group, {}).setdefault(name, {"name": name, "type": "x"})[field] = typed
    doc = {"version": 152, "data": [{"group_name": g, "options": list(o.values())} for g, o in groups.items()]}
    return json.dumps(doc, indent=4).encode()


def test_cyberpunk_profiles_round_trip(tmp_path):
    from loadout import games
    profiles = games.load_games()[1091500]["devices"]["rog-xbox-ally"]["profiles"]
    balanced = profiles["balanced"]["files"]
    raw = _cyberpunk_file(balanced[0]["set"])  # the game's "Steam Deck" preset
    assert raw.startswith(b'{\n    "version": 152,\n    "data": [\n') and not raw.endswith(b"\n")
    ctx = ctx_for(tmp_path)
    cfg = Path(safe_path(balanced[0]["path"], ctx, roots(ctx)))
    cfg.parent.mkdir(parents=True)
    cfg.write_bytes(raw)

    plan = apply(profiles["quality"]["files"], ctx, {})
    assert {(c.key.split("name=")[-1], c.old, c.new) for c in plan.changes} == {
        ("FSR2]/value", "Balanced", "Quality"), ("QuickPresets]/value", "Steam Deck", "Custom")}
    plan = apply(balanced, ctx, plan.state)
    assert cfg.read_bytes() == raw
    plan = apply(profiles["performance"]["files"], ctx, plan.state)
    changed = {c.key.split("options[")[-1]: c.new for c in plan.changes}
    assert changed["name=FSR2]/value"] == "Performance"
    assert changed["name=TextureQuality]/value"] == "Low" and changed["name=TextureQuality]/index"] == "0"
    apply([], ctx, plan.state)
    assert cfg.read_bytes() == raw


# --- LSX handler (Larian) --------------------------------------------------

from loadout import lsxcfg  # noqa: E402


def _entry(key, value, vtype="int32", type_="0"):
    return (f'                <node id="ConfigEntry">\n'
            f'                    <attribute id="MapKey" type="FixedString" value="{key}"/>\n'
            f'                    <attribute id="Type" type="int32" value="{type_}"/>\n'
            f'                    <attribute id="Value" type="{vtype}" value="{value}"/>\n'
            f'                </node>\n').encode()


# Same bytes as Baldur's Gate 3's graphicSettings.lsx (native Linux, ROG Xbox Ally, Low preset),
# fewer entries: UTF-8 without BOM, LF, 4-space indent, entries in MapKey order, final newline.
LSX_HEAD = (b'<?xml version="1.0" encoding="UTF-8"?>\n<save>\n'
            b'    <version major="4" minor="8" revision="0" build="700"/>\n'
            b'    <region id="Config">\n        <node id="root">\n'
            b'            <attribute id="Version64" type="int64" value="36169534507319298"/>\n'
            b'            <children>\n')
LSX_TAIL = b'            </children>\n        </node>\n    </region>\n</save>\n'
LSX = (LSX_HEAD + _entry("AnimationLODDetail", "2") + _entry("CurrentSettings", "Low", "LSString", "1")
       + _entry("SSAOEnabled", "0") + _entry("ShadowQuality", "2")
       + _entry("UpscaleSharpness", "0.80000001", "float", "2") + LSX_TAIL)


def test_lsx_reads_values_and_absent_keys():
    assert lsxcfg.read_values(LSX, ["ShadowQuality", "CurrentSettings", "UpscaleSharpness", "FogQuality"]) == {
        "ShadowQuality": "2", "CurrentSettings": "Low", "UpscaleSharpness": "0.80000001", "FogQuality": None}


def test_lsx_set_changes_only_the_value():
    out = lsxcfg.set_values(LSX, {"ShadowQuality": "1"})
    assert out == LSX.replace(_entry("ShadowQuality", "2"), _entry("ShadowQuality", "1"))


def test_lsx_none_removes_the_entry_and_adding_it_back_restores_the_bytes():
    removed = lsxcfg.set_values(LSX, {"SSAOEnabled": None})
    assert removed == LSX.replace(_entry("SSAOEnabled", "0"), b"")
    assert lsxcfg.read_values(removed, ["SSAOEnabled"]) == {"SSAOEnabled": None}
    assert lsxcfg.set_values(removed, {"SSAOEnabled": "0"}) == LSX  # same place, same format
    assert lsxcfg.set_values(LSX, {"FogQuality": None}) == LSX  # already absent


def test_lsx_adds_missing_keys_in_mapkey_order():
    out = lsxcfg.set_values(LSX, {"AntiAliasing": "0", "VSync": "0", "BloomEnabled": "0"})
    assert out == (LSX_HEAD + _entry("AnimationLODDetail", "2") + _entry("AntiAliasing", "0")
                   + _entry("BloomEnabled", "0") + _entry("CurrentSettings", "Low", "LSString", "1")
                   + _entry("SSAOEnabled", "0") + _entry("ShadowQuality", "2")
                   + _entry("UpscaleSharpness", "0.80000001", "float", "2") + _entry("VSync", "0") + LSX_TAIL)


@pytest.mark.parametrize("values", [
    {"FogQuality": "Low"}, {"FogQuality": "0.5"},  # only int32 entries are added
    {"ShadowQuality": '1"/><x a="'}, {"ShadowQuality": "<"}, {"ShadowQuality": "1&amp;"},
    {"Bad Key": "1"}, {"../x": "1"}, {"": "1"},
])
def test_lsx_rejects_bad_values_and_keys(values):
    with pytest.raises(ValueError):
        lsxcfg.set_values(LSX, values)


@pytest.mark.parametrize("raw", [
    LSX.replace(_entry("ShadowQuality", "2"), _entry("SSAOEnabled", "1")),  # duplicated MapKey
    LSX.replace(_entry("ShadowQuality", "2"), _entry("ShadowQuality", "2").replace(
        b'                    <attribute id="Value" type="int32" value="2"/>\n', b"")),  # entry without a Value
    LSX.replace(b'<attribute id="Value" type="int32" value="0"/>',
                b'<attribute id="Extra" type="int32" value="0"/><attribute id="Value" type="int32" value="0"/>'),
    LSX[:-30],  # truncated file
    LSX_HEAD + LSX_TAIL,  # no entries: nothing to copy the layout from
    b"\xff\xfe\x00<",
])
def test_lsx_refuses_unexpected_files(raw):
    assert raw != LSX
    with pytest.raises(ValueError):
        lsxcfg.read_values(raw, ["ShadowQuality"])


BG3_PATH = "{xdg_data}/Larian Studios/Baldur's Gate 3/graphicSettings.lsx"


def native_ctx(tmp_path):
    ctx = ctx_for(tmp_path)
    ctx["xdg_data"] = str(tmp_path / "share")
    cfg = tmp_path / "share/Larian Studios/Baldur's Gate 3/graphicSettings.lsx"
    cfg.parent.mkdir(parents=True)
    cfg.write_bytes(LSX)
    return ctx, cfg


def test_lsx_profile_and_default_round_trip_in_xdg_data(tmp_path):
    ctx, cfg = native_ctx(tmp_path)
    spec = [{"path": BG3_PATH, "format": "lsx", "set": {"ShadowQuality": "1", "SSAOEnabled": None, "VSync": "0"}}]
    plan = files.plan_files(spec, ctx, {})
    assert plan.error is None
    assert sorted((c.key, c.old, c.new) for c in plan.changes) == [
        ("SSAOEnabled", "0", None), ("ShadowQuality", "2", "1"), ("VSync", None, "0")]
    files.apply_writes(plan.writes)
    assert lsxcfg.read_values(cfg.read_bytes(), ["ShadowQuality", "SSAOEnabled", "VSync"]) == {
        "ShadowQuality": "1", "SSAOEnabled": None, "VSync": "0"}
    # Default: every key back, the added one removed, the removed one added back.
    restore = files.plan_files([], ctx, plan.state)
    files.apply_writes(restore.writes)
    assert cfg.read_bytes() == LSX


@pytest.mark.parametrize("path", [
    "{xdg_data}/Steam/config/x.lsx",  # Steam's own folder under ~/.local/share
    "{xdg_data}/Steam/steamapps/common/Other/x.lsx",
])
def test_xdg_data_keeps_steams_folder_out(tmp_path, path):
    ctx, _ = native_ctx(tmp_path)
    plan = files.plan_files([{"path": path, "format": "lsx", "set": {"A": "1"}}], ctx, {})
    assert plan.error and "Unsafe" in plan.error


def test_xdg_data_symlink_out_is_refused(tmp_path):
    ctx, cfg = native_ctx(tmp_path)
    outside = tmp_path / "outside.lsx"
    outside.write_bytes(LSX)
    link = cfg.parent / "link.lsx"
    link.symlink_to(outside)
    plan = files.plan_files([{"path": "{xdg_data}/Larian Studios/Baldur's Gate 3/link.lsx", "format": "lsx",
                              "set": {"ShadowQuality": "1"}}], ctx, {})
    assert plan.error and "Unsafe" in plan.error


def test_xdg_data_path_needs_the_token_in_context(tmp_path):
    plan = files.plan_files([{"path": BG3_PATH, "format": "lsx", "set": {"A": "1"}}], ctx_for(tmp_path), {})
    assert plan.error and "Unsafe" in plan.error


# The Witcher 3's dx12user.settings, copied from a device with the Medium preset (no BOM, CRLF). Each
# preset writes its own set of [Rendering] keys: switching adds and removes lines.
WITCHER3 = (Path(__file__).parent / "data/witcher3_dx12user_medium.settings").read_bytes()


def _ini_values(raw):
    return dict(line.split("=", 1) for line in raw.decode().splitlines() if "=" in line and not line.startswith("["))


def test_witcher3_profiles_add_and_remove_keys_and_default_restores_them(tmp_path):
    from loadout import games
    assert WITCHER3[:4] == b"[Ren" and b"\r\n" in WITCHER3 and WITCHER3.count(b"\n") == WITCHER3.count(b"\r\n")
    profiles = games.load_games()[292030]["devices"]["rog-xbox-ally"]["profiles"]
    ctx = ctx_for(tmp_path)
    cfg = tmp_path / "pfx/drive_c/users/steamuser/Documents/The Witcher 3/dx12user.settings"
    cfg.parent.mkdir(parents=True)
    cfg.write_bytes(WITCHER3)
    state = {}
    for name in ("quality", "balanced", "quality"):  # switching profiles, no Default in between
        spec = profiles[name]["files"]
        plan = apply(spec, ctx, state)
        state = {str(cfg): plan.state[str(cfg)]}
        assert inicfg.read_values(cfg.read_bytes(), list(spec[0]["set"])) == spec[0]["set"]
        assert cfg.read_bytes().count(b"\n") == cfg.read_bytes().count(b"\r\n")  # still CRLF only
    # From the Medium file, textures High drops TextureDownscale and adds TextureMipBias (as the game does).
    from_original = {(k, v["old"], v["new"]) for k, v in state[str(cfg)].items()}
    assert ("[Rendering]TextureDownscale", "1", None) in from_original
    assert ("[Rendering]TextureMipBias", None, "-0.4") in from_original

    apply([], ctx, state)  # Default
    assert _ini_values(cfg.read_bytes()) == _ini_values(WITCHER3)
    assert sorted(cfg.read_bytes().splitlines()) == sorted(WITCHER3.splitlines())


def test_witcher3_profiles_are_kestononline_with_xess_and_no_performance():
    from loadout import games
    for dev, block in games.load_games()[292030]["devices"].items():
        assert set(block["profiles"]) == {"quality", "balanced"}, dev  # 60 isn't reachable on these
        for name, p in block["profiles"].items():
            s = p["files"][0]["set"]
            assert s["[Rendering/RT]EnableRT"] == "false" and s["[PostProcess]AAMode"] == "7", (dev, name)
            assert s["[PostProcess]XESSQuality"] == {"quality": "1", "balanced": "4"}[name]  # Native AA / Quality
            # Detail Level: High for 30, Medium for 40 (less CPU).
            assert (s["[LevelOfDetail]DecalsHideDistance"], s["[Rendering]MeshLODDistanceScale"]) == {
                "quality": ("40", "1.2"), "balanced": ("30", "1")}[name]
            # Motion blur: On at 2 for 30 (absent = On), off for 40 along with blur (seen better on device).
            blur = (s["[PostProcess]AllowMotionBlur"], s.get("[PostProcess]MotionBlurIntensity"),
                    s.get("[PostProcess]AllowBlur", "unset"))
            assert blur == {"quality": (None, "2", "unset"), "balanced": ("false", None, "false")}[name]
            assert s["[Viewport]VSync"] == "false" and s["[Engine]LimitFPS"] == "0"  # Steam's QAM limits
            # Keys whose section the game drops with them are left out: inicfg can't add a section.
            assert not any(k.startswith(("[Rendering/DRS]", "[Streaming/Textures]")) for k in s)
            assert p["args"] == ["--launcher-skip"]
            # Steam sets SteamDeck=1 only on a Deck (not seen on a ROG Xbox Ally); 0 unlocks the menu there.
            assert p["env"] == ({"SteamDeck": "0"} if dev.startswith("steam-deck") else {}), (dev, name)
