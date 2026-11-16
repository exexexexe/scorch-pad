#!/usr/bin/env bash
# Put Scorched Earth on the Pi.
#
#   bash game/setup-game.sh ~/Downloads/scorch15.zip     # a zip file
#   bash game/setup-game.sh /media/usb/SCORCH            # a folder
#   bash game/setup-game.sh https://example.com/s.zip    # a download link
#
# It prepares the game for the TV's web browser (js-dos, served by the Pi).
# Add --hdmi to also install DOSBox, for a screen plugged into the Pi.
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
JSDOS_VERSION="8.5.2"
SRC=""; HDMI=0
for a in "$@"; do case "$a" in --hdmi) HDMI=1 ;; *) SRC="$a" ;; esac; done
GAME_DIR="${SCORCH_GAME_DIR:-$HOME/games/scorch}"
if [ -z "$SRC" ]; then
  echo "usage: bash $0 <zip file | folder | URL of the shareware zip> [--hdmi]"; exit 1
fi
command -v unzip >/dev/null || { sudo apt-get update -qq; sudo apt-get install -y unzip; }

mkdir -p "$GAME_DIR"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
case "$SRC" in
  http://*|https://*)
    echo "==> Downloading the game"; curl -fL "$SRC" -o "$TMP/game.zip"; SRC="$TMP/game.zip" ;;
esac
if [ -d "$SRC" ]; then cp -r "$SRC"/. "$GAME_DIR"/; else unzip -o -q "$SRC" -d "$GAME_DIR"; fi

# Find the game's EXE (it may be inside a sub-folder of the zip)
EXE="$(find "$GAME_DIR" -maxdepth 3 -iname 'scorch*.exe' | head -n1)"
[ -n "$EXE" ] || { echo "Couldn't find SCORCH.EXE in $GAME_DIR - is this the right zip?"; exit 1; }
EXE_DIR="$(dirname "$EXE")"; EXE_NAME="$(basename "$EXE")"

# ---- 1. Web version for the TV: js-dos + a game bundle -------------------
if [ ! -f "$DIR/static/jsdos/js-dos.js" ]; then
  echo "==> Downloading js-dos $JSDOS_VERSION (the in-browser DOS emulator)"
  curl -fL "https://registry.npmjs.org/js-dos/-/js-dos-$JSDOS_VERSION.tgz" -o "$TMP/jsdos.tgz"
  tar xzf "$TMP/jsdos.tgz" -C "$TMP"
  mkdir -p "$DIR/static/jsdos/emulators"
  cp "$TMP/package/dist/js-dos.js" "$TMP/package/dist/js-dos.css" "$DIR/static/jsdos/"
  find "$TMP/package/dist/emulators" -maxdepth 1 -type f \
    ! -name '*.map' ! -name '*.symbols' ! -name '*-dbg*' \
    -exec cp {} "$DIR/static/jsdos/emulators/" \;
fi

echo "==> Packing the game for the browser"
mkdir -p "$DIR/static/game"
python3 - "$EXE_DIR" "$EXE_NAME" "$DIR/static/game/scorch.jsdos" <<'PY'
import os, sys, zipfile
src, exe, out = sys.argv[1:]
conf = f"""[sdl]
autolock=false

[cpu]
cycles=auto

[autoexec]
echo off
mount c .
c:
{exe}
"""
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for root, _, files in os.walk(src):
        for f in files:
            p = os.path.join(root, f)
            z.write(p, os.path.relpath(p, src))
    z.writestr(".jsdos/dosbox.conf", conf)
print("   ", out, os.path.getsize(out) // 1024, "KB")
PY

# ---- 2. Optional: DOSBox for a screen plugged into the Pi ----------------
if [ "$HDMI" = 1 ]; then
  if ! command -v dosbox >/dev/null && ! command -v dosbox-staging >/dev/null; then
    echo "==> Installing DOSBox"
    sudo apt-get update -qq
    sudo apt-get install -y dosbox-staging 2>/dev/null || sudo apt-get install -y dosbox
  fi
  cat > "$GAME_DIR/dosbox-scorch.conf" <<CONF
# DOSBox settings for Scorched Earth (written by setup-game.sh)
[sdl]
fullscreen=true
fullresolution=desktop
output=opengl
autolock=true

[render]
aspect=true

[cpu]
cycles=auto

[autoexec]
mount c "$EXE_DIR"
c:
$EXE_NAME
exit
CONF
fi

echo
echo "Scorched Earth is ready."
echo "Test it in any browser:  http://$(hostname).local:8080/play"
