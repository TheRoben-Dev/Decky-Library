# Nightgrid Sounds

Original UI sound packs for Steam Game Mode, made for the Nightgrid theme. Every sound is **synthesized by the plugin** (Web Audio), so the plugin ships no audio files. A pack is rendered once per pack+volume into small WAVs (~200 KB total) under the plugin's data folder.

| Pack | Character |
|---|---|
| Nightgrid | Crisp terminal blips |
| Grid Pulse | Soft detuned synth, low and warm |
| Data Static | CRT clicks and lo-fi square tones |
| Ice Glass | Pure sine chimes, quiet and clean |

- Covers focus moves, select, open/back, tabs, end of list, toggles, sliders and volume, notifications, game launch and the on-screen keyboard.
- **Per sound**: keep any single sound from the pack, use Steam's, or turn it off (e.g. silence the focus tick).
- Volume slider and instant previews in Quick Access.

## How it works (and why it's light)
Steam plays every Game Mode UI sound through one method, `GamepadUIAudio.m_AudioPlaybackManager.PlayAudioURL(url)`. The plugin patches that method and swaps the URL for its own rendered sound. Steam's player only plays files from its own UI folder, so the WAVs live in `~/homebrew/data/Nightgrid Sounds/sounds/` and are served through a symlink `steamui/sounds_nightgrid` (re-created on each start, since Steam updates can wipe `steamui`; removed on uninstall). No polling, no timers, no background process. A pack renders in well under 0.2 s, only the first time you pick that pack+volume. Turning it off or uninstalling restores Steam's sounds right away.

If Audio Loader is installed too, set its pack to Default (both patch the same player); the panel warns about it.

## Build
```
pnpm install && pnpm build && ./package.sh
```
Tests: `python3 -m unittest discover -s tests`. Sounds are original works © Roben, BSD-3-Clause like the code.
