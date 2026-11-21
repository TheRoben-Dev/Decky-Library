#!/usr/bin/env bash
# Builds a Decky-installable zip: Epic Library/{dist,main.py,plugin.json,runtime/...}
# runtime/site gets Legendary and its dependencies as exact, hash-checked wheels from PyPI
# (requirements-runtime.txt), unpacked unmodified. pycryptodomex is the only compiled one: an
# abi3 wheel, so it works with any system Python 3.11+ on x86_64.
set -euo pipefail
cd "$(dirname "$0")"
NAME="Epic Library"
WHEELS="$(mktemp -d)"
trap 'rm -rf "$WHEELS"' EXIT
python3 -m pip download -q --no-deps --require-hashes --only-binary=:all: \
  --platform manylinux2014_x86_64 --python-version 3.11 --implementation cp \
  -d "$WHEELS" -r requirements-runtime.txt
rm -rf out runtime/site && mkdir -p "out/$NAME" runtime/site
for w in "$WHEELS"/*.whl; do python3 -m zipfile -e "$w" runtime/site/; done
cp -r dist main.py plugin.json package.json LICENSE README.md THIRD_PARTY.md requirements-runtime.txt "out/$NAME/"
mkdir -p "out/$NAME/py_modules" && cp -r py_modules/epiclib "out/$NAME/py_modules/"
cp -r runtime "out/$NAME/"
chmod +x "out/$NAME/runtime/launch.sh"
rm -f "out/$NAME/dist/"*.map
find "out/$NAME" -name __pycache__ -prune -exec rm -rf {} +
(cd out && zip -qr Epic-Library.zip "$NAME")
echo "out/Epic-Library.zip"
