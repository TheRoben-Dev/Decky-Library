#!/usr/bin/env bash
# Builds a Decky-installable zip: Nightgrid Sounds/{dist,main.py,plugin.json,...}
set -euo pipefail
cd "$(dirname "$0")"
NAME="Nightgrid Sounds"
rm -rf out && mkdir -p "out/$NAME"
cp -r dist main.py plugin.json package.json LICENSE README.md "out/$NAME/"
rm -f "out/$NAME/dist/"*.map
(cd out && zip -qr Nightgrid-Sounds.zip "$NAME")
echo "out/Nightgrid-Sounds.zip"
