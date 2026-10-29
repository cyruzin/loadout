# AGENTS.md - Loadout

A Decky Loader plugin (SteamOS first; Bazzite/CachyOS best effort) that applies per-game profiles
(Quality, Balanced, Performance) and returns a game to "Default (original)".
The plugin is an ENGINE; JSON files are DATA. Data can never contain code.

## Layout
- `main.py` - thin Decky adapter. The only file that imports `decky`.
- `py_modules/loadout/` - pure core (never imports `decky`):
  - `validate.py` device/game doc schema + env allow/deny rules
  - `games.py` loads `data/games/<appid>.json` (per-game env + config-file keys per profile);
    `annotate` marks installed games as supported / verified on this device (has a `devices` block for it) /
    profile applied, for the UI's Show filter (`GAME_FILTERS`); `profiles_for` picks the device's own
    profiles, else those borrowed from the device the user picked (`settings.games[appid].profile_device`)
  - `paths.py` token expansion + `safe_path` (resolve symlinks, must stay in prefix/install dir)
  - `textfile.py` decode/encode config files (UTF-8 or UTF-16, with or without BOM; ELDEN RING
    writes UTF-16 LE without BOM) + the `VALUE` charset allowed in any file
  - `xmlcfg.py` flat XML read/set that preserves every other byte (own well-formedness check)
  - `inicfg.py` INI read/set by `[Section]Key`, same byte-preserving approach; duplicated keys refused.
    Keys before any header are `[]Key` and `--` lines are comments (CryEngine's `game.cfg`).
    A key can be absent (The Witcher 3 omits keys at their default, per preset): read gives None,
    `null` in data removes the line, a missing key is added at the end of its (existing) section
  - `jsoncfg.py` JSON read/set by `/member/array[field=value]/...` path, same byte-preserving
    approach; the value keeps its JSON type; ambiguous paths, null, objects and arrays refused
  - `lsxcfg.py` Larian `.lsx` (BG3's `graphicSettings.lsx`) read/set by `MapKey`, same approach.
    The game omits settings at their default, so a key can be absent: read gives None, `null` in
    data removes the entry, a missing int32 is added (copy of an existing entry, MapKey order).
    Only that exact `ConfigEntry` layout is accepted; duplicated MapKeys refused
  - `files.py` per-key file plan (read-only) + all-or-nothing apply with rollback; keys Loadout
    wrote before that the new profile doesn't set go back to their originals (None: removed again).
    `allowed`: prefix, install dir, or `{xdg_data}` (`~/.local/share`, native games) minus its `Steam/`.
    `handler` picks lsxcfg by the `.lsx` extension (validation ties format and extension)
    `same`: a number the game only rewrote (`3000` → `3000.0000`, Skyrim SE) is still Loadout's
    value, not a change in game (string compare lost the original on profile switches)
  - `launch.py` marker-delimited launch-option block (build / strip / restore); game args go
    right after `%command%` and are recorded in the block (`LOADOUT_ARGS`) so strip needs no state
  - `planner.py` pure `build_plan` (dry-run, never writes)
  - `devices.py` DMI detection, device table, level fallback chain
  - `steam.py` libraryfolders.vdf / appmanifest parsing, per-game prefix/install paths
  - `store.py` `atomic_write` + JSON files (settings = intent, state = backups)
  - `data/devices/*.json` bundled device tables (`generic.json` is required)
  - `data/games/<appid>.json` bundled per-game data: `options` once, profiles per device under
    `devices.<device-id>` (each with its own `verified` {proton, date} and `source`), so a device is
    tuned or added without touching the others. A device level's `fps_limit` is the profile's
    target FPS, shown only (no cap since 0.6.0)
- `scripts/capture.py` - contributor tool, run on the device with the system `python3` (Decky never
  loads it, so the stdlib limit below doesn't apply; it ships in the zip under `scripts/`).
  Snapshots the prefix and install dir, finds the keys that changed with the core parsers and
  prints a draft entry (`options` + per-snapshot `set`). It shows what a game writes, not what it reads.
- `src/api.ts` typed `callable()` wrappers + Steam launch-option access. `src/index.tsx` UI.
  The QAM panel remounts (e.g. when a dropdown menu opens), which wipes `useState`: keep UI state
  in `useKept` (module-level store in `index.tsx`), never plain `useState`. Every hook (`useKept` included) goes
  before `Content`'s early returns (Loading/error): one placed after them crashed the panel (React #310). Dropdowns use
  `layout="below"` so long values aren't cut off. Keep dropdowns short: every filter caps its list
  to the 50 most recently played (`LIST_LIMIT`) and offers a search past that; a D-pad can't scroll
  hundreds of items, and the verified list will grow too.
  Text the user must read goes on a focusable item (e.g. a dropdown's `description`): the QAM
  only scrolls to focusable items, so a text row below the last one gets cut off.
  The device is detected at load (`main.DEVICE`), else `generic`; there's no Setup or switch (removed:
  a manual pick only made it easy to land on the wrong device). The panel only shows it, first row (no switch: another device's profiles
  are borrowed per game).
  **Reset Loadout** (in Settings) applies Default to every game with a profile (frontend: launch
  options are written there), then `reset_settings`; it stops, settings kept, at the first game that fails.
  The confirm modal (`describe`) leads with a plain summary; the technical diff stays under `Details`
  (collapsed). Never drop the diff: showing exactly what changes before writing is a core guarantee.
  The Game dropdown's description (`gameNote`) explains the selected game's mark (other devices / no settings).
  The Profile dropdown lists only the profiles the device's (or borrowed) block has (`annotate`'s
  `profiles`; a block leaves out one it can't hold the target with) and `games.profile_spec` refuses
  the others. Its description says what the profile is made for ("40 FPS at 1280×720"):
  `get_bootstrap` returns each profile's target on the configured device (`fps_targets`).
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
- Env vars: allowlist prefixes + denylist (plus exact names in `ENV_EXACT`, e.g. `SteamDeck`); values quoted with shlex.quote in launch options.
  Game args: plain flags only (`validate.ARG`: no values, spaces or shell characters).
- Writes are atomic (temp file + os.replace), all-or-nothing, never while the game runs.
  Backups are per key, never whole files.
- Paths from data go through `safe_path` + `files.allowed` (prefix, install dir, or `~/.local/share`
  outside Steam's folder, never the whole home); files are opened with O_NOFOLLOW.
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
IN: game list (games with an entry), 3 profiles + Default (per device, borrowable by other devices), per-game env and game args, per-game XML/INI/JSON/LSX config keys,
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
keys out of entries. A profile's `resolution` ("WIDTHxHEIGHT") is shown only (Profile dropdown's
description), never written. Upscaler/frame generation stay in profiles where the game reads them from the
file; where it doesn't (Hogwarts Legacy), the user sets them in the menu.
OUT (maintainer decision, 0.6.0): the Uncapped profile (without the cap it was Performance again;
`test_uncapped_is_gone`). A setting with it applied from an older version still restores with Default.
OUT (maintainer decision, 0.6.0): FPS cap, of any kind. Steam's QAM frame limit works for every game
(native, Vulkan/OpenGL under Proton included), changes without leaving the game and has per-game
profiles; Loadout's DXVK/VKD3D env cap didn't reach native or Vulkan/OpenGL games, needed a native-game
heuristic and a switch to stay out of Steam's way. Profiles only show their target FPS. Launch options
stay for per-game env and args; a block with a cap from 0.5.0 or older is removed by the next apply
(`test_cap_block_from_an_older_version_is_removed`). Games without an entry are no longer listed
(nothing to set), except while a profile from an older version is applied. What was learned, in case
it comes back: Proton 11.0's DXVK ignores `DXVK_FRAME_RATE` and reads `DXVK_CONFIG=dxgi.maxFrameRate=N;
d3d9.maxFrameRate=N` (seen capping D3D9 Space Marine and D3D11 Crysis 3); its VKD3D reads
`VKD3D_FRAME_RATE` (seen capping D3D12 Cyberpunk 2077). Gamescope's `GAMESCOPE_FPS_LIMIT` atom or
`$MANGOHUD_CONFIGFILE` would fight Steam's own limiter. MangoHud via env (tested on a ROG Xbox Ally):
`MANGOHUD=1 MANGOHUD_CONFIG=fps_limit=N,no_display` capped native Vulkan, did nothing on OpenGL, ELDEN
RING (Proton) didn't start with it, and it overrides the QAM performance overlay (gamescope#1800).

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
- Baldur's Gate 3 (native Linux build): it saves `graphicSettings.lsx` when leaving the options
  menu, and reads it on launch (seen on device: after Quality the menu showed its values and the
  preset as Custom, though the profile doesn't set `CurrentSettings`). Not confirmed: that a
  stale preset name never makes it re-apply that preset. Players who force Proton have the file
  in the prefix (`AppData/Local/Larian Studios/...`): the entry doesn't cover them.
- Which field a JSON game reads: Cyberpunk reads `index` for fixed lists (seen on device: `value`
  alone was ignored) and `value` for dynamic ones (FSR2, QuickPresets). The entry sets both for
  fixed lists; `test_bundled_cyberpunk_sets_index_with_every_list_value` keeps them in sync.
- The Witcher 3 (DX12, the only renderer its launcher offers now): reads `dx12user.settings` on
  launch (seen on device: the Low snapshot written over a Medium file showed Low and FSR Auto in the
  menu, and the game rewrote the same bytes). The cloud syncs only the DX11 `user.settings`. Its
  "Steam Deck" preset wrote the same file as Low. The Deck blocks set `SteamDeck=0` (ProtonDB
  reports: with Steam's `SteamDeck=1` the game locks its graphics settings; `ENV_EXACT` allows that
  one mixed-case name). Not tested on a Deck. Steam didn't set `SteamDeck` at all for the game on the
  ROG Xbox Ally (env read from the running process), so the Ally block leaves it out.
  Every menu option was mapped to its keys on device (one change at a time). A section whose only
  key is at its default disappears with it (`[Rendering/DRS]` with dynamic resolution off,
  `[Streaming/Textures]` with textures Ultra+), so the entry leaves those keys out (inicfg won't add
  a section). Ray tracing options are greyed out under Proton. Not confirmed: that every profile
  holds its target FPS.
- Skyrim Special Edition: graphics only in its launcher, which writes `SkyrimPrefs.ini` (no BOM,
  CRLF) when the Options window is closed with OK (Advanced's OK alone writes nothing). The four
  presets were snapshotted on device (auto-detected Ultra = picked Ultra, byte for byte;
  `Skyrim.ini` never changed); Godrays mapped one change at a time (Off 0/0, Low 1/0, Medium 1/1,
  High 1/2 for `bVolumetricLightingEnable`/`iVolumetricLightingQuality`). Each launcher option
  only touched its own keys, so the profiles combine preset snapshots with those values.
  The game reads the file and rewrites it while running, keeping the profile's values (seen on
  device with Quality) and adding its own keys (`iVSyncPresentInterval`, `[Bethesda.net]`, ...).
  Anniversary Edition is DLC on the same app (489830); the original Skyrim (72850) is not covered.
  With `SteamDeck=1` (Deck) the game skips the launcher and uses its own settings (GamingOnLinux,
  Dec 2023); the Deck blocks set `SteamDeck=0`. Not tested on a Deck.

## Code style
- Never use tool or plugin names (e.g. "ponytail") as comment prefixes. Write plain comments.

## Git
- Commit messages (written for the maintainer or committed by an agent) never carry a
  `Co-Authored-By:` or any other attribution trailer.

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
