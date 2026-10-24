# Loadout

A [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin that applies one-click
per-game, console-style profiles — **Quality**, **Balanced**, **Performance**, **Uncapped** — and can
always return a game to **Default (original)**: exactly what you had before Loadout touched it.

Targets SteamOS first; Bazzite, CachyOS and other Linux distros running Steam Game Mode + Decky
should work too.

## What the MVP does

- Lists installed Steam games by reading `libraryfolders.vdf` and `appmanifest_*.acf` (all libraries,
  including SD cards). By default only games with Loadout settings (`data/games/`) are shown, plus
  any game that currently has a profile applied; **Show all games** lists the rest as "(generic)",
  which only get the device FPS cap. Proton/runtime tools are always hidden.
- Applies a profile by writing a managed block to the game's launch options, e.g.

  ```
  LOADOUT_BEGIN=1 DXVK_FRAME_RATE=40 VKD3D_FRAME_RATE=40 LOADOUT_END=1 %command% -novid
  ```

  Your own launch options are kept. Switching profiles never stacks; Default restores your original
  string exactly (or, if you edited it meanwhile, removes only the Loadout block).
- Edits in-game graphics settings for games that have a data entry (XML configs inside the Proton
  prefix, e.g. ELDEN RING's `GraphicsConfig.xml`). Only the listed keys change, each original value
  is backed up, writes are atomic and all-or-nothing, and nothing is written while the game runs.
  Default puts every key back unless the game changed it since.
- Shows a dry-run diff and asks for confirmation before changing anything.
- Detects the device from `/sys/class/dmi/id/product_name` (Steam Deck LCD/OLED, ROG Ally and
  Legion Go families bundled; anything else falls back to a generic table) and asks you to confirm
  it on first run.
- Lets you pick a preferred render resolution, globally and per game.
- Changes apply the next time the game launches.

**FPS cap:** uses the DXVK/VKD3D frame limiters, so it works for Direct3D games running under
Proton. Native Linux, OpenGL and native Vulkan games are not capped (yet).

| Device                          | Panel              | Quality | Balanced | Performance | Uncapped |
|---------------------------------|--------------------|---------|----------|-------------|----------|
| Steam Deck LCD                  | 1280×800, 60 Hz    | 30      | 40       | 60          | no cap   |
| Steam Deck OLED                 | 1280×800, 90 Hz    | 30      | 45       | 90          | no cap   |
| ROG Ally                        | 1920×1080, 120 Hz  | 30      | 40       | 60          | no cap   |
| ROG Ally X                      | 1920×1080, 120 Hz  | 30      | 40       | 60          | no cap   |
| ROG Xbox Ally                   | 1920×1080, 120 Hz  | 30      | 40       | 60          | no cap   |
| ROG Xbox Ally X                 | 1920×1080, 120 Hz  | 30      | 40       | 60          | no cap   |
| ROG Xbox Ally X20¹              | 1920×1080, 120 Hz  | 30      | 40       | 60          | no cap   |
| Lenovo Legion Go                | 2560×1600, 144 Hz  | 36      | 48       | 72          | no cap   |
| Lenovo Legion Go 2              | 1920×1200, 144 Hz  | 36      | 48       | 72          | no cap   |
| Lenovo Legion Go S              | 1920×1200, 120 Hz  | 30      | 40       | 60          | no cap   |
| Generic / other                 | —                  | 30      | 40       | 60          | no cap   |

Caps divide the panel refresh rate evenly (e.g. 40 FPS on 120 Hz, 48 FPS on 144 Hz) to keep frame
pacing smooth.

¹ X20 support is early.

Values live in `py_modules/loadout/data/devices/*.json`.

### Game-specific vs. generic profiles

What a profile does depends on whether the game has a Loadout entry in
`py_modules/loadout/data/games/`:

| | Game with a Loadout entry (e.g. ELDEN RING) | Any other game ("generic") |
|---|---|---|
| FPS cap from the device table | yes | yes |
| Per-game env vars (e.g. `MESA_VK_WSI_PRESENT_MODE`) | yes | no |
| In-game graphics settings (config file edits) | yes, where the entry defines them | no |

In short: **without a game-specific entry, a profile only applies the FPS cap.** Graphics stay as
you set them in the game, and Uncapped simply removes Loadout's cap. That is why the game list
shows only games with an entry by default; turn on **Show all games** to use the generic cap on
the rest. See [Adding a game](#adding-a-game) to contribute an entry.

Not in the MVP yet: community data repo download, ini/json config files, TDP, global/batch profiles,
export/import.

## Requirements

- Node.js 18+ and [pnpm](https://pnpm.io) 9+ (or run it through `npx pnpm@10`)
- Python 3.9+ (only to run the tests; the plugin uses Decky's bundled Python)
- A device with [Decky Loader](https://decky.xyz) installed

## Build

```bash
pnpm install
pnpm run build        # outputs dist/index.js
pnpm run typecheck
```

## Test

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

## Install on a device (development)

The plugin folder needs `plugin.json`, `package.json`, `main.py`, `dist/` and `py_modules/`.
From your computer (replace `deck@steamdeck` with your user/host; enable SSH on the device first):

```bash
pnpm run build
rsync -av --delete plugin.json package.json main.py dist py_modules deck@steamdeck:/tmp/Loadout/
ssh -t deck@steamdeck 'sudo rm -rf ~/homebrew/plugins/Loadout && sudo mv /tmp/Loadout ~/homebrew/plugins/Loadout && sudo systemctl restart plugin_loader'
```

Then open the Quick Access Menu (`…` button) → Decky → **Loadout**.

Logs: `~/homebrew/logs/Loadout/`. Settings: `~/homebrew/settings/Loadout/settings.json`.
Backups of your original launch options and game config values: `~/homebrew/data/Loadout/state.json`.

The backend runs as your normal user (no root flag).

## Releasing

1. Bump `version` in `package.json` (e.g. `0.2.0`) and commit.
2. Tag and push:

   ```bash
   git tag v0.2.0
   git push origin main v0.2.0
   ```

The [Release workflow](.github/workflows/release.yml) runs the tests, builds `Loadout.zip` and
publishes it on the GitHub Releases page. The tag must match the `package.json` version.

To build the zip locally: `scripts/package.sh` (writes `out/Loadout.zip`).

Installing a release on a device: Decky → Settings → enable **Developer mode** → Developer →
**Install Plugin from ZIP File**. Download the zip first (Desktop Mode / Konsole or SSH):

```bash
curl -L -o ~/Downloads/Loadout.zip https://github.com/cyruzin/loadout/releases/latest/download/Loadout.zip
```

**Install Plugin from URL** can hang: for URL installs Decky also posts an install count to its
store server, with no timeout
([decky-loader#984](https://github.com/SteamDeckHomebrew/decky-loader/issues/984)). ZIP installs
skip that step.

After updating, restart the loader so the Quick Access panel doesn't keep the old UI
([decky-loader#976](https://github.com/SteamDeckHomebrew/decky-loader/issues/976)):

```bash
sudo systemctl restart plugin_loader
```

## Project layout

```
main.py                    Decky adapter (only file importing `decky`)
py_modules/loadout/        pure Python core
py_modules/loadout/data/   bundled device tables and per-game data
src/                       React/TypeScript frontend (@decky/ui, @decky/api)
tests/                     pytest suite
scripts/package.sh         builds out/Loadout.zip
.github/workflows/         tag-triggered release
AGENTS.md                  rules for contributors and coding agents
```

## Adding a game

Create `py_modules/loadout/data/games/<appid>.json` (see `1245620.json`, ELDEN RING). Each profile can:

- add allowlisted env vars to the launch options (per-game values win over device values);
- set keys in the game's XML config files. Paths must start with `{prefix}/` (the game's Proton
  prefix) or `{install_dir}/`, and keys must already exist in the file: copy them from a real
  config, never guess.

`options` lists the values each key accepts (copy them from the in-game menu; e.g. ELDEN RING
writes Off as `DISABLE` and Maximum as `MAX`). Profiles that set anything outside that list are
rejected.

Only define profiles that were actually tested: list each device in `verified` (Proton version,
device id, date) and link where the settings came from in `source`.

```json
{
  "schema_version": 1,
  "appid": 1245620,
  "name": "ELDEN RING",
  "verified": [
    { "proton": "default", "device": "rog-xbox-ally", "date": "2026-10-24" },
    { "proton": "default", "device": "steam-deck-lcd", "date": "2026-10-24" },
    { "proton": "default", "device": "steam-deck-oled", "date": "2026-10-24" }
  ],
  "options": {
    "{prefix}/drive_c/users/steamuser/AppData/Roaming/EldenRing/GraphicsConfig.xml": {
      "MotionBlur": ["DISABLE", "LOW", "MEDIUM", "HIGH"],
      "ShadowQuality": ["LOW", "MEDIUM", "HIGH", "MAX"]
    }
  },
  "profiles": {
    "quality": {
      "launch": { "env": { "MESA_VK_WSI_PRESENT_MODE": "immediate" } },
      "files": [{
        "path": "{prefix}/drive_c/users/steamuser/AppData/Roaming/EldenRing/GraphicsConfig.xml",
        "format": "xml",
        "set": { "MotionBlur": "DISABLE", "ShadowQuality": "LOW" }
      }]
    }
  }
}
```

## Adding a device

Create `py_modules/loadout/data/devices/<id>.json` (see `steam-deck-lcd.json`). In `match`, put a
distinctive part of what `cat /sys/class/dmi/id/product_name` prints on the device (matching is by
substring, since some vendors add per-unit suffixes). Confirm it on real hardware, don't guess.
Run the tests; invalid files fail validation.

## License

[BSD-3-Clause](LICENSE). Based on the
[Decky plugin template](https://github.com/SteamDeckHomebrew/decky-plugin-template) (BSD-3-Clause, Steam Deck Homebrew).
