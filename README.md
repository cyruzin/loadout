# Loadout

A [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin that applies one-click
per-game, console-style profiles — **Quality**, **Balanced**, **Performance**, **Uncapped** — and can
always return a game to **Default (original)**: exactly what you had before Loadout touched it.

Targets SteamOS first; Bazzite, CachyOS and other Linux distros running Steam Game Mode + Decky
should work too.

## What the MVP does

- Lists installed Steam games by reading `libraryfolders.vdf` and `appmanifest_*.acf` (all libraries,
  including SD cards). Proton/runtime tools are always hidden. A **Show** filter picks which games
  are listed (saved in settings):
  - **Verified on this device** (default): games with a Loadout entry whose `verified` list
    includes your device.
  - **All Loadout games**: also entries not verified on your device, marked "(untested)".
  - **All games**: also every other installed game, marked "(generic)" (FPS cap only).

  When a filter matches more than 50 games (a big library, or lots of verified games), only the 50
  most recently played are listed (plus the running game and any game with a profile applied),
  with a note saying so, and a **Search games** field (opens the on-screen keyboard) finds any
  other game in that filter by name.

  When the panel opens it shows the last game you applied a profile or resolution to (remembered
  across Steam and Decky restarts), else the game that's running.

  Games with a profile applied show it next to the name (e.g. "Crysis 3 (generic) · Performance").
  If the filter hides such a game, a note lists it so it can still be set back to Default.
- Applies a profile by writing a managed block to the game's launch options, e.g.

  ```
  LOADOUT_BEGIN=1 DXVK_FRAME_RATE=40 VKD3D_FRAME_RATE=40 LOADOUT_END=1 %command% -novid
  ```

  Your own launch options are kept. Switching profiles never stacks; Default restores your original
  string exactly (or, if you edited it meanwhile, removes only the Loadout block).
- Edits in-game graphics settings for games that have a data entry: XML configs (e.g. ELDEN
  RING's `GraphicsConfig.xml` in the Proton prefix) and INI configs (e.g. Lies of P's Unreal
  Engine `GameUserSettings.ini` in the install folder). Only the listed keys change, each original
  value is backed up, writes are atomic and all-or-nothing, and nothing is written while the game runs
  (the confirmation asks you to close it). Default puts every key back unless the game changed it
  since.
- Never acts on its own: nothing runs when a game starts or exits. Settings you change in the game's
  menu stay as you set them until you apply a profile again (the diff shows what that would change).
- Shows a dry-run diff and asks for confirmation before changing anything.
- Detects the device from `/sys/class/dmi/id/product_name` (Steam Deck LCD/OLED, ROG Ally and
  Legion Go families bundled; anything else falls back to a generic table) and asks you to confirm
  it on first run.
- Sets the game's resolution, for games whose entry says where it is stored (both bundled games),
  only when you pick one in **Resolution for this game**. The default, **Keep the game's
  setting**, never touches it: the game and Steam's own game-resolution setting decide. Picking a
  resolution writes it right away and leaves the applied profile as it is (game closed, like any
  config change); going back to Keep restores the original, and so does Default. Choices go up to
  the display's maximum, read from `/sys/class/drm` (built-in panel, or the external display when
  docked) and shown under Device as **Display max**; that's the screen's highest mode, not the
  output resolution set in Steam. The width follows the screen's aspect ratio: 720p is 1280×720
  on a 16:9 ROG Ally and 1152×720 on a 16:10 Steam Deck. If a picked resolution no longer fits
  after docking or undocking, the panel says so and **Update resolution** rewrites it.
- Shows the result of every apply in the panel itself (Steam can play a toast's sound without
  showing it while the Quick Access Menu is open).
- Launch-option changes (FPS cap, env vars) apply the next time the game launches.

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
| Game resolution written to the game's config | when you pick one, where the entry maps it | no |

In short: **without a game-specific entry, a profile only applies the FPS cap.** Graphics stay as
you set them in the game, and Uncapped simply removes Loadout's cap. That is why the game list
shows only verified games by default; pick **All games** in the Show filter to use the generic cap
on the rest. See [CONTRIBUTING.md](CONTRIBUTING.md) to contribute an entry.

### Bundled games

| Game | Verified on | Quality | Balanced | Performance / Uncapped |
|---|---|---|---|---|
| ELDEN RING (1245620) | all bundled devices (tested on ROG Xbox Ally) | tuned graphics (high textures/AA, low shadows, motion blur off) | device cap only | every graphics option at its lowest |
| Lies of P (1627720) | all bundled devices (tested on ROG Xbox Ally) | everything Medium | Medium; shading, shadows, reflections, fog, AO Low | everything Low |

The FPS cap always comes from the device table above. All ELDEN RING profiles also set
`MESA_VK_WSI_PRESENT_MODE=immediate`. All Lies of P profiles keep textures at Medium and
anisotropic filtering at Maximum (cheap, big visual win), use FSR 3 Quality with 0.7 sharpness and
CACAO, and turn off the game's own frame limit and VSync so Loadout's cap is the only limiter.

### Not included

- Not yet: community data repo download, JSON config files, global/batch profiles,
  export/import.
- Out of scope: TDP and other power settings. Use the Steam Quick Access Menu for those.

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

1. Bump `version` in `package.json` (e.g. `X.Y.Z`) and commit.
2. Tag and push:

   ```bash
   git tag vX.Y.Z
   git push origin main vX.Y.Z
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
CONTRIBUTING.md            how to verify/add games and devices
AGENTS.md                  rules for coding agents
```

## Contributing

Game and device data come from people testing on real hardware. [CONTRIBUTING.md](CONTRIBUTING.md)
has the step-by-step for:

- **verifying an existing game on your device**, which moves it to the default
  "Verified on this device" list for everyone with that device;
- adding a new game (finding its config file, mapping menu options to file values, writing the
  entry, testing every profile);
- adding a new device (DMI string, panel, FPS caps).

## License

[BSD-3-Clause](LICENSE). Based on the
[Decky plugin template](https://github.com/SteamDeckHomebrew/decky-plugin-template) (BSD-3-Clause, Steam Deck Homebrew).
