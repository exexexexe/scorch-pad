#!/usr/bin/env bash
# Control the TV over HDMI-CEC:  tv.sh on | off
#   on  = wake the TV and switch its input to the Pi
#   off = put the TV in standby
# Needs cec-ctl (apt install v4l-utils) and a TV with CEC enabled
# (Samsung "Anynet+", LG "SimpLink", Sony "Bravia Sync", Philips "EasyLink").
# Pi 4/5: /dev/cec0 is the HDMI port next to the USB-C power, /dev/cec1 the other.
DEV="${CEC_DEV:-}"
if [ -z "$DEV" ]; then
  for d in /dev/cec0 /dev/cec1; do
    [ -e "$d" ] || continue
    # pick the port that has a TV attached (a real physical address)
    if cec-ctl -d "$d" 2>/dev/null | grep -q 'Physical Address.*[1-9]\.'; then DEV="$d"; break; fi
  done
  DEV="${DEV:-/dev/cec0}"
fi
command -v cec-ctl >/dev/null || { echo "cec-ctl missing (sudo apt install v4l-utils)"; exit 0; }
[ -e "$DEV" ] || { echo "no $DEV - HDMI-CEC not available"; exit 0; }

cec-ctl -d "$DEV" --playback --osd-name "Scorch Pad" >/dev/null 2>&1
case "${1:-on}" in
  on)
    cec-ctl -d "$DEV" --to 0 --image-view-on >/dev/null 2>&1
    PA="$(cec-ctl -d "$DEV" 2>/dev/null | awk -F': *' '/Physical Address/{print $2; exit}')"
    [ -n "$PA" ] && cec-ctl -d "$DEV" --to 0 --active-source phys-addr="$PA" >/dev/null 2>&1
    echo "TV on, input -> Pi ($DEV $PA)" ;;
  off)
    cec-ctl -d "$DEV" --to 0 --standby >/dev/null 2>&1; echo "TV standby" ;;
  *) echo "usage: $0 on|off"; exit 1 ;;
esac
