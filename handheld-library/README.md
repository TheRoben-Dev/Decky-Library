# Handheld Library (Decky plugin)

1. **Handheld Ready collection** – keeps a normal Steam collection (Library → Collections) of the games
   in your library that are known to work on SteamOS **and** have full or partial controller support.
   The same list is in the plugin's panel with **Play** and **Page** buttons.
2. **Hidden games tab** – its own Quick Access tab (eye icon, next to Notifications/Friends/Settings)
   listing the hidden games that are installed on this device (with their square Steam icons), with **Play**, **Unhide**, **Page** and
   **Unhide all**.
   Optional **PIN lock** (4–8 digits, on-screen number pad): set, change or remove it in the plugin's
   panel (changing/removing needs the current PIN). Once unlocked it stays unlocked for 15 minutes (through
   Quick Access closing, Play, etc.) and locks again when that runs out or the device sleeps. A wrong PIN just shows an error (no lockout timer). Only a salted
   PBKDF2-SHA256 hash is stored, in `~/homebrew/settings/Handheld Library/pin.json`.
   **Forgot the PIN?** Delete that file from Desktop Mode (or over SSH); the lock is gone at once.
   **This is a privacy lock, not real security**: hidden games are still reachable through Steam itself
   (Library → Collections → Hidden, search, store pages). Turning off the Collections Library tab
   removes the easiest route; the Handheld Ready Library tab can stand in for it.
3. **Quick Access tab hiding** – in the plugin's panel, switch off any Quick Access tab you don't use
   (Steam's own, the Hidden games tab, or tabs other plugins add). Decky's own tab can't be hidden, so
   you can always get back to the setting. Applies the next time Quick Access opens.
4. **Plugin tabs** – give any installed Decky plugin (e.g. Vex Performance, Ally Tweaks) its own
   Quick Access tab with the plugin's icon; the tab shows the plugin's panel directly. The plugin stays
   in Decky's list too. Off for every plugin by default; added through Decky's tabs hook like the
   Hidden games tab, and a plugin that isn't loaded just shows a note instead of its panel.
5. **Library tab hiding** – switch off Steam Library tabs (Great on Deck / SteamOS Compatible,
   All games, Installed, Favorites, Collections, Non-Steam, Soundtracks, …), and optionally show the
   Handheld Ready collection as its own Library tab. Steam has no built-in setting for this. If every
   tab is off, Steam's tabs come back. If **TabMaster** is installed, this section turns itself off
   and leaves the Library to TabMaster.

## Rules (all changeable in Quick Access)
A game is in the collection when it has the controller support you pick **and** at least one accepted
rating:

| Setting | Default | Source |
|---|---|---|
| Steam Deck rating | Verified or Playable | Steam's Deck compatibility rating |
| Controller support | Full or partial | Steam's controller-support data (same rule as Steam's own Full/Partial Controller Support filters) |
| Also: SteamOS Compatible | On | Steam's newer rating for SteamOS PCs/handhelds that aren't a Deck |
| Also: ProtonDB | Off (Gold or Platinum / Platinum only) | protondb.com summary tier, cached for 7 days |
| Also: native Linux build | Off | Steam's "has native Linux binaries" flag |
| Never include Deck Unsupported | On | Valve's Unsupported rating overrides the other sources |

Software, tools and non-Steam shortcuts are left out (Steam has no ratings for them).

## How it works
- Reads the ratings Steam already has for every owned app (`appStore` overviews:
  `steam_deck_compat_category`, `steam_os_compat_category`, `has_native_linux_binaries`,
  `xbox_controller_support` + store categories 28/18). Field names were checked against Steam's own
  library code (Nov 2026 client).
- Creates the collection once through Steam's `collectionStore` and remembers its id, then adds/removes
  games so it matches. It re-syncs at startup, every 10 minutes and whenever you change a rule; it only
  saves when something changed. Collections sync through your Steam account, so it shows up on other
  devices too.
- It never touches a collection it didn't create: if a collection with the chosen name already exists,
  it asks you to pick another name. Renaming the collection in the panel renames the same collection.
- **Delete collection** removes it (your games stay) and turns sync off.
- Quick Access: the plugin doesn't patch Steam itself. It adds its tab through Decky Loader's own
  tabs hook (`window.__TABS_HOOK_INSTANCE`, the same code that adds Decky's tab) and filters the tab
  list right after Decky fills it, putting the full list back before each render so Decky's own
  bookkeeping is unaffected. If the hook is missing or anything throws, filtering stops and Quick
  Access renders exactly as without the plugin. Unloading the plugin restores every tab.
- Library tabs: Steam builds the tab list in a `useMemo` inside the Library component. Like
  TabMaster, the plugin patches the `/library` route and, only while that component renders, wraps
  `useMemo` to filter the list it returns (and add the collection tab, built from Steam's own
  "All games" tab with the collection swapped in). Anything unexpected returns Steam's own tabs;
  unloading the plugin turns the patch into a pass-through at once.
- Hidden games come from Steam's own Hidden collection (installed ones only); Unhide uses Steam's own call
  (`SetAppsAsHidden`), the same as the game's context menu.
- The Python backend only stores settings and looks up ProtonDB tiers (the browser side can't, because
  of CORS). At most 400 lookups per sync, 4 at a time; failures are retried next sync.

## Install
From **Library Hub** in Quick Access, or Decky → Developer → Install Plugin from Zip with
`Handheld-Library.zip` from this repo's releases.

## Build
```
pnpm install && pnpm build && ./package.sh   # → out/Handheld-Library.zip
python3 -m unittest discover -s tests -v
```

## Status
Not yet tested on a device. The Steam internals it uses are the same ones Steam's own library and
TabMaster use, but Steam can rename internals in a client update.
