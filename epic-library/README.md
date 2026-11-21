# Epic Library

Your Epic Games Store library in Steam Game Mode, Nightgrid-styled and fully controller-driven.

- **Sign in without typing.** Scan a QR code with your phone: it opens Epic's own activation page
  (epicgames.com/activate) with the code filled in. Sign in, confirm, and the handheld continues by itself. Your
  password only ever goes to Epic. (Pasting a code on a page the handheld serves, or typing it, works too.)
- **Browse & search the Epic Games Store** (Browse tab): this week's **free games** on top, then search, sort (Popular,
  Newest, price, A–Z), price (Free, On sale) and genre. **Controller support is on by default** (Epic's own
  *Controller Support* tag); switch to *All games* to see everything. Filters also apply to search.
  Games you own open their library page. Others show their price: **Get/Buy on Epic** opens that game's store page in
  Steam's browser, or **on phone** shows a QR code. Free games have to be claimed there too. Then press *I got it*:
  the game moves to your library.
- **Your library**: every game you own in a full-screen grid: Library, Installed, Updates, Downloads.
  L1/R1 switch tabs, A opens a game, X installs or plays it right from the grid.
- **Install** through Proton (Epic games are Windows builds). The game page shows the size before you install. DLC you
  own is installed with the game (setting). Downloads can be **paused and resumed**; a paused download can be discarded.
- **Plays from Steam** with the game's own Epic artwork (box art capsule, key art wide/hero, logo, icon) finished in
  the Nightgrid look. Each launch fetches a **fresh Epic sign-in token** right before Proton starts, so online games
  and games that check ownership work as they do in the Epic launcher. Offline, it falls back to an offline launch.
- **Updates** are checked when you open the library (at most every 6 hours) or with Check for updates.
- **Repair / Verify files** checks the game's files against Epic's manifest and fixes broken ones.
- **Epic cloud saves** for games that support them: *Download save* / *Upload save* on the game page (after the
  game has run once, so Proton has created its save folder).
- **Uninstall** removes the files and the shortcut, and lets you choose whether to keep the Proton prefix (saves).
- Installs to internal storage or any SD card / USB drive (Quick Access → Epic Library → Settings).

Games that Epic sells but that are installed through another launcher (EA app, Ubisoft Connect) are hidden by default
and can't be installed here.

Nothing runs in the background: the library is fetched (and cached for 30 minutes) and updates are checked only when
you open it. The store is only contacted while the Browse tab is open. Downloads run one at a time.

## How it works

Downloads, updates, sign-in and launch tokens use **[Legendary](https://github.com/derrod/legendary)** 0.21.1, the
open-source Epic Games launcher (GPL-3.0). It's bundled unmodified and run as its own program with the system Python
(Bazzite/SteamOS ship Python 3.11+). Its data, including your Epic sign-in, lives in
`~/homebrew/settings/Epic Library/legendary/` (readable only by you) and never mixes with a `~/.config/legendary`
you may already have. Browse uses the Epic store's public catalog (the same one the website uses).

Each Steam shortcut runs the game's `.exe` through Proton with these launch options:

```
"~/homebrew/data/Epic Library/runtime/launch.sh" <app name> %command%
```

The wrapper asks Legendary for the game's Epic arguments and appends them to Steam's Proton command. Its log is
`~/homebrew/data/Epic Library/logs/launch.log`.

## Phone sign-in won't open?

The first sign-in option (Epic's activation code) doesn't use the local page at all: the QR opens epicgames.com/activate,
so any network works. The rest of this section is about the *Paste a code from my phone* option.

The QR page is served by the handheld itself on port 47615 (up to 47619), so your phone has to be on the same Wi-Fi
(not mobile data or a guest network, which keeps devices apart). Fedora-based systems such as Bazzite run a firewall;
the plugin can't change it without root, but it reads the firewall's rules and puts the page on a port they already
allow. If none is allowed, the sign-in screen says so and shows the one command that fixes it for every store
plugin, to run once in Desktop Mode (Konsole):

```
sudo firewall-cmd --permanent --add-port=47615-47619/tcp && sudo firewall-cmd --reload
```

Your phone may label the page "Not secure". That's expected for a page on your own network (there are no
certificates for local addresses); nothing on it goes through the internet, and it closes after you sign in.

## What gets installed where

| | |
|---|---|
| Games | `~/Games/epic/<Game>/` (or `<drive>/Games/epic/` when you pick an SD card) |
| Epic sign-in, installed-games list | `~/homebrew/settings/Epic Library/legendary/` |
| Steam shortcut ids | `~/homebrew/settings/Epic Library/games.json` |
| Library cache, icons, Legendary runtime, launch log | `~/homebrew/data/Epic Library/` |
| Saves | Steam's Proton prefix for the shortcut (`steamapps/compatdata/<shortcut id>`) |

Sign out from Quick Access → Epic Library → Settings.

## Notes

Unofficial plugin, not affiliated with or endorsed by Epic Games. It only downloads games your account owns, through
the same services the Epic launcher uses.

Tested logic: Python unit tests with Legendary and the store faked (`python3 -m unittest discover -s tests`).
Not yet tested on hardware, and the store browse queries were written against Epic's public GraphQL catalog without
a live test from the build machine.

## Build

```
pnpm install
pnpm build
./package.sh   # downloads the pinned wheels from PyPI, out/Epic-Library.zip
```
