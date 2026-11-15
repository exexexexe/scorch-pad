# Scorch Pad — phone controller for Scorched Earth

Control Scorched Earth on your TV from your phone. The Raspberry Pi runs a
small web server. That server creates a **virtual USB keyboard and mouse**
(Linux `uinput`), so the game gets real key presses. This works with
DOSBox and with a browser running js-dos / DOS.Zone, on X11 and Wayland.

```
 iPhone (Safari / Home Screen app / Shortcuts / Siri)
        │  http://raspberrypi.local:8080
        ▼
 Raspberry Pi: server.py ──uinput──► "virtual keyboard" ──► Scorched Earth
```

Hot-seat play works out of the box: every player opens the same page, and
whoever's turn it is presses the buttons.

## Install on the Pi

```bash
git clone https://github.com/exexexexe/scorch-pad.git ~/scorched-controller
cd ~/scorched-controller
bash install.sh
```

The install script:

1. installs `python3-evdev`,
2. lets the `input` group use `/dev/uinput`,
3. installs a systemd service, which then starts on every boot.

When it finishes it prints a URL like `http://192.168.1.42:8080`. Open that
URL on your phone. **Log out and back in once** (or reboot) so the new
group membership takes effect.

To try it without installing: `sudo python3 server.py`.
To test only the web page on any computer: `python3 server.py --dry-run`.

> **Keep the game window focused.** The keys go to whatever window has
> focus on the Pi, the same as a real keyboard.
>
> **Browser + pointer lock tip:** if the game runs in Chromium with the
> mouse captured, the **Esc** button also releases the mouse capture
> (that's Chromium's "Press Esc to reveal your mouse pointer" banner).
> That is harmless: tap the game once with the Mouse tab to recapture it.

### Add it to your Home Screen

In Safari open the page → Share → **Add to Home Screen**. It then opens
full-screen like an app. Turn the phone sideways for the two-handed layout.

## The controller

| Tab | What's on it |
|---|---|
| **Battle** | Angle ◀ ▶ (←/→), power ▼ ▲ (↓/↑), PgDn/PgUp, previous/next weapon (Shift+Tab / Tab), Inventory (I), Esc, Enter, and a big **FIRE** (Space). Hold a button to repeat. Repeats speed up the longer you hold. |
| **Keys** | A full keyboard (letters, numbers, F1–F10, arrows) and a text box for typing player names. |
| **Mouse** | Touchpad for the setup menus: drag to move, tap = left click, two-finger tap = right click. |

**Unstick** (top right) releases every key, in case one ever gets stuck.

Need a different key on the Battle tab? Edit the `data-key="…"` attribute of
that button in `static/index.html` and reload the page. Use `/api/keys` to see
all key names.

## Apple Shortcuts / Siri

Every action is a plain URL. Use the **Get Contents of URL** action in
Shortcuts (method GET is fine). Replace `raspberrypi.local` with your Pi's
name or IP address.

| Shortcut name (= what you say to Siri) | URL |
|---|---|
| "Fire" | `http://raspberrypi.local:8080/api/tap?key=space` |
| "Next weapon" | `http://raspberrypi.local:8080/api/tap?key=tab` |
| "Aim left" | `http://raspberrypi.local:8080/api/tap?key=left&times=10` |
| "Aim right" | `http://raspberrypi.local:8080/api/tap?key=right&times=10` |
| "More power" | `http://raspberrypi.local:8080/api/tap?key=up&times=20` |
| "Less power" | `http://raspberrypi.local:8080/api/tap?key=down&times=20` |
| "Start game" | `http://raspberrypi.local:8080/api/tap?key=enter` |

Fancier versions:

- **Macro** (comma-separated `key*count`, `wait*seconds` to pause):
  `…/api/seq?do=left*15,up*30,wait*0.3,space` aims, powers up and fires.
- **Ask for a number:** Shortcut actions *Ask for Input (Number)* → *Get
  Contents of URL* with
  `http://raspberrypi.local:8080/api/tap?key=right&times=` followed by the
  *Provided Input* variable. Max 100 taps per call.
- **Key combos:** `…/api/combo?keys=shift+tab`
- **Typing:** `…/api/type?text=Destroyer` (URL-encode spaces as `%20`)

Shortcuts can also go on the Lock Screen, in Control Center, or on the
Action button. "Hey Siri, fire!" then works from across the room.

## API reference

All endpoints accept GET or POST. Parameters go in the query string, or in a
form or JSON body.

| Endpoint | Params | Does |
|---|---|---|
| `/api/tap` | `key`, `times` (1–100) | press + release |
| `/api/combo` | `keys=ctrl+left` | hold the first keys, tap the last one |
| `/api/seq` | `do=left*5,wait*0.5,space` | a macro |
| `/api/type` | `text` | type a string (handles capitals & symbols) |
| `/api/down` / `/api/up` | `key` | hold / release (auto-release after 2 s) |
| `/api/release` | — | release everything |
| `/api/mouse` | `dx`, `dy`, `wheel` | move the mouse |
| `/api/click` | `button=left\|right\|middle`, optional `state=down\|up` | click |
| `/api/keys` | — | list key names |

### Optional password

Anyone on your Wi-Fi can open the page. To require a token, add
`--token mysecret` to the `ExecStart` line in
`/etc/systemd/system/scorched-controller.service` and run
`sudo systemctl daemon-reload && sudo systemctl restart scorched-controller`.
Then:

- open the page once as `http://pi:8080/?token=mysecret` (the phone remembers it),
- add `&token=mysecret` to each Shortcut URL.

## Troubleshooting

- **The page works but nothing happens in the game:** click the game window
  on the Pi once so it has focus. Check the logs with
  `journalctl -u scorched-controller -f`.
- **`PermissionError: /dev/uinput`:** log out and back in after
  `install.sh`, or run once with `sudo`.
- **Game runs on a different computer than the Pi?** Run `server.py` on the
  computer that shows the game (any Linux box). Or plug the Pi in as a USB
  keyboard: a Pi Zero/4/5 in USB-gadget mode can do that. That setup needs
  a different backend.
