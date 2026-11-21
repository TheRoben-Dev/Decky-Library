#!/usr/bin/env bash
# Builds out/Nightgrid.zip: one "Nightgrid" folder, ready to drop into ~/homebrew/themes/.
set -euo pipefail
cd "$(dirname "$0")"
rm -rf out && mkdir -p out
python3 -m json.tool Nightgrid/theme.json > /dev/null
zip -qr -X out/Nightgrid.zip Nightgrid -x '*.DS_Store'
echo "out/Nightgrid.zip"
