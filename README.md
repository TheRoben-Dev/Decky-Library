# Decky-Library

Decky Loader plugins for Bazzite / SteamOS handhelds. Each plugin lives in its own folder and builds on its own.

| Plugin | What it does |
|---|---|
| [vex-performance](vex-performance/) | Per-game smart profiles: gamescope FSR, frame cap + matched refresh, TDP/GPU (Handheld Daemon aware) and lsfg-vk frame gen, applied automatically on game launch. |
| [proton-picker](proton-picker/) | Per-game Proton picker: ProtonDB/Deck-rating driven auto choice, installs GE-Proton / Proton-CachyOS, applies it with no launch options and rolls back if a game breaks. |
| [ally-tweaks](ally-tweaks/) | ROG Ally 2023 tweaks: ring RGB that persists through Handheld Daemon (per-game, battery/temperature/TDP reactive, low-battery pulse), charge limiter with one-tap full charge, per-game M1/M2 layouts, panel overdrive. No TDP/fan/firmware changes. |

## Building a plugin
```
cd <plugin-folder>
pnpm install
pnpm build
./package.sh   # installable zip in out/
```
Install the zip from Decky → Developer → Install Plugin from Zip.
