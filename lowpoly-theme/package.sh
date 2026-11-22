#!/usr/bin/env bash
# Builds out/Lowpoly.zip: one "Lowpoly" folder, ready to drop into ~/homebrew/themes/.
set -euo pipefail
cd "$(dirname "$0")"
rm -rf out && mkdir -p out
python3 -m json.tool Lowpoly/theme.json > /dev/null
zip -qr -X out/Lowpoly.zip Lowpoly -x '*.DS_Store'
echo "out/Lowpoly.zip"
