#!/usr/bin/env bash
# Builds a Decky-installable zip: <Plugin Name>/{dist,movies,main.py,plugin.json,...}
# The videos in movies/ are rendered from render/movies.html (see README); they're committed so
# the release build doesn't need a browser.
set -euo pipefail
cd "$(dirname "$0")"
NAME="Nightgrid Movies"
rm -rf out && mkdir -p "out/$NAME"
cp -r dist movies main.py plugin.json package.json LICENSE README.md "out/$NAME/"
mkdir -p "out/$NAME/py_modules" && cp -r py_modules/ngmovies "out/$NAME/py_modules/"
rm -f "out/$NAME/dist/"*.map
find "out/$NAME" -name __pycache__ -prune -exec rm -rf {} +
(cd out && zip -qr Nightgrid-Movies.zip "$NAME")
echo "out/Nightgrid-Movies.zip"
