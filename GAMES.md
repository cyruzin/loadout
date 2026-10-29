# Supported games

Games with a Loadout entry in `py_modules/loadout/data/games/<appid>.json`. On these, a profile
sets the game's graphics settings. Loadout doesn't cap the frame rate (since 0.6.0): each profile
is made for a target FPS from the device table (see the [README](README.md#what-the-mvp-does)),
which you set as the frame limit in Steam's Quick Access Menu.

Profiles are per device. Every game below has the same profiles for the Steam Deck LCD, Steam Deck
OLED and ROG Xbox Ally, tested on a ROG Xbox Ally at 15 W (a chip close to the Steam Deck's). On
any other device, pick one of those under **Use profiles from**, or add a block for your device
([CONTRIBUTING.md](CONTRIBUTING.md)).

Profiles never set the game's resolution: pick it in the game's menu (or Steam's game
resolution setting) for your device and whether you're docked. Where a game ignores a setting in
its config file, the entry leaves it out and you set it in the menu (see Hogwarts Legacy).

| Game | Profiles for | Quality | Balanced | Performance |
|---|---|---|---|---|
| ELDEN RING (1245620) | Steam Deck LCD/OLED, ROG Xbox Ally | tuned graphics (high textures/AA, low shadows, motion blur off) | — | — |
| Lies of P (1627720) | Steam Deck LCD/OLED, ROG Xbox Ally | everything Medium | Medium; shading, shadows, reflections, fog, AO Low | everything Low |
| Cyberpunk 2077 (1091500) | Steam Deck LCD/OLED, ROG Xbox Ally | the game's "Steam Deck" preset with FSR 2 Quality | the game's "Steam Deck" preset (FSR 2 Balanced) | everything Low/Off, FSR 2 Performance |
| Hogwarts Legacy (990080) | Steam Deck LCD/OLED, ROG Xbox Ally | mostly Medium (shading High; volumetrics, population Low) | everything Low | everything Low |
| Crysis 3 Remastered (2096610) | Steam Deck LCD/OLED, ROG Xbox Ally | High, textures High | Medium, textures High | Low, textures High |
| Baldur's Gate 3 (1086940) | Steam Deck LCD/OLED, ROG Xbox Ally | mostly Low, textures Medium, FSR 2.2 Quality | — | — |
| The Witcher 3: Wild Hunt (292030) | Steam Deck LCD/OLED, ROG Xbox Ally | mostly Medium, textures/detail High, water Low, XeSS Native AA, motion blur 2 | the same with XeSS Quality, detail Medium, motion blur and blur off | — |

### Recommended resolution

Shown under **Profile** in the panel. On the ROG Xbox Ally it's the resolution each profile was
tested at. On the Steam Decks it's the native 1280×800, not tested there: about 11% more pixels
than 720p, and Crysis 3's levels come from Deck reports at that resolution.

| Game | ROG Xbox Ally | Steam Deck LCD/OLED |
|---|---|---|
| ELDEN RING | 1280×720 | 1280×800 |
| Lies of P | 1920×1080 (Quality, Balanced), 1280×720 (Performance) | 1280×800 |
| Cyberpunk 2077 | 1280×720 | 1280×800 |
| Hogwarts Legacy | 1280×720 | 1280×800 |
| Crysis 3 Remastered | 1280×720 | 1280×800 |
| Baldur's Gate 3 | 1280×720 | 1280×800 |
| The Witcher 3 | 1280×720 | 1280×800 |

## Notes per game

**ELDEN RING.** Quality only: 40 FPS is reachable, but only by giving up too much image quality
on these handhelds, so there's no Balanced or Performance (the panel hides them).
Quality also sets `MESA_VK_WSI_PRESENT_MODE=immediate`.

**Lies of P.** All profiles keep textures at Medium and anisotropic filtering at Maximum (cheap,
big visual win), use FSR 3 Quality with 0.7 sharpness and CACAO, and turn off frame generation, the
game's own frame limit and VSync so Steam's frame limit is the only limiter.

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
held 40 with drops to 31-35 (so Quality, made for 30), Medium with textures High held 45 Hz
(Balanced), everything Low ran 60 with rare dips (Performance; that report also lowered the
resolution and used FSR, which a profile doesn't). VSync is off so Steam's frame limit is the
only limiter. All profiles also set anisotropic filtering 16x and motion blur off; lens flares are
left as you set them. After a profile, the menu can still show your previous motion blur amount
(it reads it from the profile file), while `game.cfg` and the game keep it off. Texture options below High weren't seen in the file, so they aren't offered.

**Baldur's Gate 3.** Native Linux build (Steam's default since it shipped): settings live in
`~/.local/share/Larian Studios/Baldur's Gate 3/graphicSettings.lsx`, which the game saves when you
leave the options menu. Quality only: these handhelds don't hold 40 in Act 3, so there's no
Balanced or Performance (the panel hides them). Quality follows a Steam Deck native-build video
(28-37 FPS in Act 3 with FSR 2.2 Quality): textures Medium, terrain, instance/detail distance, fog
and animation Low, anisotropic 8x, ambient occlusion on, depth of field off, VSync and the game's
frame cap off. Model, shadow and cloud quality (not shown there) are Low. Bloom, subsurface
scattering and Slow HDD Mode are off, as in a Steam Deck OLED guide (lighter for Act 3; Slow HDD
Mode uses more of the RAM the GPU shares). Dynamic crowds is off: extra NPCs in cities cost CPU,
and Act 3 is CPU-bound. Seen on a ROG Xbox
Ally: after applying Quality the menu shows these values and the preset as Custom; Default puts
every key back. The preset name (`CurrentSettings`) isn't set by the profile: while playing with
Quality the game drops it, so after Default the menu may show Custom with your original values. If you force Proton, the file is in the prefix and the
entry doesn't reach it.

**The Witcher 3: Wild Hunt.** DX12 (the only renderer its launcher offers now). Settings live in
`Documents/The Witcher 3/dx12user.settings` in the prefix, which the game reads on launch. Quality
follows a Steam Deck 30 FPS setup from r/SteamDeck ("Witcher 3 Remastered Settings", top comment):
XeSS Native AA (no upscaling), sharpening off, GTAO High, reflections Low, background characters,
shadows, terrain, foliage and grass Medium, screen space shadows on, water Low, textures and detail
High. Balanced is the same with XeSS Quality, as that comment suggests for a higher frame rate,
and detail Medium (less CPU, to stay at 40). Played on a ROG Xbox Ally: Quality keeps motion blur on
at intensity 2 (instead of the game's 10), Balanced turns motion blur and blur off; both felt better
that way.
No Performance: 60 isn't expected on these handhelds. Both profiles turn ray tracing, HairWorks,
VSync and the game's own frame limit (Maximum Frames Per Second: Unlimited) off. Dynamic resolution
is left alone (the menu disables it with XeSS); bloom, depth of field and the other effects are left
as you set them. All profiles launch with `--launcher-skip`. On the Steam Decks they
also set `SteamDeck=0`, as ProtonDB reports do: with Steam's `SteamDeck=1` the game locks its
graphics settings (not tested on a Deck). The ROG Xbox Ally doesn't need it: Steam doesn't set
`SteamDeck` there. Not yet measured: whether each profile holds its target FPS.

## Adding or verifying a game

See [CONTRIBUTING.md](CONTRIBUTING.md). Resolution keys don't go in an entry.
