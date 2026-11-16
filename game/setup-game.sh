#!/usr/bin/env bash
# Put Scorched Earth on the Pi and make it ready for DOSBox.
#
#   bash game/setup-game.sh ~/Downloads/scorch15.zip     # a zip file
#   bash game/setup-game.sh /media/usb/SCORCH            # a folder
#   bash game/setup-game.sh https://example.com/s.zip    # a download link
#
# Files go to ~/games/scorch (override with SCORCH_GAME_DIR).
set -euo pipefail
SRC="${1:-}"
GAME_DIR="${SCORCH_GAME_DIR:-$HOME/games/scorch}"
if [ -z "$SRC" ]; then
  echo "usage: bash $0 <zip file | folder | URL of the shareware zip>"; exit 1
fi

if ! command -v dosbox >/dev/null && ! command -v dosbox-staging >/dev/null; then
  echo "==> Installing DOSBox"
  sudo apt-get update -qq
  sudo apt-get install -y dosbox-staging 2>/dev/null || sudo apt-get install -y dosbox
fi
command -v unzip >/dev/null || sudo apt-get install -y unzip

mkdir -p "$GAME_DIR"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
case "$SRC" in
  http://*|https://*)
    echo "==> Downloading"; curl -fL "$SRC" -o "$TMP/game.zip"; SRC="$TMP/game.zip" ;;
esac
if [ -d "$SRC" ]; then
  cp -r "$SRC"/. "$GAME_DIR"/
else
  unzip -o -q "$SRC" -d "$GAME_DIR"
fi

# Find the game's EXE (it may be inside a sub-folder of the zip)
EXE="$(find "$GAME_DIR" -maxdepth 3 -iname 'scorch*.exe' | head -n1)"
if [ -z "$EXE" ]; then
  echo "Couldn't find SCORCH.EXE in $GAME_DIR - is this the right zip?"; exit 1
fi
EXE_DIR="$(dirname "$EXE")"; EXE_NAME="$(basename "$EXE")"

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

echo
echo "Scorched Earth is ready in $EXE_DIR"
echo "Try it now:  bash $(cd "$(dirname "$0")" && pwd)/launch.sh"
