# Loadout

A [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin that applies one-click
per-game profiles — **Performance**, **Balanced**, **Quality**, **Battery** — and can always return a
game to **Default (original)**: exactly what you had before Loadout touched it.

Targets SteamOS first; Bazzite, CachyOS and other Linux distros running Steam Game Mode + Decky
should work too.

## What the MVP does

- Lists installed Steam games by reading `libraryfolders.vdf` and `appmanifest_*.acf` (all libraries,
  including SD cards). Proton/runtime tools are hidden.
- Applies a profile by writing a managed block to the game's launch options, e.g.

  ```
  LOADOUT_BEGIN=1 DXVK_FRAME_RATE=40 VKD3D_FRAME_RATE=40 LOADOUT_END=1 %command% -novid
  ```

  Your own launch options are kept. Switching profiles never stacks; Default restores your original
  string exactly (or, if you edited it meanwhile, removes only the Loadout block).
- Shows a dry-run diff and asks for confirmation before changing anything.
- Detects the device from `/sys/class/dmi/id/product_name` (Steam Deck LCD/OLED bundled; anything
  else falls back to a generic table) and asks you to confirm it on first run.
- Lets you pick a preferred render resolution, globally and per game.
- Changes apply the next time the game launches.

**FPS cap:** uses the DXVK/VKD3D frame limiters, so it works for Direct3D games running under
Proton. Native Linux, OpenGL and native Vulkan games are not capped (yet).

| Profile     | Steam Deck LCD | Steam Deck OLED | Generic  |
|-------------|----------------|-----------------|----------|
| Performance | 60 FPS         | 90 FPS          | uncapped |
| Balanced    | 45 FPS         | 60 FPS          | 60 FPS   |
| Quality     | 40 FPS         | 45 FPS          | 45 FPS   |
| Battery     | 30 FPS         | 30 FPS          | 30 FPS   |

Values live in `py_modules/loadout/data/devices/*.json`.

Not in the MVP yet: community data repo download, per-game config file edits (ini/json), TDP,
global/batch profiles, export/import.

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
Backups of your original launch options: `~/homebrew/data/Loadout/state.json`.

The backend runs as your normal user (no root flag).

## Project layout

```
main.py                    Decky adapter (only file importing `decky`)
py_modules/loadout/        pure Python core + bundled device data
src/                       React/TypeScript frontend (@decky/ui, @decky/api)
tests/                     pytest suite
AGENTS.md                  rules for contributors and coding agents
```

## Adding a device

Create `py_modules/loadout/data/devices/<id>.json` (see `steam-deck-lcd.json`). Put the exact
`product_name` your device reports (`cat /sys/class/dmi/id/product_name`) — confirm it on real
hardware, don't guess. Run the tests; invalid files fail validation.

## License

[BSD-3-Clause](LICENSE). Based on the
[Decky plugin template](https://github.com/SteamDeckHomebrew/decky-plugin-template) (BSD-3-Clause, Steam Deck Homebrew).
