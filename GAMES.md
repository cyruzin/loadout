# Supported games

Games with a Loadout entry in `py_modules/loadout/data/games/<appid>.json`. On these, a profile
sets the FPS cap from the device table (see the [README](README.md#what-the-mvp-does)) **and**
the game's graphics settings. Any other game gets the FPS cap only.

Profiles are per device. Every game below has the same profiles for the Steam Deck LCD, Steam Deck
OLED and ROG Xbox Ally, tested on a ROG Xbox Ally at 15 W (a chip close to the Steam Deck's). On
any other device, pick one of those under **Use profiles from**, or add a block for your device
([CONTRIBUTING.md](CONTRIBUTING.md)).

Profiles never set the game's resolution: pick it in the game's menu (or Steam's game
resolution setting) for your device and whether you're docked. Where a game ignores a setting in
its config file, the entry leaves it out and you set it in the menu (see Hogwarts Legacy).

| Game | Profiles for | Quality | Balanced | Performance / Uncapped |
|---|---|---|---|---|
| ELDEN RING (1245620) | Steam Deck LCD/OLED, ROG Xbox Ally | tuned graphics (high textures/AA, low shadows, motion blur off) | device cap only | every graphics option at its lowest |
| Lies of P (1627720) | Steam Deck LCD/OLED, ROG Xbox Ally | everything Medium | Medium; shading, shadows, reflections, fog, AO Low | everything Low |
| Cyberpunk 2077 (1091500) | Steam Deck LCD/OLED, ROG Xbox Ally | the game's "Steam Deck" preset with FSR 2 Quality | the game's "Steam Deck" preset (FSR 2 Balanced) | everything Low/Off, FSR 2 Performance |
| Hogwarts Legacy (990080) | Steam Deck LCD/OLED, ROG Xbox Ally | mostly Medium (shading High; volumetrics, population Low) | everything Low | everything Low |
| Crysis 3 Remastered (2096610) | Steam Deck LCD/OLED, ROG Xbox Ally | High, textures High | Medium, textures High | Low, textures High |

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

**Crysis 3 Remastered.** Settings live in `game.cfg` (CryEngine, no sections), which the game
reads on launch; the menu then shows System Spec "Custom". On launch it reloads antialiasing and
ray tracing from its encrypted profile (`Profiles/default/attributes.xml`), so set those in the
menu (the Steam Deck reports turn ray tracing off; SMAA 1X, or FXAA for 60). Levels follow the
Steam Deck reports on [ProtonDB](https://www.protondb.com/app/2096610): High with ray tracing off
held 40 with drops to 31-35 (so Quality, capped at 30), Medium with textures High held 45 Hz
(Balanced), everything Low ran 60 with rare dips (Performance; that report also lowered the
resolution and used FSR, which a profile doesn't). VSync is off so Loadout's cap is the only
limiter. All profiles also set anisotropic filtering 16x and motion blur off; lens flares are
left as you set them. After a profile, the menu can still show your previous motion blur amount
(it reads it from the profile file), while `game.cfg` and the game keep it off. Texture options below High weren't seen in the file, so they aren't offered.

## Adding or verifying a game

See [CONTRIBUTING.md](CONTRIBUTING.md). Resolution keys don't go in an entry.
