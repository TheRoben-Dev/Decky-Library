#!/bin/bash
# Epic Library launch wrapper. Steam runs it from a game's launch options:
#   "<data dir>/runtime/launch.sh" <Epic app name> %command%
# %command% is Steam's own command line (Proton + the game's .exe). This asks Legendary for the
# game's Epic sign-in arguments (a fresh one-time exchange code, ownership token, user name/locale),
# appends them, and hands over to Steam's command. If Epic can't be reached it falls back to an
# offline launch, and if even that fails the game still starts, just without Epic arguments.
set -u
here="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
app="${1:-}"
shift || true
if [ -z "$app" ] || [ "$#" -eq 0 ]; then
  echo "usage: launch.sh <app name> %command%" >&2
  exit 64
fi
# shellcheck source=/dev/null
. "$here/paths.env"
log="$EPIC_LOGS/launch.log"
mkdir -p "$EPIC_LOGS" 2>/dev/null
[ -f "$log" ] && [ "$(stat -c %s "$log" 2>/dev/null || echo 0)" -gt 262144 ] && mv -f "$log" "$log.1"

lgd() {
  # Steam's runtime libraries and overlay must not leak into the system Python.
  env -u LD_PRELOAD -u LD_LIBRARY_PATH -u PYTHONHOME -u PYTHONPATH \
    LEGENDARY_CONFIG_PATH="$EPIC_CONFIG" PYTHONPYCACHEPREFIX="$EPIC_CACHE/pycache" \
    timeout 40 "$EPIC_PYTHON" -I "$here/lgd.py" "$@"
}

extract() {
  env -u LD_PRELOAD -u LD_LIBRARY_PATH "$EPIC_PYTHON" -I -c '
import json, sys
d = json.load(sys.stdin)
out = []
for a in d.get("game_parameters", []) + d.get("user_parameters", []) + d.get("egl_parameters", []):
    a = str(a)
    # The ownership token is a Linux path; inside Proton the game sees the root as drive Z:.
    if a.startswith("-epicovt=/"):
        a = "-epicovt=Z:" + a[len("-epicovt="):].replace("/", "\\")
    out.append(a)
sys.stdout.write("\0".join(out))'
}

{
  echo "== $(date '+%F %T') $app"
} >>"$log" 2>/dev/null

extra=()
if json="$(lgd launch "$app" --json --no-wine --skip-version-check 2>>"$log")" && [ -n "$json" ]; then
  mapfile -d '' -t extra < <(printf '%s' "$json" | extract 2>>"$log")
elif json="$(lgd launch "$app" --json --no-wine --skip-version-check --offline 2>>"$log")" && [ -n "$json" ]; then
  echo "online sign-in failed, launching offline" >>"$log"
  mapfile -d '' -t extra < <(printf '%s' "$json" | extract 2>>"$log")
else
  echo "Legendary gave no launch arguments; starting without them" >>"$log"
fi
echo "starting with ${#extra[@]} Epic arguments" >>"$log"
exec "$@" "${extra[@]}"
