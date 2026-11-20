# Decky-Library

Decky Loader plugins and CSS Loader themes for Bazzite / SteamOS handhelds. Each one lives in its own folder.

## Themes (CSS Loader)
| Theme | What it does |
|---|---|
| [nightgrid-theme](nightgrid-theme/) | Retro-terminal Game Mode theme based on the Nightgrid app: near-black grid canvas, cyan data accents, magenta outlined selection, uppercase mono labels. Covers Game Mode, Quick Access, friends & chat, the Store and toasts. Palette, custom colors, grid, font, glow and scanline options. |

Install a theme by extracting its zip into `~/homebrew/themes/`, then refresh CSS Loader and enable it.

## Plugins
| Plugin | What it does |
|---|---|
| [library-hub](library-hub/) | Installs, updates and removes every plugin in this repo and the Nightgrid theme from Quick Access (SHA-256 checked, via Decky's own installer), offers CSS Loader if it's missing, and updates itself. |
| [handheld-library](handheld-library/) | Keeps a "Handheld Ready" Library collection of games rated Deck Verified/Playable (optionally SteamOS Compatible, ProtonDB Gold+ or native) that have full or partial controller support, and lists your hidden games in Quick Access with Play and Unhide. |
