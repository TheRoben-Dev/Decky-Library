# GOG Library

Your GOG games and the GOG store in Steam Game Mode, Nightgrid-styled and fully controller-driven.

- **Sign in without typing.** Scan a QR code with your phone, sign in on GOG's own page there (your password manager
  works, and your password never reaches the handheld), then paste the address GOG lands on back into the page. Done.
- **Browse & search the GOG store** (Browse tab): sort by Trending, Bestselling, Newest, Top rated, Biggest discount
  or A–Z, filter by price (Free, On sale, under $10/$25), genre and system. **Controller support is on by default**
  (GOG's own "Controller support" feature filter; switch to All games to see everything). Search uses the on-screen
  keyboard. Games you own install directly (X on the tile). Paid games show their price; **Buy on GOG** opens the
  game's store page in Steam's browser, or **Buy on phone** shows a QR code; after buying, *I bought it* moves it to
  your library. Free games work the same way (*Get it on GOG*, then *I added it*), because GOG only lets an account
  download games that are in its library.
- **Store pages for every game**: opening a game (from Browse or your library) shows its screenshots (D-pad through
  them, A for full screen), trailers, rating and review count, release date, genres, developer, publisher, game modes,
  features and the full description. Details come from GOG's store and games database and are cached for 3 days.
- **Your library**: every game you own in a full-screen grid: Library, Installed, Updates, Downloads.
  L1/R1 switch tabs, A opens a game, X installs or plays it right from the grid.
- **Native Linux first, Windows through Proton.** When a game has both you choose which wins (Settings), or pick on the
  game page. Linux versions come from GOG's Linux installers (unpacked in Python, nothing is executed). Windows versions
  are downloaded file by file from GOG Galaxy's content system, like Galaxy and Heroic do, with owned DLCs included;
  games without a Galaxy build fall back to GOG's Windows installer (unpacked with `innoextract` when it's installed,
  otherwise run once through Proton).
- **Plays from Steam.** Each installed game becomes a non-Steam shortcut with GOG's official artwork (vertical cover,
  hero, logo, icon) or, if you prefer, artwork drawn in the Nightgrid look. Windows games get Proton set automatically,
  and the launch file comes from the game's own GOG launch info (`goggame-<id>.info`).
- **Updates** are checked when you open the library (at most every 6 hours) or with Check for updates. Galaxy builds
  only download the files that changed; installer updates keep files the game created in its own folder (saves,
  settings). An interrupted Windows download continues where it stopped.
- **Uninstall** removes the files and the shortcut. For Windows games you choose whether to keep the Proton prefix,
  which holds their saves.
- Installs to internal storage or any SD card / USB drive (Quick Access → GOG Library → Settings), in the game language
  you pick.

Nothing runs in the background: the library is fetched (and cached for 30 minutes) and updates are checked only when you
open it. Downloads run one at a time and report progress only while they run.

## Signing in

The QR code on the sign-in screen opens a one-time page served by the handheld itself on your Wi-Fi. It links to GOG's
sign-in (`auth.gog.com`, with GOG Galaxy's public client id, as every open-source GOG launcher uses). After you sign in,
GOG shows a mostly empty page whose address contains `code=…`; copy that address and paste it into the first page. The
code works once and expires within minutes. That page only exists while the sign-in screen is open, answers on a random
address, takes one sign-in and closes.

The tokens are stored in `~/homebrew/settings/GOG Library/settings.json` (readable only by you), are only ever sent to
`*.gog.com` over HTTPS, and never reach the plugin's UI. Sign out from Quick Access → GOG Library → Settings.

## Phone sign-in won't open?

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
| Games | `~/Games/gog/<Title>-<id>/` (or `<drive>/Games/gog/` when you pick an SD card) |
| Install records | `~/homebrew/settings/GOG Library/installed.json` |
| Library cache, artwork links, icons, file lists | `~/homebrew/data/GOG Library/` |
| Windows saves | Steam's Proton prefix for the shortcut (`steamapps/compatdata/<shortcut id>`) |

Not supported yet: macOS-only games, DLC installers for Linux versions (the Windows version includes owned DLCs),
GOG cloud saves, and beta branches.

## Notes

Unofficial plugin, not affiliated with GOG. It uses GOG's public endpoints (the ones GOG Galaxy and the open-source
launchers use) and only downloads games your account owns. No code from other launchers is included; see THIRD_PARTY.md.
