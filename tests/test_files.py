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
    spec = games.load_games()[1245620]["profiles"]["quality"]["files"]
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
    "[ScalabilityGroups]sg.Missing", "[Nope]sg.ShadowQuality",
    "sg.ShadowQuality", "[ScalabilityGroups]a=b", "[A]]x",
])
def test_ini_key_errors(key):
    with pytest.raises(ValueError):
        inicfg.read_values(INI, [key])


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
    profiles = games.load_games()[1627720]["profiles"]
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
