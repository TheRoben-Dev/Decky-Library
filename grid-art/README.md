# Grid Art

Change a game's library artwork from [SteamGridDB](https://www.steamgriddb.com) without leaving Game Mode, in a full-screen Nightgrid-styled browser.

- **Capsule, Wide, Hero, Logo and Icon** (the small square game icon) for Steam games and non-Steam shortcuts.
- Uses Steam's own custom artwork (`SteamClient.Apps.SetCustomArtworkForApp`), so Steam keeps the files in `userdata/<id>/config/grid` and the art stays even if the plugin is removed. **Reset to Steam's** puts the original back.
- **From file** applies any PNG/JPEG on the device (Decky's file browser).
- Filters: style per slot, animated (APNG) art, humor, flashing images, adult content (off by default).
- **Custom search**: press **Search…** (or **Y** on any picture), type any name with the on-screen keyboard and pick the SteamGridDB game to take art from. Handy for remasters, demos, mods, or a game SteamGridDB files under another name. The pick is remembered per game; **Use Steam's own** (or **Match by name again** for shortcuts) undoes it.
- Non-Steam shortcuts are matched on SteamGridDB by name automatically; Search fixes a wrong match.

## Light on resources
Nothing runs in the background: no polling, no Steam event hooks, no startup work beyond registering one route and one game-menu entry. The backend only talks to SteamGridDB when the browser is open, caches answers in memory for 10 minutes, and thumbnails are lazy-loaded straight from SteamGridDB's CDN.

## Setup
1. Get a free API key: sign in at steamgriddb.com → Preferences → API.
2. Quick Access → Grid Art → **API key**, type or paste it, **Save key**.
   Easier from Desktop Mode: save the key as `~/homebrew/settings/Grid Art/key.txt`; the plugin imports it the next time the panel opens and deletes the file.

The key is stored in `~/homebrew/settings/Grid Art/settings.json` (mode 600) and never sent to the UI.

## Use
In the library, open a game's menu and pick **Change artwork…** (between Manage and Properties). Or open a game's page (or pick a game in the panel), then Quick Access → Grid Art → **Change artwork**. L1/R1 switch between slots; A sets the focused picture, Y opens Search.

## Files
| Path | What |
|---|---|
| `main.py` | Decky backend (API calls, downloads, settings) |
| `py_modules/gridart/sgdb.py` | SteamGridDB client: query building, host allow-list, size cap, PNG/JPEG check |
| `src/page.tsx` | Full-screen browser (`/grid-art/:appid`) |
| `src/search.tsx` | Custom search dialog (debounced, newest answer wins) |
| `src/index.tsx` | Quick Access panel |
| `src/menu.tsx` | "Change artwork…" entry in the library game menu |

Runs as the normal user (no root). Tests: `python3 -m unittest discover -s tests`.

SteamGridDB artwork belongs to its creators; this plugin only shows and downloads what you pick. Not affiliated with SteamGridDB or Valve.
