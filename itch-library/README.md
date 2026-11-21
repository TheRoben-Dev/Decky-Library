# Itch Library

Your itch.io library in Steam Game Mode, Nightgrid-styled and fully controller-driven.

- **Sign in without typing.** Scan a QR code with your phone, paste your itch.io API key on the page it opens, done.
  (Or save the key as `~/Desktop/itch-key.txt` in Desktop Mode, or type it.)
- **Browse & search itch.io** for new games (Browse tab): sort by Popular, New & popular, Top sellers, Top rated or Newest,
  filter by price (Free, Paid, On sale, $5/$15 or less), genre and platform, and under *More filters* by release date,
  length, multiplayer, accessibility, engine, demo and up to three tags. Adult/NSFW tags are only offered once you
  turn on *Show adult content in Browse* in Quick Access → Itch Library → Settings (off by default; itch.io itself also
  limits which adult games its browse pages list). **Controller support is on by default**
  (itch.io's "Gamepad (any)" input filter; switch to Xbox controller or All games). Search uses the on-screen keyboard.
  Free games install directly (X on the tile). Paid games show their price and **Buy on itch.io** opens that game's
  store page in Steam's browser, or **Buy on phone** shows a QR code; after buying, *I bought it* moves it to your
  library. Paid games' free demos can be installed too.
- **Your library**: every game you bought or claimed in a full-screen grid: All, Installed, Updates, Downloads.
  L1/R1 switch tabs, A opens a game, X installs or plays it right from the grid.
- **Install** native Linux builds, or Windows builds through Proton (you choose which wins when a game has both, and
  which Proton). Pick a specific build on the game page when there's more than one.
- **Plays from Steam.** Each installed game becomes a non-Steam shortcut with generated Nightgrid artwork
  (capsule, wide, hero, logo, icon) made from its itch.io cover. Windows games get Proton set automatically.
- **Updates** are checked when you open the library (at most every 6 hours) or with Check for updates. Updating keeps
  files the game created in its own folder (saves, settings).
- **Uninstall** removes the files and the shortcut. For Windows games you choose whether to keep the Proton prefix,
  which holds their saves.
- Installs to internal storage or any SD card / USB drive (Quick Access → Itch Library → Settings).

Browse uses itch.io's public RSS feeds for its browse pages (the same filters as the website), search uses the
official API. Pages are cached for 15 minutes, filter changes are batched, and if itch.io answers "too many requests"
the plugin waits out its Retry-After before asking again (showing earlier results meanwhile). Nothing runs in the background: the library is fetched (and cached for 30 minutes) and updates are checked only when
you open it. Downloads run one at a time and report progress only while they run.

## Signing in

itch.io → Settings → **API keys** → *Generate new API key*. The QR code on the sign-in screen opens a one-time page
served by the handheld itself on your Wi-Fi, which links straight there; paste the key and press *Send to handheld*.
That page only exists while the sign-in screen is open, answers on a random address, takes one key and closes.

The key is stored in `~/homebrew/settings/Itch Library/settings.json` (readable only by you), is only ever sent to
`api.itch.io`, and never reaches the plugin's UI. Sign out from Quick Access → Itch Library → Settings, and revoke the
key on itch.io if you no longer want it.

## What gets installed where

| | |
|---|---|
| Games | `~/Games/itch/<Title>-<id>/` (or `<drive>/Games/itch/` when you pick an SD card) |
| Install records | `~/homebrew/settings/Itch Library/installed.json` |
| Library cache, icons, file lists | `~/homebrew/data/Itch Library/` |
| Windows saves | Steam's Proton prefix for the shortcut (`steamapps/compatdata/<shortcut id>`) |

Archives: zip and tar (gz/xz/bz2) are handled natively; 7z, rar and zstd use `7z`/`bsdtar`/`unrar` when the system has
them. Single-file builds (.exe, .AppImage, .x86_64, .sh) work as they are. The launch file is chosen from the developer's
`.itch.toml` manifest when there is one, then itch.io's own scan of the build, then by name/size; you can change it on
the game page. Inno Setup / NSIS installers are unpacked with `innoextract`/`7z` when possible; otherwise Play runs the
installer once through Proton and you pick the installed game afterwards.

Not supported: macOS-only and Android builds, web (HTML) games, .msi installers, and itch.io's external-link uploads.
Bundle games show up once you've claimed them on the bundle's page.

## Notes

Unofficial plugin, not affiliated with itch.io. It uses itch.io's public API (the same one the official itch app uses)
with your own key, and only downloads games your account owns or has claimed.

Tested logic: Python unit tests (`python3 -m unittest discover -s tests`). Not yet tested on hardware.

## Build

```
pnpm install
pnpm build
./package.sh   # out/Itch-Library.zip
```
