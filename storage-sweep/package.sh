#!/usr/bin/env bash
# Builds a Decky-installable zip: Storage Sweep/{dist,main.py,plugin.json,...}
set -euo pipefail
cd "$(dirname "$0")"
NAME="Storage Sweep"
rm -rf out && mkdir -p "out/$NAME"
cp -r dist main.py plugin.json package.json LICENSE README.md "out/$NAME/"
mkdir -p "out/$NAME/py_modules" && cp -r py_modules/sweep "out/$NAME/py_modules/"
rm -f "out/$NAME/dist/"*.map
find "out/$NAME" -name __pycache__ -prune -exec rm -rf {} +
(cd out && zip -qr Storage-Sweep.zip "$NAME")
echo "out/Storage-Sweep.zip"
