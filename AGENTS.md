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
  - `inicfg.py` INI read/set by `[Section]Key`, same byte-preserving approach; duplicated keys refused
  - `files.py` per-key file plan (read-only) + all-or-nothing apply with rollback
  - `launch.py` marker-delimited launch-option block (build / strip / restore)
  - `planner.py` pure `build_plan` (dry-run, never writes)
  - `devices.py` DMI detection, device table, level fallback chain
  - `steam.py` libraryfolders.vdf / appmanifest parsing, per-game prefix/install paths
  - `store.py` `atomic_write` + JSON files (settings = intent, state = backups)
  - `data/devices/*.json` bundled device tables (`generic.json` is required)
  - `data/games/<appid>.json` bundled per-game data (device-independent)
- `src/api.ts` typed `callable()` wrappers + Steam launch-option access. `src/index.tsx` UI.
  The QAM panel remounts (e.g. when a dropdown menu opens), which wipes `useState`: keep UI state
  in `useKept` (module-level store in `index.tsx`), never plain `useState`. Dropdowns use
  `layout="below"` so long values aren't cut off.

## Commands
    pnpm install && pnpm run build     # frontend -> dist/index.js
    pnpm run typecheck                 # tsc --noEmit
    .venv/bin/python -m pytest -q      # backend tests
    scripts/package.sh                 # out/Loadout.zip (release: push a vX.Y.Z tag)

## Security rules (non-negotiable)
- Validate data structurally and semantically before use. Unknown fields are rejected.
- Never use str.format, eval, exec, pickle, yaml.load or shell=True with data.
- Env vars: allowlist prefixes + denylist; values quoted with shlex.quote in launch options.
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
IN: game list, 4 profiles + Default, FPS cap (DXVK/VKD3D env), per-game env, per-game XML/INI config keys,
launch options, settings file,
device detection, preferred render resolution.
LATER (do not build unless asked): community data download + SHA-256, JSON config handler,
Wine registry, global/batch profile, export/import.
OUT (maintainer decision): TDP and other power settings; the user handles those in Steam's QAM.

## Known unknowns (do NOT guess; flag them)
- Steam frontend APIs (`SteamClient.Apps.*`) are not a public contract.
- DMI `product_name` for ROG Ally and Legion Go families: taken from Handheld Daemon
  (github.com/hhd-dev/hhd), not yet confirmed on our own hardware. Some original Legion Go units
  report no valid product_name (HHD falls back to BIOS version); those must pick the device manually.
- How to set (not just declare) the render resolution (`SetAppResolutionOverride` is a candidate).

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
