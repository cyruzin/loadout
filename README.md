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
  - **Verified on this device** (default): games with a Loadout entry that has profiles for your
    device.
  - **All Loadout games**: also entries with profiles for other devices only, marked
    "(other devices)", and any game with a profile applied, even a generic one.
  - **All games**: also every other installed game, marked "(generic)" (FPS cap only).

  For a selected game that isn't verified on your device, the **Game** dropdown says what a
  profile does there: "Other devices" (profiles exist for other devices only) or "Generic" (no
  Loadout settings, FPS cap only).

  When a filter matches more than 50 games (a big library, or lots of verified games), only the 50
  most recently played are listed (plus the running game and any game with a profile applied),
  with a note saying so, and a **Search games** field (opens the on-screen keyboard) finds any
  other game in that filter by name.

  When the panel opens it shows the last game you applied a profile to (remembered
  across Steam and Decky restarts), else the game that's running.

  Games with a profile applied show it next to the name (e.g. "Crysis 3 (generic) · Performance").
  If the filter hides such a game, a note lists it so it can still be set back to Default.
- Applies a profile by writing a managed block to the game's launch options, e.g.

  ```
  LOADOUT_BEGIN=1 DXVK_FRAME_RATE=40 DXVK_CONFIG='dxgi.maxFrameRate=40;d3d9.maxFrameRate=40' VKD3D_FRAME_RATE=40 LOADOUT_END=1 %command% -novid
  ```

  Game arguments from an entry go right after `%command%` and are recorded in the block
  (`LOADOUT_ARGS=--launcher-skip`), so Default removes them too.

  Your own launch options are kept. Switching profiles never stacks; Default restores your original
  string exactly (or, if you edited it meanwhile, removes only the Loadout block).
- Profiles are per device, so each device's graphics can be tuned on its own. When a game has no
  profiles for your device, **Use profiles from** lists the devices it has them for: pick one with a
  similar chip (a ROG Ally X can start from the ROG Xbox Ally's). Until you pick one, the profiles
  only set the FPS cap. The FPS cap always comes from your own device's table.
- Each game has an **Apply the profile's N FPS cap** switch (on by default; shown for Quality,
  Balanced and Performance with the cap from your device's table). Off, the profile only changes
  the game's settings and you set the frame limit in Steam's Quick Access Menu, which you can
  change without leaving the game. Flipping it re-applies the current profile (with the usual
  confirmation).
- Edits in-game graphics settings for games that have a data entry: XML configs (e.g. ELDEN
  RING's `GraphicsConfig.xml` in the Proton prefix), INI configs (e.g. Lies of P's Unreal
  Engine `GameUserSettings.ini` in the install folder) and JSON configs (e.g. Cyberpunk 2077's
  `UserSettings.json`). Only the listed keys change, each original
  value is backed up, writes are atomic and all-or-nothing, and nothing is written while the game runs
  (the confirmation asks you to close it). Default puts every key back unless the game changed it
  since.
- Never acts on its own: nothing runs when a game starts or exits. Settings you change in the game's
  menu stay as you set them until you apply a profile again (the diff shows what that would change).
- Shows a dry-run diff and asks for confirmation before changing anything.
- Detects the device from `/sys/class/dmi/id/product_name` (Steam Deck LCD/OLED, ROG Ally and
  Legion Go families bundled; anything else falls back to a generic table) and asks you to confirm
  it on first run. After that the panel only shows it (**Device**, first in the panel).
- **Reset Loadout** (under **Settings**, after a confirmation listing the affected games) applies
  Default (original) to every game with a profile, then clears Loadout's settings so Setup asks for
  the device again. The confirmation names the 10 most recently played (and how many more); the
  panel shows the progress ("Resetting 3 of 20: …"). It's blocked while one of those games is
  running, and stops without clearing anything if a game can't be restored.
- Shows the result of every apply in the panel itself (Steam can play a toast's sound without
  showing it while the Quick Access Menu is open).
- Launch-option changes (FPS cap, env vars, game arguments) apply the next time the game launches.

**FPS cap:** uses the DXVK/VKD3D frame limiters, so it works for Direct3D games running under
Proton. Native Linux games (OpenGL or Vulkan) are not capped: use Steam's per-game profile in the
Quick Access Menu (Performance → Use per-game profile → Frame limit) for those.

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
`py_modules/loadout/data/games/` with profiles for your device (or one you picked under
**Use profiles from**):

| | Entry with profiles for your device (e.g. ELDEN RING) | Any other game ("generic"), or an entry for other devices with none picked |
|---|---|---|
| FPS cap from the device table | yes | yes |
| Per-game env vars (e.g. `MESA_VK_WSI_PRESENT_MODE`) | yes | no |
| Per-game launch arguments (e.g. `--launcher-skip`) | yes | no |
| In-game graphics settings (config file edits) | yes, where the entry defines them | no |

In short: **without profiles for your device, a profile only applies the FPS cap.** Graphics stay as
you set them in the game, and Uncapped simply removes Loadout's cap. That is why the game list
shows only verified games by default; pick **All games** in the Show filter to use the generic cap
on the rest. See [CONTRIBUTING.md](CONTRIBUTING.md) to contribute an entry or your device's profiles.

### Supported games

ELDEN RING, Lies of P, Cyberpunk 2077, Hogwarts Legacy and Crysis 3 Remastered have game-specific entries. What each
profile sets per game, and which devices it has profiles for: [GAMES.md](GAMES.md).

### Not included

- Not yet: community data repo download, global/batch profiles,
  export/import.
- Out of scope: TDP and other power settings. Use the Steam Quick Access Menu for those.
- Out of scope since 0.3.1: the game's resolution. It was removed because it's easy to change
  in the game's own menu. If you picked a resolution in Loadout 0.3.0, applying a profile with
  the game closed puts the original back.

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
scripts/capture.py         records which config keys a game changes (draft entry for CONTRIBUTING)
.github/workflows/         tag-triggered release
GAMES.md                   supported games and what each profile sets
CONTRIBUTING.md            how to verify/add games and devices
AGENTS.md                  rules for coding agents
```

## Contributing

Game and device data come from people testing on real hardware. [CONTRIBUTING.md](CONTRIBUTING.md)
has the step-by-step for:

- **adding your device to an existing game** (its own profiles, tuned higher or lower), which
  moves it to the default "Verified on this device" list for everyone with that device;
- adding a new game (finding its config file, mapping menu options to file values, writing the
  entry, testing every profile);
- adding a new device (DMI string, panel, FPS caps).

## License

[BSD-3-Clause](LICENSE). Based on the
[Decky plugin template](https://github.com/SteamDeckHomebrew/decky-plugin-template) (BSD-3-Clause, Steam Deck Homebrew).
