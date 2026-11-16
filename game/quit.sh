#!/usr/bin/env bash
# Close the game. Pass "tv-off" to also put the TV in standby.
pkill -x dosbox 2>/dev/null; pkill -x dosbox-staging 2>/dev/null
[ "${1:-}" = "tv-off" ] && "$(cd "$(dirname "$0")" && pwd)/tv.sh" off
exit 0
