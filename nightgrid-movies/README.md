# Nightgrid Movies

Decky plugin with Nightgrid-styled **startup movies**, **sleep (suspend) animations** and an
**idle screensaver** for Steam Game Mode, matching the [Nightgrid](../nightgrid-theme) CSS Loader theme. Pick them from
Quick Access; install or update it from Library Hub.

| Startup movie | |
|---|---|
| Boot Sequence | the grid draws in, a boot log types out, a static burst, then the wordmark locks in (6 s) |
| Kernel Log | a fast kernel-style boot log scrolls past, then the wordmark types itself in (6 s) |
| Login | terminal login, password dots, ACCESS GRANTED, then the wordmark (6 s) |
| Diagnostics | a system check with filling bars, ALL SYSTEMS NOMINAL, then the wordmark (6 s) |
| Decrypt | a hex scramble that locks into the wordmark letter by letter (5.5 s) |
| Signal | TV static thins out and leaves the wordmark behind (5 s) |
| Grid Run | a perspective grid runs at you and the wordmark rises over the horizon (5 s) |

| Sleep animation | |
|---|---|
| Power Down | old-CRT switch-off: the picture collapses to a line, then a dot (2.4 s) |
| Static Out | the wordmark breaks into static, then the static rolls away to black (2.4 s) |

Each movie has a thumbnail in the picker and a **Preview** button that plays it fullscreen
(any input stops it). **Shuffle each boot** picks a different startup movie every time the plugin loads.

## Screensaver
After a set time with no input (1–30 min, default 5), a fullscreen Nightgrid animation covers
Game Mode. Any button, stick, trigger or touch wakes it. The button that wakes it also does its
normal job, so moving a stick is the safest way to wake it. It never shows while a game is
running, and Steam's own dim and sleep timers still apply on top of it.

| Style | |
|---|---|
| Grid Run | endless perspective grid with the wordmark and a clock over the horizon |
| Signal | wordmark and clock drifting over a faint static, with a short glitch now and then |
| Terminal | a slow standby log typing out, with the clock in the corner |
| Clock | a big drifting clock and date on the grid |
| Random | a different style each time |

Everything that stays on screen drifts slowly. The art is drawn live
(`src/saverArt.ts`, 960×540 canvas scaled up, max 30 fps). Idle detection uses
`SteamClient.Input` controller callbacks plus touch, key and mouse events in the Game Mode window
(`src/screensaver.tsx`).

## How it works
Steam plays override videos from `~/.steam/root/config/uioverrides/movies`:

| File | Used for |
|---|---|
| `deck_startup.webm` | startup movie: select **deck_startup.webm** once in Settings → Customization → Startup Movie |
| `steam_os_suspend.webm` | suspend animation from the menus |
| `steam_os_suspend_from_throbber.webm` | suspend animation from in-game |

The plugin copies the chosen video there and remembers each file's SHA-256. A file it didn't
write (Animation Changer, something added by hand) is never deleted. It's renamed to
`<name>.before-nightgrid` and put back when you pick "Steam default" or uninstall the plugin.
Runs as the normal user (no root).

## Rendering the videos
The videos are drawn in code (`render/movies.html`, canvas, seeded so every render is the same)
and encoded to 1280×720 VP9 at 30 fps with no audio:

```sh
cd render && NODE_PATH=$(npm root -g) node render.cjs ../movies            # all
NODE_PATH=$(npm root -g) node render.cjs --stills /tmp/stills signal       # 8 preview stills
```
You need Playwright (Chromium) and ffmpeg. Thumbnails in `movies/thumbs/` are one frame per
movie (`ffmpeg -ss <t> -i movies/<id>.webm -frames:v 1 -vf scale=320:180 movies/thumbs/<id>.jpg`). The rendered `.webm` files are committed, so the
release build only runs `pnpm build` and `package.sh`.

JetBrains Mono (in `render/`) is under the SIL Open Font License; see `render/JetBrainsMono-OFL.txt`.
