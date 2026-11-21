# Nightgrid Sounds

Original UI sound packs for Steam Game Mode, made for the Nightgrid theme. Every sound is **synthesized by the plugin** (Web Audio, rendered once into tiny WAVs in memory), so the plugin ships no audio files and writes nothing to disk except its settings.

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
Steam plays every Game Mode UI sound through one method, `GamepadUIAudio.m_AudioPlaybackManager.PlayAudioURL(url)`. The plugin patches that method and swaps the URL for its own rendered sound. No polling, no timers, no background process; the backend only stores `~/homebrew/settings/Nightgrid Sounds/settings.json`. The 13 sounds of a pack render in well under 0.2 s total, once at startup and again only when you change pack or volume. Turning it off or uninstalling restores Steam's sounds right away.

If Audio Loader is installed too, set its pack to Default (both patch the same player); the panel warns about it.

## Build
```
pnpm install && pnpm build && ./package.sh
```
Tests: `python3 -m unittest discover -s tests`. Sounds are original works © Roben, BSD-3-Clause like the code.
