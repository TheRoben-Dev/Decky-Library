# Decky-Library

Decky Loader plugins and CSS Loader themes for Bazzite / SteamOS handhelds. Each one lives in its own folder.

## Themes (CSS Loader)
| Theme | What it does |
|---|---|
| [nightgrid-theme](nightgrid-theme/) | Retro-terminal Game Mode theme based on the Nightgrid app: near-black grid canvas, cyan data accents, magenta outlined selection, uppercase mono labels. Covers Game Mode, Quick Access, friends & chat, the Store and toasts. Palette, custom colors, grid, font, glow and scanline options. |
| [lowpoly-theme](lowpoly-theme/) | Late-90s 3D Game Mode theme: a low-res pre-rendered scene (fogged grid floor, pixelated low-poly toys, 15-bit dither) behind dark flat rows with one warm accent. Eight accents plus custom, backdrop, CRT, font and animation options. |

Install a theme by extracting its zip into `~/homebrew/themes/`, then refresh CSS Loader and enable it.

## Plugins
| Plugin | What it does |
|---|---|
| [library-hub](library-hub/) | Installs, updates and removes every plugin in this repo and the Nightgrid theme from Quick Access (SHA-256 checked, via Decky's own installer), offers CSS Loader if it's missing, and updates itself. |
| [handheld-library](handheld-library/) | Keeps a "Handheld Ready" Library collection of games rated Deck Verified/Playable (optionally SteamOS Compatible, ProtonDB Gold+ or native) that have full or partial controller support, and lists your hidden games in Quick Access with Play and Unhide. |
| [vex-performance](vex-performance/) | Per-game smart profiles: gamescope FSR, frame cap + matched refresh, TDP/GPU (Steam slider / PowerStation) and lsfg-vk frame gen, applied automatically on game launch. |
| [proton-picker](proton-picker/) | Per-game Proton picker: ProtonDB/Deck-rating driven auto choice, installs GE-Proton / Proton-CachyOS, applies it with no launch options and rolls back if a game breaks. |
| [itch-library](itch-library/) | Your itch.io library in Game Mode: sign in from your phone (QR), browse and search itch.io (controller-supported games by default) and your owned games in a full-screen Nightgrid grid, buy paid games on their itch page, install native Linux or Windows (Proton) builds, play them from Steam with generated artwork, update keeping saves, uninstall. Nothing runs in the background. |
| [amazon-library](amazon-library/) | Your Amazon Games library in Game Mode: sign in from your phone (QR), Prime Gaming / Luna free games, install through Proton with every file checked against Amazon's signed manifest, Steam shortcuts with Amazon's artwork in the Nightgrid look, updates that fetch only changed files, verify, uninstall (keeps the Proton prefix unless asked), SD card support. Nothing runs in the background. |
| [gog-library](gog-library/) | Your GOG library in Game Mode: sign in from your phone (QR) on GOG's own page, browse and search the GOG store (controller-supported games by default) and your owned games in a full-screen Nightgrid grid, buy games on their GOG page, install native Linux versions or Windows versions through Proton (file-by-file Galaxy downloads with owned DLCs, updates fetch only what changed), Steam shortcuts with GOG's artwork, uninstall (keeps the Proton prefix unless asked), SD card support. Nothing runs in the background. |
| [epic-library](epic-library/) | Your Epic Games Store library in Game Mode: sign in from your phone (QR) on Epic's own page, browse and search the Epic store (this week's free games on top, controller-supported games by default), install through Proton with Legendary (owned DLC included, pause/resume), launch from Steam with a fresh Epic token and the game's own artwork in the Nightgrid look, updates, repair, Epic cloud saves, uninstall (keeps the Proton prefix unless asked), SD card support. Nothing runs in the background. |
| [grid-art](grid-art/) | SteamGridDB artwork browser: capsule, wide, hero, logo and shortcut icons in a full-screen Nightgrid page, applied through Steam's own custom artwork. Needs a free SteamGridDB API key. |
| [nightgrid-sounds](nightgrid-sounds/) | Original Nightgrid UI sound packs (synthesized in the plugin, no audio files): four packs, volume, per-sound Pack/Steam/Off. |
| [storage-sweep](storage-sweep/) | Frees space left by uninstalled games (shader caches, workshop files, Proton prefixes with a save warning) and resets single shader caches. SD-card aware; scans only on demand. |
| [nightgrid-control](nightgrid-control/) | Nightgrid homelab hosts in Quick Access: online state, CPU, memory, disk and temperature, with Wake, Reboot and Shut down (confirmed). Uses your existing Nightgrid profile export or the Nightgrid app on the device; SSH only, refreshes only while open, controller-only. |
| [ally-tweaks](ally-tweaks/) | ROG Ally 2023 tweaks: ring RGB (kernel LED on Bazzite 44+/InputPlumber, HHD where present) that survives reboots, per-game/reactive/follow-screen lighting, left/right ring colors, charge limiter with one-tap full charge, panel overdrive. No TDP/fan/firmware changes. |

## Building a plugin
```
cd <plugin-folder>
pnpm install
pnpm build
./package.sh   # installable zip in out/
```
Install the zip from Decky → Developer → Install Plugin from Zip.
