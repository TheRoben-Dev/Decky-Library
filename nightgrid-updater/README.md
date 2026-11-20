# Nightgrid Updater (Decky plugin)

Installs and updates the [Nightgrid](../nightgrid-theme/) CSS Loader theme from this repository's
GitHub releases, from the Quick Access menu.

CSS Loader only updates themes that were installed from DeckThemes (it checks `api.deckthemes.com`
by theme id), so a theme hosted on GitHub can't update itself. This small companion plugin does it instead.

## What it does
- Quick Access → Nightgrid Updater shows the installed and latest version, with **Install / Update**
  and **Check for updates** buttons. About 15 s after boot it checks once and shows a toast if
  there's an update. It never installs anything on its own.
- Update = download → verify → swap in `~/homebrew/themes/Nightgrid` → ask CSS Loader to reload
  (the same call as its Refresh button). Your CSS Loader settings for Nightgrid (on/off, palette,
  colors, grid…) are kept.

## Security
- Only releases from `TheRoben-Dev/Decky-Library` tagged `nightgrid-theme-vX.Y.Z` (not drafts or
  pre-releases) are considered, over HTTPS with certificate checks; redirects may only go to GitHub hosts.
- The asset URL must belong to that repo and that release tag.
- The zip must match the release's `Nightgrid.zip.sha256`, and GitHub's own asset digest when the API
  reports one. Mismatch → nothing is changed.
- Every zip entry is checked before extracting: only `Nightgrid/…`, no absolute paths, `..`, links or
  oversized content; `theme.json` must be the Nightgrid theme with a manifest CSS Loader supports.
- It's staged outside the themes folder and swapped in; if the swap fails the old version is restored.
- Runs as your user (no root flag) and writes nothing outside `~/homebrew/themes/Nightgrid` and its own
  data folder.

The checksum guards against corrupted or swapped downloads; it comes from the same release, so the trust
anchor is the GitHub repo itself (only people with push access to it can publish a release).

## Releasing (maintainer)
Bump `version` in `nightgrid-theme/Nightgrid/theme.json`, merge, then:
```
git tag nightgrid-theme-v0.3.0 && git push origin nightgrid-theme-v0.3.0
```
`.github/workflows/nightgrid-release.yml` checks that the tag matches theme.json, builds `Nightgrid.zip`
and its `.sha256`, and publishes the release. The updater picks it up from there.
Tag `nightgrid-updater-vX.Y.Z` (matching `package.json`) to publish this plugin's own zip.

## Build
```
pnpm install
pnpm build
pnpm test        # Python tests for the release picking, checksum and safe install
./package.sh     # → out/Nightgrid-Updater.zip
```
Install the zip from Decky → Developer → Install Plugin from Zip.
