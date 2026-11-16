#!/usr/bin/env bash
# Turn the TV on, switch it to the Pi, and start Scorched Earth full-screen.
# Works from a terminal, a desktop icon, or the controller's /api/launch.
DIR="$(cd "$(dirname "$0")" && pwd)"
GAME_DIR="${SCORCH_GAME_DIR:-$HOME/games/scorch}"
CONF="$GAME_DIR/dosbox-scorch.conf"
LOG="${XDG_RUNTIME_DIR:-/tmp}/scorch-dosbox.log"

if [ ! -f "$CONF" ]; then
  echo "Game not set up yet - run: bash $DIR/setup-game.sh <zip>" >&2; exit 2
fi

# When started from the background service there is no desktop session in the
# environment, so point it at the Pi's screen (works on Wayland and X11).
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
if [ -z "${WAYLAND_DISPLAY:-}" ]; then
  for s in "$XDG_RUNTIME_DIR"/wayland-*; do
    [[ "$s" == *.lock ]] && continue
    [ -S "$s" ] && export WAYLAND_DISPLAY="$(basename "$s")" && break
  done
fi
export DISPLAY="${DISPLAY:-:0}"
[ -z "${XAUTHORITY:-}" ] && [ -f "$HOME/.Xauthority" ] && export XAUTHORITY="$HOME/.Xauthority"

"$DIR/tv.sh" on || true

DOSBOX="$(command -v dosbox-staging || command -v dosbox)"
pkill -x dosbox 2>/dev/null; pkill -x dosbox-staging 2>/dev/null; sleep 0.5
setsid nohup "$DOSBOX" -conf "$CONF" >"$LOG" 2>&1 < /dev/null &
echo "Started Scorched Earth (log: $LOG)"
