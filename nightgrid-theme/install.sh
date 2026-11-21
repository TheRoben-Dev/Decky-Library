#!/usr/bin/env bash
# Run on the handheld (Desktop Mode terminal or over SSH) from this folder or next to Nightgrid.zip.
# Copies the theme to ~/homebrew/themes/Nightgrid. Then: Quick Access → CSS Loader → ⟳ Refresh,
# and enable "Nightgrid".
set -euo pipefail
cd "$(dirname "$0")"
DEST="$HOME/homebrew/themes"
[ -d "$DEST" ] || { echo "No $DEST — is Decky + CSS Loader installed?"; exit 1; }
if [ -f Nightgrid.zip ]; then
  rm -rf "$DEST/Nightgrid" && unzip -q -o Nightgrid.zip -d "$DEST"
else
  rm -rf "$DEST/Nightgrid" && cp -r Nightgrid "$DEST/"
fi
echo "Installed to $DEST/Nightgrid — refresh CSS Loader and enable Nightgrid."
