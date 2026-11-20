# Handheld Library (Decky plugin)

Two things in one Quick Access panel:

1. **Handheld Ready collection** – keeps a normal Steam collection (Library → Collections) of the games
   in your library that are known to work on SteamOS **and** have full or partial controller support.
   The same list is in Quick Access with **Play** and **Page** buttons.
2. **Hidden games** – lists every game you've hidden in Steam, with **Play**, **Unhide**, **Page** and
   **Unhide all**.

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
- Hidden games come from Steam's own Hidden collection; Unhide uses Steam's own call
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
