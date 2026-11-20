#!/usr/bin/env bash
# Builds a Decky-installable zip: Library Hub/{dist,main.py,plugin.json,...}
set -euo pipefail
cd "$(dirname "$0")"
NAME="Library Hub"
rm -rf out && mkdir -p "out/$NAME"
cp -r dist main.py plugin.json package.json LICENSE README.md "out/$NAME/"
mkdir -p "out/$NAME/py_modules" && cp -r py_modules/libhub "out/$NAME/py_modules/"
rm -f "out/$NAME/dist/"*.map
find "out/$NAME" -name __pycache__ -prune -exec rm -rf {} +
(cd out && zip -qr Library-Hub.zip "$NAME")
echo "out/Library-Hub.zip"
