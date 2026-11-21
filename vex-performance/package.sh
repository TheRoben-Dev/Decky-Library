#!/usr/bin/env bash
# Builds a Decky-installable zip: <Plugin Name>/{dist,bin,main.py,plugin.json,...}
# The official lsfg-vk build is fetched from upstream and checksum-verified.
# It is shipped unmodified (lsfg-vk is CC BY-NC-ND 4.0, see THIRD_PARTY.md).
set -euo pipefail
cd "$(dirname "$0")"
NAME="Vex Performance"
LSFG_VERSION="2.0.0"
LSFG_URL="https://builds.lsfg-vk.dev/lsfg-vk-${LSFG_VERSION}.tar.xz"
LSFG_SHA256="08bdbdf373a111022df87dac7aa87e3b564bb841f961552e3ca85fea12b5aa74"
LSFG_FILE="bin/lsfg-vk-${LSFG_VERSION}.tar.xz"

mkdir -p bin
if [ ! -f "$LSFG_FILE" ] || ! echo "$LSFG_SHA256  $LSFG_FILE" | sha256sum -c --status; then
  echo "Downloading lsfg-vk $LSFG_VERSION"
  curl -fL --retry 3 -o "$LSFG_FILE.part" "$LSFG_URL"
  mv "$LSFG_FILE.part" "$LSFG_FILE"
fi
echo "$LSFG_SHA256  $LSFG_FILE" | sha256sum -c

rm -rf out && mkdir -p "out/$NAME/bin"
cp -r dist main.py plugin.json package.json LICENSE README.md THIRD_PARTY.md "out/$NAME/"
cp "$LSFG_FILE" "out/$NAME/bin/"
mkdir -p "out/$NAME/py_modules" && cp -r py_modules/vex "out/$NAME/py_modules/"
rm -f "out/$NAME/dist/"*.map
find "out/$NAME" -name __pycache__ -prune -exec rm -rf {} +
(cd out && zip -qr Vex-Performance.zip "$NAME")
echo "out/Vex-Performance.zip"
