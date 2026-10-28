# Contributing game and device data

Loadout is an engine; what it knows about each game and device lives in JSON files under
`py_modules/loadout/data/`. Most contributions are one of these:

1. [Add your device to an existing game](#1-add-your-device-to-an-existing-game): the
   easiest one. It moves the game from "(other devices)" to the default **Verified on this device**
   list for everyone with that device.
2. [Add a new game](#2-add-a-new-game).
3. [Add a new device](#3-add-a-new-device).

**Ground rule: never guess.** Every key, value and DMI string must come from a real file, the
in-game menu or real hardware. If you're unsure about something, leave it out and say so in the PR.

## Before you start

- A handheld or PC with SteamOS (or Bazzite, CachyOS, …) and [Decky Loader](https://decky.xyz).
- SSH or Konsole (Desktop Mode) on the device, for the commands below.
- On your computer: the [build and test setup](README.md#build) from the README.

Know your device id: it's the file name (without `.json`) in `py_modules/loadout/data/devices/`,
e.g. `steam-deck-oled` or `rog-xbox-ally`. The Loadout setup screen shows which one was detected.

## 1. Add your device to an existing game

The game already has `py_modules/loadout/data/games/<appid>.json`, but its `devices` has no block
for your device (Loadout shows it as "(other devices)" under **All Loadout games**). Each device has
its own block, so yours can set graphics higher or lower than the others without changing them.

1. Install the latest Loadout release (see [Installing a release](README.md#releasing)).
2. Under **Use profiles from**, pick the listed device closest to yours (e.g. `rog-xbox-ally` for a
   ROG Xbox Ally X20). Its profiles are your starting point.
3. Close the game. Apply each profile (Quality, Balanced, Performance, Uncapped) and, for each one:
   - read the confirmation diff: every key should change to the value in the JSON;
   - launch the game and check that the in-game menu shows those settings;
   - after launching, check the file again: some games overwrite values from their save on
     launch, and a key the game doesn't read from this file doesn't belong in the entry;
   - play a few minutes: FPS cap holds, no crashes, no visual glitches. If your device has headroom
     (or struggles), change settings in the menu and note what holds the profile's FPS cap.
4. Apply **Default (original)** with the game closed and check that your previous settings and
   launch options are back.
5. Note the Proton version the game runs with (game Properties → Compatibility). Use `default`
   only if you didn't force one; better, write the exact version, e.g. `Proton 9.0-4`.
6. Copy the starting device's block under `devices`, rename it to your device id, set `verified`
   and change only the values you tested. Values must be in the game's `options`:

   ```json
   "devices": {
     "rog-xbox-ally": { "...": "unchanged" },
     "rog-xbox-ally-x20": {
       "source": "https://github.com/cyruzin/loadout/pull/123",
       "verified": { "proton": "Proton 9.0-4", "date": "2026-11-02" },
       "profiles": { "quality": { "files": [ "..." ] }, "...": "..." }
     }
   }
   ```

7. Run the tests (`.venv/bin/python -m pytest -q`) and open the PR.

Tuning an existing device's block works the same way: test it on that device and change only
that block. If something didn't work, don't add a block: open an issue instead with what you saw.

## 2. Add a new game

Find the appid in the game's Steam store URL (`store.steampowered.com/app/<appid>/`) or with
`ls ~/.local/share/Steam/steamapps/appmanifest_*.acf`.

### 2.0 Look it up first

- **Where the config lives**: [PCGamingWiki](https://www.pcgamingwiki.com/)'s page for the game,
  section "Configuration file(s) location". It also says when settings are in the registry or a
  binary save instead (not supported, see below).
- **What each profile should set**: tested handheld settings such as
  [SteamDeckHQ](https://steamdeckhq.com/game-reviews/) or [ShareDeck](https://sharedeck.games/).
  Link the one you used in `source`. Use them for the choice of settings only: keys and values
  still come from the real file (2.1 to 2.3), and their TDP/power advice is out of scope.

### 2.1 Find the config file

The quickest way is the capture script. It records which keys change while you change settings
in the game, and also does 2.3 for you. It comes with Loadout; on the device (Konsole or SSH),
with the game closed and launched at least once before:

```bash
python3 ~/homebrew/plugins/Loadout/scripts/capture.py <appid> > ~/draft.json
```

1. Label the current settings (e.g. `original`): it takes a snapshot.
2. Launch the game, set every setting the profiles will touch to its **lowest** option, quit the
   game, then label it (e.g. `low`). Repeat with each step up to the highest (`medium`, `high`, …),
   then press Enter on an empty label.
3. `~/draft.json` has, per file and in the entry's syntax, `options` (each value seen, in the
   order you captured them) and `snapshots` (what each round set, ready to paste into a
   profile's `files`). The terminal lists the files that changed but can't be set: if the only
   change was a `.sav` or `user.reg`, the game keeps those settings in a save or the registry.

The draft shows what the game **writes**, not what it **reads** back: keep the checks in 2.5. Drop
keys that aren't graphics settings (window position, timestamps, resolution). Copy 2.2's byte
check for the PR as well.

To do it by hand instead: configure the game the way you want the profile to be, then **quit the
game** (many games only write their config on exit). Right after quitting, list the files the
game just wrote inside its Proton prefix:

```bash
P=~/.local/share/Steam/steamapps/compatdata/<appid>/pfx    # SD card: /run/media/*/steamapps/compatdata/<appid>/pfx
find "$P/drive_c/users/steamuser" -type f -mmin -5 2>/dev/null   # changed in the last 5 minutes
```

Common places: `drive_c/users/steamuser/AppData/Roaming/<Game>/`,
`drive_c/users/steamuser/AppData/Local/<Game>/` and `drive_c/users/steamuser/Documents/My Games/`.
Unreal Engine games use `<Project>/Saved/Config/WindowsNoEditor/GameUserSettings.ini` (UE4) or
`.../Windows/GameUserSettings.ini` (UE5), either under `AppData/Local/` in the prefix or inside the
game's install folder (Lies of P). If the prefix search finds nothing, search the install folder:

```bash
find ~/.local/share/Steam/steamapps/common/"<Game folder>" -type f -mmin -5 2>/dev/null
```

Supported formats:

- **XML** with flat `<Key>value</Key>` elements (ELDEN RING's `GraphicsConfig.xml`). Keys are the
  element names, e.g. `MotionBlur`.
- **INI** (Unreal's `GameUserSettings.ini`). Keys are written `[Section]Key`, because both parts
  can contain dots and slashes, e.g. `[ScalabilityGroups]sg.ShadowQuality` or
  `[/Script/ProjectP.LGameUserSettings]FSR3Mode`. A key that appears more than once in its section
  can't be set.
  Files without sections, like CryEngine's `game.cfg` (Crysis 3 Remastered), write keys before any
  header as `[]Key`, e.g. `[]sys_spec_Shadows`; lines starting with `;`, `#` or `--` are comments.

- **JSON** (Cyberpunk 2077's `UserSettings.json`). Keys are paths of object members, each starting
  with `/`; a member holding an array of objects picks its one element whose field equals a value,
  written `name[field=value]`:
  `/data[group_name=/graphics/advanced]/options[name=AmbientOcclusion]/value`. The value keeps its
  JSON type: write `"true"`/`"false"` for booleans and plain numbers (`"8"`, `"0.5"`) for numbers.
  `null`, objects and arrays can't be set, and a path must match exactly one value.
  Check which field the game actually reads: Cyberpunk keeps both `value` and `index` (the
  position in `values`) for fixed lists and reads `index`, so its entry sets both, e.g.
  `.../options[name=AmbientOcclusion]/index` = `"2"` with `value` = `"Medium"`. Changing only
  `value` looked right in the file but the game kept the old setting.

Other formats (Wine registry, binary saves) aren't supported: you can still add an entry with
launch env vars only, or open an issue with the file attached.

### 2.2 Check the file's bytes

Paste the output of these in the PR. Terminal output hides encoding details (ELDEN RING's file is
UTF-16 without a BOM, which looks like plain text in `cat`):

```bash
F="$P/drive_c/users/steamuser/AppData/Roaming/EldenRing/GraphicsConfig.xml"   # your file
file "$F"; head -c 64 "$F" | xxd; tail -c 48 "$F" | xxd
cat "$F"
```

### 2.3 Map menu options to file values

For every setting the profiles will change, write down the options the in-game menu offers, from
lowest to highest, and the value the file stores for each. The file often uses different words
than the menu (ELDEN RING: Off → `DISABLE`, Maximum → `MAX`). To find out, change one setting in
the menu, quit, and look at the file again. Don't assume a convention for values you didn't see.

This becomes the entry's `options`: Loadout rejects any profile value that isn't listed there.

### 2.4 Write the entry

Create `py_modules/loadout/data/games/<appid>.json` (use `1245620.json`, ELDEN RING, as the
model):

```json
{
  "schema_version": 2,
  "appid": 1245620,
  "name": "ELDEN RING",
  "options": {
    "{prefix}/drive_c/users/steamuser/AppData/Roaming/EldenRing/GraphicsConfig.xml": {
      "MotionBlur": ["DISABLE", "LOW", "MEDIUM", "HIGH"]
    }
  },
  "devices": {
    "rog-xbox-ally": {
      "source": "https://link-to-where-these-settings-came-from",
      "verified": { "proton": "default", "date": "2026-10-24" },
      "profiles": {
        "quality": {
          "launch": { "env": { "MESA_VK_WSI_PRESENT_MODE": "immediate" } },
          "files": [{
            "path": "{prefix}/drive_c/users/steamuser/AppData/Roaming/EldenRing/GraphicsConfig.xml",
            "format": "xml",
            "set": { "MotionBlur": "DISABLE" }
          }]
        }
      }
    }
  }
}
```

- **Paths** start with `{prefix}/` (the game's Proton prefix) or `{install_dir}/` (the game's
  install folder). Nothing else is allowed, and Loadout refuses paths that escape those folders.
- **`format`** is `xml`, `ini` or `json`; see `1627720.json` (Lies of P) for an INI entry and
  `1091500.json` (Cyberpunk 2077) for a JSON one.
- **No resolution keys**: the user picks the resolution in the game's menu
  (`test_bundled_games_leave_resolution_alone` enforces it). Leave out any key the game doesn't
  read from the file: Hogwarts Legacy rewrites its upscaler and resolution in
  `GameUserSettings.ini` from `SavedUserOptions.sav` on launch, so its entry sets only `sg.*`.
- **Keys** must already exist in the file; copy them exactly (case matters).
- **Profiles**: define only the ones you tested. The FPS cap comes from the device table, so a
  profile's `files` are about graphics, not frame rate.
- **Env vars** must match the allowlist (`DXVK_`, `VKD3D_`, `PROTON_`, `MANGOHUD`,
  `WINEDLLOVERRIDES`, `SDL_`, `MESA_`, `RADV_`).
- **Game arguments** go in `"launch": { "args": ["--launcher-skip"] }` (Cyberpunk 2077 skips its
  launcher with it). Each one is a plain flag (`-x` or `--name`, letters, digits, `_` and `-`):
  no values, spaces or shell characters. Loadout puts them right after `%command%`.
- **`source`**: where the settings came from (forum post, guide, ProtonDB report). If they're your
  own, link the PR or an issue describing your tests.
- **`options`** are the game's, shared by every device; **`devices`** has one block per device id
  (a file name in `py_modules/loadout/data/devices/`, without `.json`), each with its own profiles.
  Add a block only for a device where you did the checks in [section 1](#1-add-your-device-to-an-existing-game);
  its `verified` says with which Proton and when. Devices with the same chip can share the same
  profiles (the bundled games copy the ROG Xbox Ally's to both Steam Decks).

### 2.5 Test

1. On your computer: `.venv/bin/python -m pytest -q`. Invalid entries fail
   `test_bundled_games_load`.
2. Build and install your version on the device: `scripts/package.sh`, copy `out/Loadout.zip` to
   the device, Decky → Developer → **Install Plugin from ZIP File**, then
   `sudo systemctl restart plugin_loader`.
3. Do the checks from [section 1](#1-add-your-device-to-an-existing-game) for every profile.

## 3. Add a new device

1. On the device: `cat /sys/class/dmi/id/product_name`. Paste the output in the PR.
2. Create `py_modules/loadout/data/devices/<id>.json` (see `steam-deck-lcd.json`). In `match`, put
   a distinctive part of that string (matching is by substring, since some vendors add per-unit
   suffixes). Check it doesn't also match another device's string.
3. `native` is the panel resolution. FPS caps should divide the refresh rate evenly (30/40/60 on
   120 Hz, 36/48/72 on 144 Hz).
4. Add a case to `test_bundled_devices_load_and_detect` in `tests/test_core.py`, run the tests and
   check that the Loadout setup screen detects the device.

## Pull request checklist

- [ ] Tests pass (`.venv/bin/python -m pytest -q`).
- [ ] Each device block you added or changed has the Proton version and date of the test in `verified`.
- [ ] `source` links to where the settings came from.
- [ ] For new config files: `file`/`xxd`/`cat` output and the menu → file value mapping are in
      the PR description.
- [ ] Applied every defined profile and then Default on a real device; the game showed the
      expected settings and Default restored the originals.
