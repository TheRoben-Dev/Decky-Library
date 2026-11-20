# Library Hub (Decky plugin)

One Quick Access panel that installs, updates and removes everything published from this repo:
the [Nightgrid](../nightgrid-theme/) CSS Loader theme and every Decky plugin here (Vex Performance,
Proton Picker, Ally Tweaks, and any later ones), including Library Hub itself.

It replaces **Nightgrid Updater**: on first start Library Hub removes it (through Decky's uninstaller)
and shows a toast.

## What it does
- Lists every published item with the installed and latest version, and **Install**, **Update to X**
  and **Uninstall** buttons. Library Hub's own update is in its own section.
- Plugins are installed through Decky Loader's own installer (`utilities/install_plugin`), so you get
  Decky's normal confirmation prompt and Decky loads the new version without a restart.
- The theme is installed into `~/homebrew/themes/Nightgrid` and CSS Loader is reloaded; your Nightgrid
  options in CSS Loader are kept.
- Dependencies:
  - No CSS Loader? A banner offers **Install CSS Loader** from Decky's own store (Decky's prompt again).
  - Vex Performance shows whether **Lossless Scaling** is installed in Steam (needed for frame
    generation) and opens its Steam store page if not.
- About 15 s after boot it checks once and toasts if updates exist. It never installs anything without
  you pressing a button and confirming.

## Security
- Only releases from `TheRoben-Dev/Decky-Library` tagged `<folder>-vX.Y.Z` (not drafts or pre-releases),
  over HTTPS with certificate checks; redirects may only go to GitHub hosts.
- Asset URLs must belong to that repo and that release's tag.
- Every zip must match its release's `.sha256` file, and GitHub's own asset digest when reported.
  For plugins this is checked here **before** Decky is asked to install, and Decky checks the same
  SHA-256 again on its own download. (Decky removes the old copy before unpacking, so checking first
  means a bad release can't leave you with neither version.)
- Plugin zips are inspected first: exactly one folder whose name matches its `plugin.json`, a `main.py`,
  no absolute paths, `..`, links or oversized content, and the version must match the release.
- Theme zips: only `Nightgrid/…`, valid `theme.json`, staged and swapped in with rollback.
- CSS Loader comes from Decky's store index (`plugins.deckbrew.xyz`), with the hash the store publishes;
  that host is allowed only for that one lookup.
- Runs as your user (no root flag). Root-level work (placing plugin folders) is done by Decky itself.

## Releasing (maintainer)
Bump `version` in a plugin's `package.json` and push to `main`, a `claude/*` or an `add-*` branch:
`.github/workflows/plugin-release.yml` builds it, tags `<folder>-vX.Y.Z` on that commit and publishes
the zip + `.sha256` (title `<plugin.json name> vX.Y.Z`). The theme works the same way from
`theme.json` via `nightgrid-release.yml`. Versions that already have a release are skipped.
A new plugin needs `plugin.json`, `package.json` and a `package.sh` that leaves one `out/*.zip`.

## Build
```
pnpm install
pnpm build
pnpm test        # Python tests: release catalog, checksums, zip checks, theme install
./package.sh     # → out/Library-Hub.zip
```
First install: Decky → Developer → Install Plugin from URL (the `Library-Hub.zip` release asset) or
from zip. After that it updates itself.
