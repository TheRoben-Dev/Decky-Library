# Decky-Library

Decky Loader plugins for Bazzite / SteamOS handhelds. Each plugin lives in its own folder and builds on its own.

| Plugin | What it does |
|---|---|
| [vex-performance](vex-performance/) | Per-game smart profiles: gamescope FSR, frame cap + matched refresh, TDP/GPU (Steam slider / PowerStation) and lsfg-vk frame gen, applied automatically on game launch. |

## Building a plugin
```
cd <plugin-folder>
pnpm install
pnpm build
./package.sh   # installable zip in out/
```
Install the zip from Decky → Developer → Install Plugin from Zip.
