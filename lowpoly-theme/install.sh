#!/usr/bin/env bash
# Run on the handheld (Desktop Mode terminal or over SSH) from this folder or next to Lowpoly.zip.
# Copies the theme to ~/homebrew/themes/Lowpoly. Then: Quick Access → CSS Loader → ⟳ Refresh,
# and enable "Lowpoly".
set -euo pipefail
cd "$(dirname "$0")"
DEST="$HOME/homebrew/themes"
[ -d "$DEST" ] || { echo "No $DEST — is Decky + CSS Loader installed?"; exit 1; }
if [ -f Lowpoly.zip ]; then
  rm -rf "$DEST/Lowpoly" && unzip -q -o Lowpoly.zip -d "$DEST"
else
  rm -rf "$DEST/Lowpoly" && cp -r Lowpoly "$DEST/"
fi
echo "Installed to $DEST/Lowpoly — refresh CSS Loader and enable Lowpoly."
