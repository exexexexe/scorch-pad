#!/usr/bin/env bash
# Run on the Raspberry Pi:  bash install.sh
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
USER_NAME="${SUDO_USER:-$USER}"

echo "==> Installing python3-evdev and HDMI-CEC tools"
sudo apt-get update -qq
sudo apt-get install -y python3-evdev python3-venv v4l-utils

echo "==> Installing the LG TV remote-control library"
python3 -m venv --system-site-packages "$DIR/.venv"
"$DIR/.venv/bin/pip" install -q "aiowebostv==0.10.0"

echo "==> Allowing the 'input' group to use /dev/uinput"
sudo cp "$DIR/99-uinput.rules" /etc/udev/rules.d/99-uinput.rules
echo uinput | sudo tee /etc/modules-load.d/uinput.conf >/dev/null
sudo modprobe uinput
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=misc --sysname-match=uinput || true
sudo usermod -aG input,video "$USER_NAME"

echo "==> Installing systemd service (runs as $USER_NAME)"
sed -e "s#/home/pi/scorched-controller#$DIR#" -e "s#^User=pi#User=$USER_NAME#" \
  "$DIR/scorched-controller.service" | sudo tee /etc/systemd/system/scorched-controller.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now scorched-controller.service

IP="$(hostname -I | awk '{print $1}')"
echo
echo "Done! On your phone open:  http://$IP:8080"
echo "     (or http://$(hostname).local:8080)"
echo "Logs: journalctl -u scorched-controller -f"
if [ ! -f "$DIR/static/game/scorch.jsdos" ]; then
  echo
  echo "Next: put the game on the Pi with"
  echo "  bash $DIR/game/setup-game.sh <scorched-earth zip or folder>"
fi
if [ ! -f "$DIR/lgtv.json" ]; then
  echo
  echo "Then connect your LG TV (it must be on):"
  echo "  $DIR/.venv/bin/python $DIR/tv/lgtv.py pair"
fi
