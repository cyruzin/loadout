# AGENTS.md - Loadout

A Decky Loader plugin (SteamOS first; Bazzite/CachyOS best effort) that applies per-game profiles
(Quality, Balanced, Performance, Uncapped) and returns a game to "Default (original)".
The plugin is an ENGINE; JSON files are DATA. Data can never contain code.

## Layout
- `main.py` - thin Decky adapter. The only file that imports `decky`.
- `py_modules/loadout/` - pure core (never imports `decky`):
  - `validate.py` device/game doc schema + env allow/deny rules
  - `games.py` loads `data/games/<appid>.json` (per-game env + config-file keys per profile);
    `annotate` marks installed games as supported / verified on this device / profile applied,
    for the UI's Show filter (`GAME_FILTERS`)
  - `paths.py` token expansion + `safe_path` (resolve symlinks, must stay in prefix/install dir)
  - `textfile.py` decode/encode config files (UTF-8 or UTF-16, with or without BOM; ELDEN RING
    writes UTF-16 LE without BOM) + the `VALUE` charset allowed in any file
  - `xmlcfg.py` flat XML read/set that preserves every other byte (own well-formedness check)
  - `inicfg.py` INI read/set by `[Section]Key`, same byte-preserving approach; duplicated keys refused.
    Keys before any header are `[]Key` and `--` lines are comments (CryEngine's `game.cfg`)
  - `jsoncfg.py` JSON read/set by `/member/array[field=value]/...` path, same byte-preserving
    approach; the value keeps its JSON type; ambiguous paths, null, objects and arrays refused
  - `files.py` per-key file plan (read-only) + all-or-nothing apply with rollback; keys Loadout
    wrote before that the new profile doesn't set go back to their originals
  - `launch.py` marker-delimited launch-option block (build / strip / restore); game args go
    right after `%command%` and are recorded in the block (`LOADOUT_ARGS`) so strip needs no state
  - `planner.py` pure `build_plan` (dry-run, never writes)
  - `devices.py` DMI detection, device table, level fallback chain
  - `steam.py` libraryfolders.vdf / appmanifest parsing, per-game prefix/install paths
  - `store.py` `atomic_write` + JSON files (settings = intent, state = backups)
  - `data/devices/*.json` bundled device tables (`generic.json` is required)
  - `data/games/<appid>.json` bundled per-game data (device-independent)
- `scripts/capture.py` - contributor tool, run on the device with the system `python3` (Decky never
  loads it, so the stdlib limit below doesn't apply; it ships in the zip under `scripts/`).
  Snapshots the prefix and install dir, finds the keys that changed with the core parsers and
  prints a draft entry (`options` + per-snapshot `set`). It shows what a game writes, not what it reads.
- `src/api.ts` typed `callable()` wrappers + Steam launch-option access. `src/index.tsx` UI.
  The QAM panel remounts (e.g. when a dropdown menu opens), which wipes `useState`: keep UI state
  in `useKept` (module-level store in `index.tsx`), never plain `useState`. Every hook (`useKept` included) goes
  before `Content`'s early returns (Loading/Setup): one placed after them crashed the panel (React #310). Dropdowns use
  `layout="below"` so long values aren't cut off. Keep dropdowns short: every filter caps its list
  to the 50 most recently played (`LIST_LIMIT`) and offers a search past that; a D-pad can't scroll
  hundreds of items, and the verified list will grow too.
  Text the user must read goes on a focusable item (e.g. a dropdown's `description`): the QAM
  only scrolls to focusable items, so a text row below the last one gets cut off.
  The FPS cap switch is per game (`settings.games[appid].fps_cap`, default on); `get_bootstrap`
  returns each profile's cap for the configured device (`fps_limits`) for its label.
  Report every outcome with `report()` / `reportError()`: they write the in-panel status line and
  toast. Never rely on a toast alone (Steam can play its sound without showing it with the QAM open).

## Commands
    pnpm install && pnpm run build     # frontend -> dist/index.js
    pnpm run typecheck                 # tsc --noEmit
    .venv/bin/python -m pytest -q      # backend tests
    scripts/package.sh                 # out/Loadout.zip (release: push a vX.Y.Z tag)
    python3 scripts/capture.py <appid> # on the device: snapshot/diff of a game's config -> draft entry

## Security rules (non-negotiable)
- Validate data structurally and semantically before use. Unknown fields are rejected.
- Never use str.format, eval, exec, pickle, yaml.load or shell=True with data.
- Env vars: allowlist prefixes + denylist; values quoted with shlex.quote in launch options.
  Game args: plain flags only (`validate.ARG`: no values, spaces or shell characters).
- Writes are atomic (temp file + os.replace), all-or-nothing, never while the game runs.
  Backups are per key, never whole files.
- Paths from data go through `safe_path` (prefix/install dir only); files are opened with O_NOFOLLOW.
- No root (`plugin.json` flags are empty). No compiled Python deps.
- Decky runs plugins on its own PyInstaller-frozen Python, which only ships the stdlib modules
  decky_loader uses. The backend may only import `__future__ codecs json os pathlib re stat sys
  typing` (enforced by `tests/test_runtime.py`). No xml.etree, shlex, dataclasses, tempfile, copy:
  `xml.etree` already crashed the plugin on a real device. Adding a module means proving it ships.
- Never invent device or game values; every data entry needs a real source. Config keys and
  their accepted values (`options`) are copied from a real config file / the in-game menu.
- Test fixtures for game files must match the real file's BYTES (encoding, BOM, line endings),
  not text pasted from a terminal: check with `xxd` on the device first.

## Scope
IN: game list, 4 profiles + Default, FPS cap (DXVK/VKD3D env), per-game env and game args, per-game XML/INI/JSON config keys,
launch options, settings file,
device detection. Profiles set graphics (upscaler included), never resolution; `GAMES.md` lists
the bundled games.
LATER (do not build unless asked): community data download + SHA-256,
Wine registry, global/batch profile, export/import.
OUT (maintainer decision): TDP and other power settings; the user handles those in Steam's QAM.
OUT (maintainer decision, 0.3.1): game resolution, in profiles or as a separate pick. It caused
trouble (Hogwarts Legacy reloads it from its save on launch) and depends on the screen. 0.3.0's
per-game resolution (with `read_display`, stale detection) was removed; state written by it is
restored by the next profile apply. `test_bundled_games_leave_resolution_alone` keeps resolution
keys out of entries. Upscaler/frame generation stay in profiles where the game reads them from the
file; where it doesn't (Hogwarts Legacy), the user sets them in the menu.
OUT (maintainer decision): FPS cap for native Linux games. Setting gamescope's `GAMESCOPE_FPS_LIMIT`
atom or writing `$MANGOHUD_CONFIGFILE` would fight Steam's own QAM limiter (both are Steam's) and
need the plugin to act on game launch; Steam's per-game profile already caps those games.
MangoHud via env was tested on a ROG Xbox Ally in Game Mode: `MANGOHUD=1
MANGOHUD_CONFIG=fps_limit=N,no_display` capped native Vulkan, did nothing on OpenGL (needs the
`mangohud` wrapper), and ELDEN RING (Proton) didn't start with `MANGOHUD=1`. A `MANGOHUD_CONFIG`
on a game also overrides the QAM performance overlay (ValveSoftware/gamescope#1800).

## Known unknowns (do NOT guess; flag them)
- Steam frontend APIs (`SteamClient.Apps.*`) are not a public contract.
- DMI `product_name` for ROG Ally and Legion Go families: taken from Handheld Daemon
  (github.com/hhd-dev/hhd), not yet confirmed on our own hardware. Some original Legion Go units
  report no valid product_name (HHD falls back to BIOS version); those must pick the device manually.
- Which keys a game reads from its config file: some games overwrite part of it from their save on
  launch (Hogwarts Legacy: upscaler and resolution in `[/Script/Phoenix.PhoenixGameSettings]`, likely
  the whole section, from `SavedUserOptions.sav`; `[ScalabilityGroups]` sticks). Check the file after launching.
- Crysis 3 Remastered reads `game.cfg` on launch (seen on device: `sys_spec_Shadows` edited to 1
  showed Low, System Spec Custom, value kept), except `r_AntialiasingMode` and `sys_spec_raytracing`:
  after Loadout wrote 1/1, launching put back the previous 0/4, likely from the encrypted
  `Profiles/default/attributes.xml`. The entry leaves both out. `r_vSync`, `r_TexMax/MinAnisotropy`
  and `r_MotionBlurShutterSpeed` stick (file unchanged after launch, VSync and 16x shown in the menu),
  but the menu then shows the previous motion blur amount (Low) while the file keeps 0 (Disabled):
  assumed display-only, not confirmed visually.
- FPS cap env per Proton: Proton 11.0's DXVK has no `DXVK_FRAME_RATE` string in `dxgi.dll`/`d3d11.dll`
  (checked on device; Crysis 3, D3D11, ran 70+ under a 30 cap with the DXVK HUD showing), so the
  cap also sets `DXVK_CONFIG=dxgi.maxFrameRate=N;d3d9.maxFrameRate=N`. Its `d3d12core.dll` still
  reads `VKD3D_FRAME_RATE`. Since which Proton `DXVK_FRAME_RATE` stopped working: unknown.
- Which field a JSON game reads: Cyberpunk reads `index` for fixed lists (seen on device: `value`
  alone was ignored) and `value` for dynamic ones (FSR2, QuickPresets). The entry sets both for
  fixed lists; `test_bundled_cyberpunk_sets_index_with_every_list_value` keeps them in sync.

## Code style
- Never use tool or plugin names (e.g. "ponytail") as comment prefixes. Write plain comments.

## Definition of done
Run this checklist at the end of EVERY implementation, adjustment or fix, before reporting back:

1. Tests: new behavior has new tests (malicious inputs included for anything touching data, paths,
   env or files); existing tests that the change affects are updated, not deleted to make them pass.
2. Run everything and fix what fails:
   `.venv/bin/python -m pytest -q`, `pnpm run typecheck`, `pnpm run build`.
3. Docs: check whether README.md (user-facing: features, tables, how to run), CONTRIBUTING.md
   (data format and the verify/add steps) or AGENTS.md (layout, rules, scope, known unknowns)
   are now stale, and update them.
4. No `decky` import under `py_modules/loadout/`.
5. Report what was run and its result; say explicitly if something was skipped or is unverified.
