# Supported games

Games with a Loadout entry in `py_modules/loadout/data/games/<appid>.json`. On these, a profile
sets the FPS cap from the device table (see the [README](README.md#what-the-mvp-does)) **and**
the game's graphics settings. Any other game gets the FPS cap only.

Profiles never set the game's resolution: pick it in the game's menu (or Steam's game
resolution setting) for your device and whether you're docked. Where a game ignores a setting in
its config file, the entry leaves it out and you set it in the menu (see Hogwarts Legacy).

| Game | Verified on | Quality | Balanced | Performance / Uncapped |
|---|---|---|---|---|
| ELDEN RING (1245620) | all bundled devices (tested on ROG Xbox Ally) | tuned graphics (high textures/AA, low shadows, motion blur off) | device cap only | every graphics option at its lowest |
| Lies of P (1627720) | all bundled devices (tested on ROG Xbox Ally) | everything Medium | Medium; shading, shadows, reflections, fog, AO Low | everything Low |
| Cyberpunk 2077 (1091500) | all bundled devices (tested on ROG Xbox Ally) | the game's "Steam Deck" preset with FSR 2 Quality | the game's "Steam Deck" preset (FSR 2 Balanced) | everything Low/Off, FSR 2 Performance |
| Hogwarts Legacy (990080) | all bundled devices (untested) | mostly Medium (shading High; volumetrics, population Low) | everything Low | everything Low |

## Notes per game

**ELDEN RING.** All profiles also set `MESA_VK_WSI_PRESENT_MODE=immediate`.

**Lies of P.** All profiles keep textures at Medium and anisotropic filtering at Maximum (cheap,
big visual win), use FSR 3 Quality with 0.7 sharpness and CACAO, and turn off frame generation, the
game's own frame limit and VSync so Loadout's cap is the only limiter.

**Cyberpunk 2077.** All profiles turn ray tracing, frame generation, VSync and the game's own
frame limit off, and launch with `--launcher-skip` (straight into the game, no CD PROJEKT RED
launcher). The game is CPU-heavy: on a ROG Xbox
Ally, Performance drops below 60 in busy areas even with everything Low.

**Hogwarts Legacy.** Only the scalability groups (`sg.*`) are set: on launch the game reloads
its upscaler and resolution (and most likely the rest of `[/Script/Phoenix.PhoenixGameSettings]`)
from its save (`SavedUserOptions.sav`), so set the upscaler (e.g. FSR 3), ray tracing, VSync and the frame limit (Unlimited) in the game.
Balanced held 40 FPS in Hogsmeade on a ROG Xbox Ally at 15 W, 720p, FSR 3 Balanced, with drops.

## Adding or verifying a game

See [CONTRIBUTING.md](CONTRIBUTING.md). Resolution keys don't go in an entry.
