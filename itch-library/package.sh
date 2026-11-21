#!/usr/bin/env bash
# Builds a Decky-installable zip: Itch Library/{dist,main.py,plugin.json,...}
set -euo pipefail
cd "$(dirname "$0")"
NAME="Itch Library"
rm -rf out && mkdir -p "out/$NAME"
cp -r dist main.py plugin.json package.json LICENSE README.md THIRD_PARTY.md "out/$NAME/"
mkdir -p "out/$NAME/py_modules" && cp -r py_modules/itchlib "out/$NAME/py_modules/"
rm -f "out/$NAME/dist/"*.map
find "out/$NAME" -name __pycache__ -prune -exec rm -rf {} +
(cd out && zip -qr Itch-Library.zip "$NAME")
echo "out/Itch-Library.zip"
