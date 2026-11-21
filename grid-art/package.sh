#!/usr/bin/env bash
# Builds a Decky-installable zip: Grid Art/{dist,main.py,plugin.json,...}
set -euo pipefail
cd "$(dirname "$0")"
NAME="Grid Art"
rm -rf out && mkdir -p "out/$NAME"
cp -r dist main.py plugin.json package.json LICENSE README.md "out/$NAME/"
mkdir -p "out/$NAME/py_modules" && cp -r py_modules/gridart "out/$NAME/py_modules/"
rm -f "out/$NAME/dist/"*.map
find "out/$NAME" -name __pycache__ -prune -exec rm -rf {} +
(cd out && zip -qr Grid-Art.zip "$NAME")
echo "out/Grid-Art.zip"
