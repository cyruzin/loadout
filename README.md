# Loadout

A [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin that applies one-click
per-game, console-style profiles — **Quality**, **Balanced**, **Performance** — and can
always return a game to **Default (original)**: exactly what you had before Loadout touched it.

Targets SteamOS first; Bazzite, CachyOS and other Linux distros running Steam Game Mode + Decky
should work too.

## What the MVP does

- Lists installed Steam games that have a Loadout entry, by reading `libraryfolders.vdf` and
  `appmanifest_*.acf` (all libraries, including SD cards). A **Show** filter picks which ones
  (saved in settings):
  - **Verified on this device** (default): entries with profiles for your device.
  - **All Loadout games**: also entries with profiles for other devices only, marked
    "(other devices)", and any game with a profile applied (e.g. an FPS cap set by Loadout 0.5.0
    or older on a game without an entry, marked "(no settings)"), so it can be set back to Default.

  For a selected game that isn't verified on your device, the **Game** dropdown says why.

  When a filter matches more than 50 games, only the 50 most recently played are listed (plus the
  running game and any game with a profile applied), with a note saying so, and a **Search games**
  field (opens the on-screen keyboard) finds any other game in that filter by name.

  When the panel opens it shows the last game you applied a profile to (remembered
  across Steam and Decky restarts), else the game that's running.

  Games with a profile applied show it next to the name (e.g. "Crysis 3 Remastered · Performance").
  If the filter hides such a game, a note lists it so it can still be set back to Default.
- Edits in-game graphics settings: XML configs (e.g. ELDEN RING's `GraphicsConfig.xml` in the
  Proton prefix), INI configs (e.g. Lies of P's Unreal Engine `GameUserSettings.ini` in the install
  folder), JSON configs (e.g. Cyberpunk 2077's `UserSettings.json`) and Larian's LSX configs
  (Baldur's Gate 3's native `graphicSettings.lsx` in `~/.local/share`; never elsewhere in your home,
  never Steam's own folder). Only the listed keys
  change, each original value is backed up, writes are atomic and all-or-nothing, and nothing is
  written while the game runs (the confirmation asks you to close it). Default puts every key back
  unless the game changed it since.
- Profiles are per device, so each device's graphics can be tuned on its own. When a game has no
  profiles for your device, **Use profiles from** lists the devices it has them for: pick one with a
  similar chip (a ROG Ally X can start from the ROG Xbox Ally's). Until you pick one, nothing is set.
  The **Profile** dropdown only lists the profiles a device has: an entry leaves out one the device
  can't reach the target FPS with (e.g. Performance on a game that doesn't run at 60).
- **No FPS cap.** Each profile is made for a frame rate and a resolution, and the **Profile**
  dropdown says which ("Made for 40 FPS at 1280×720"): set the frame limit in Steam's Quick Access
  Menu (Performance → Frame limit, per game with "Use per-game profile") and the resolution in the
  game's menu. Steam's limiter works for every game and can be changed without leaving it. The
  target FPS comes from your device's table (below). There's no Uncapped profile since 0.6.0: it
  was Performance's graphics without Loadout's cap; to play uncapped, turn Steam's frame limit off.
- Where an entry needs them, writes per-game env vars and launch arguments to a managed block in
  the game's launch options, e.g. ELDEN RING's

  ```
  LOADOUT_BEGIN=1 MESA_VK_WSI_PRESENT_MODE=immediate LOADOUT_END=1 %command% -novid
  ```

  Game arguments go right after `%command%` and are recorded in the block
  (`LOADOUT_ARGS=--launcher-skip`, Cyberpunk 2077), so Default removes them too. Your own launch
  options are kept. Switching profiles never stacks; Default restores your original string exactly
  (or, if you edited it meanwhile, removes only the Loadout block). A block from Loadout 0.5.0 or
  older (with its FPS cap) is removed the next time you apply a profile or Default to that game.
- Never acts on its own: nothing runs when a game starts or exits. Settings you change in the game's
  menu stay as you set them until you apply a profile again (the diff shows what that would change).
- Asks for confirmation before changing anything, with a plain summary (how many game settings
  change, the target FPS and resolution) and the full dry-run diff under **Show details** (env
  vars, each config key old → new, launch options before/after).
- Detects the device from `/sys/class/dmi/id/product_name` (Steam Deck LCD/OLED, ROG Ally and
  Legion Go families bundled; anything else falls back to the generic table, whose games start
  under **All Loadout games** and borrow profiles with **Use profiles from**). Nothing to set up:
  the panel opens on your games and only shows the device (**Device**, first in the panel).
- **Reset Loadout** (under **Settings**, after a confirmation listing the affected games) applies
  Default (original) to every game with a profile, then clears Loadout's settings. The
  confirmation names the 10 most recently played (and how many more); the panel shows the progress ("Resetting 3 of 20: …"). It's blocked while one of those games is
  running, and stops without clearing anything if a game can't be restored.
- Shows the result of every apply in the panel itself (Steam can play a toast's sound without
  showing it while the Quick Access Menu is open).
- Launch-option changes (env vars, game arguments) apply the next time the game launches.

Target FPS per profile (what each device's profiles are made for; set it as Steam's frame limit):

| Device                          | Panel              | Quality | Balanced | Performance |
|---------------------------------|--------------------|---------|----------|-------------|
| Steam Deck LCD                  | 1280×800, 60 Hz    | 30      | 40       | 60          |
| Steam Deck OLED                 | 1280×800, 90 Hz    | 30      | 45       | 90          |
| ROG Ally                        | 1920×1080, 120 Hz  | 30      | 40       | 60          |
| ROG Ally X                      | 1920×1080, 120 Hz  | 30      | 40       | 60          |
| ROG Xbox Ally                   | 1920×1080, 120 Hz  | 30      | 40       | 60          |
| ROG Xbox Ally X                 | 1920×1080, 120 Hz  | 30      | 40       | 60          |
| ROG Xbox Ally X20¹              | 1920×1080, 120 Hz  | 30      | 40       | 60          |
| Lenovo Legion Go                | 2560×1600, 144 Hz  | 36      | 48       | 72          |
| Lenovo Legion Go 2              | 1920×1200, 144 Hz  | 36      | 48       | 72          |
| Lenovo Legion Go S              | 1920×1200, 120 Hz  | 30      | 40       | 60          |
| Generic / other                 | —                  | 30      | 40       | 60          |

Targets divide the panel refresh rate evenly (e.g. 40 FPS on 120 Hz, 48 FPS on 144 Hz) to keep
frame pacing smooth.

¹ X20 support is early.

Values live in `py_modules/loadout/data/devices/*.json` (`fps_limit` per profile: the target shown).

### Supported games

ELDEN RING, Lies of P, Cyberpunk 2077, Hogwarts Legacy, Crysis 3 Remastered and Baldur's Gate 3
(native Linux build) have game-specific entries. What each
profile sets per game, and which devices it has profiles for: [GAMES.md](GAMES.md).

### Not included

- Not yet: community data repo download, global/batch profiles,
  export/import.
- Out of scope: TDP and other power settings, and (since 0.6.0) the FPS cap. Use the Steam Quick
  Access Menu for those.
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
- adding a new device (DMI string, panel, target FPS).

## License

[BSD-3-Clause](LICENSE). Based on the
[Decky plugin template](https://github.com/SteamDeckHomebrew/decky-plugin-template) (BSD-3-Clause, Steam Deck Homebrew).
