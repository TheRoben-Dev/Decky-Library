# Nightgrid Movies

Decky plugin with Nightgrid-styled **startup movies** and **sleep (suspend) animations** for
Steam Game Mode, matching the [Nightgrid](../nightgrid-theme) CSS Loader theme. Pick them from
Quick Access; install or update it from Library Hub.

| Startup movie | |
|---|---|
| Boot Sequence | the grid draws in, a boot log types out, a static burst, then the wordmark locks in (6 s) |
| Signal | TV static thins out and leaves the wordmark behind (5 s) |
| Grid Run | a perspective grid runs at you and the wordmark rises over the horizon (5 s) |

| Sleep animation | |
|---|---|
| Power Down | old-CRT switch-off: the picture collapses to a line, then a dot (2.4 s) |
| Static Out | the wordmark breaks into static, then the static rolls away to black (2.4 s) |

**Shuffle each boot** picks a different startup movie every time the plugin loads.

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
cd render && NODE_PATH=$(npm root -g) node render.js ../movies            # all
NODE_PATH=$(npm root -g) node render.js --stills /tmp/stills signal       # 8 preview stills
```
You need Playwright (Chromium) and ffmpeg. The rendered `.webm` files are committed, so the
release build only runs `pnpm build` and `package.sh`.

JetBrains Mono (in `render/`) is under the SIL Open Font License; see `render/JetBrainsMono-OFL.txt`.
