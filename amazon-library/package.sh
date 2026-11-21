#!/usr/bin/env bash
# Builds a Decky-installable zip: Amazon Library/{dist,main.py,plugin.json,...}
set -euo pipefail
cd "$(dirname "$0")"
NAME="Amazon Library"
rm -rf out && mkdir -p "out/$NAME"
cp -r dist main.py plugin.json package.json LICENSE README.md THIRD_PARTY.md "out/$NAME/"
mkdir -p "out/$NAME/py_modules" && cp -r py_modules/amzlib "out/$NAME/py_modules/"
rm -f "out/$NAME/dist/"*.map
find "out/$NAME" -name __pycache__ -prune -exec rm -rf {} +
(cd out && zip -qr Amazon-Library.zip "$NAME")
echo "out/Amazon-Library.zip"
