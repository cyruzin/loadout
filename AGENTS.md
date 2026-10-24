# AGENTS.md - Loadout

A Decky Loader plugin (SteamOS first; Bazzite/CachyOS best effort) that applies per-game profiles
(Performance, Balanced, Quality, Battery) and returns a game to "Default (original)".
The plugin is an ENGINE; JSON files are DATA. Data can never contain code.

## Layout
- `main.py` - thin Decky adapter. The only file that imports `decky`.
- `py_modules/loadout/` - pure core (never imports `decky`):
  - `validate.py` device-doc schema + env allow/deny rules
  - `launch.py` marker-delimited launch-option block (build / strip / restore)
  - `planner.py` pure `build_plan` (dry-run, never writes)
  - `devices.py` DMI detection, device table, level fallback chain
  - `steam.py` libraryfolders.vdf / appmanifest parsing
  - `store.py` atomic JSON files (settings = intent, state = backups)
  - `data/devices/*.json` bundled device tables (`generic.json` is required)
- `src/api.ts` typed `callable()` wrappers + Steam launch-option access. `src/index.tsx` UI.

## Commands
    pnpm install && pnpm run build     # frontend -> dist/index.js
    pnpm run typecheck                 # tsc --noEmit
    .venv/bin/python -m pytest -q      # backend tests

## Security rules (non-negotiable)
- Validate data structurally and semantically before use. Unknown fields are rejected.
- Never use str.format, eval, exec, pickle, yaml.load or shell=True with data.
- Env vars: allowlist prefixes + denylist; values quoted with shlex.quote in launch options.
- Writes are atomic (temp file + os.replace). Backups are per key, never whole files.
- No root (`plugin.json` flags are empty). No compiled Python deps.
- Never invent device or game values; every data entry needs a real source.

## Scope
IN: game list, 4 profiles + Default, FPS cap (DXVK/VKD3D env), launch options, settings file,
device detection, preferred render resolution.
LATER (do not build unless asked): community data download + SHA-256, per-game config files
(ini/json), TDP, global/batch profile, export/import.

## Known unknowns (do NOT guess; flag them)
- Steam frontend APIs (`SteamClient.Apps.*`) are not a public contract.
- DMI `product_name` for devices other than Steam Deck (Jupiter/Galileo).
- How to set (not just declare) the render resolution (`SetAppResolutionOverride` is a candidate).

## Code style
- Never use tool or plugin names (e.g. "ponytail") as comment prefixes. Write plain comments.

## Definition of done
Tests pass, typecheck clean, no `decky` import under `py_modules/loadout/`, docs updated.
