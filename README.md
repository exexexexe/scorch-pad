# Scorch Pad — phone controller for Scorched Earth

Control Scorched Earth on your TV from your phone. The Raspberry Pi runs a
small web server. The game runs in the TV's web browser, served by the Pi,
and your phone's button presses travel to it over Wi-Fi (see *Play on the TV*
below). If the game runs on a screen plugged into the Pi, the presses go
through a virtual keyboard (Linux `uinput`) instead.

```
 iPhone (Safari / Home Screen app / Shortcuts / Siri)
        │  http://raspberrypi.local:8080
        ▼
 Raspberry Pi: server.py ──Wi-Fi──► LG TV browser (/play) running Scorched Earth
                       └─uinput─► or a game on the Pi's own screen
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

## Play on the TV — wirelessly, with one button

The Pi can sit in another room. It **hosts the game as a web page**, and the
living-room **LG TV's web browser** plays it. Your phone's button presses go
to the Pi, and the Pi passes them to the TV over Wi-Fi. No cables, and no
video streaming, so there's no lag.

```
 phone ──Wi-Fi──► Pi (other room) ──Wi-Fi──► LG TV browser running the game
                    │
                    └── "Play" button: wakes the TV and opens the game on it
```

### 1. Put the game on the Pi (once)

The game files aren't in this repo. Use your own copy of the shareware
release (version 1.5): get the zip from the author's official site or a
shareware archive, then copy it to the Pi:

```bash
bash ~/scorched-controller/game/setup-game.sh ~/Downloads/scorch15.zip
```

This downloads the in-browser DOS emulator (js-dos) to the Pi and packs the
game for it. To check it worked, open `http://raspberrypi.local:8080/play` in
any browser on your Wi-Fi.

### 2. Connect the LG TV (once)

1. On the TV, turn on **Settings → General → Devices → TV Management →
   Turn on via Wi-Fi**. On older models it's **Settings → Network → LG Connect
   Apps** and **Mobile TV On**. This lets the Pi wake the TV from standby.
2. With the TV on, run this on the Pi:
   ```bash
   ~/scorched-controller/.venv/bin/python ~/scorched-controller/tv/lgtv.py pair
   ```
   If it can't find the TV, add its IP address after `pair`. To find the IP:
   TV Settings → Network → Wi-Fi → Advanced, or run `lgtv.py find`.
3. Press **Allow** on the TV when it asks.

### 3. Play

| What | Link |
|---|---|
| ▶ Game on the TV (wakes it, opens the game) | `http://raspberrypi.local:8080/api/launch` |
| ■ Close the game | `http://raspberrypi.local:8080/api/quit` |
| Close + TV off | `http://raspberrypi.local:8080/api/quit?tv=off` |
| TV on / off | `http://raspberrypi.local:8080/api/tv?state=on` / `state=off` |

- **Phone controller:** press the yellow **▶ Play on TV** button. The
  header says **📺 TV connected** once the game is up on the TV.
- **Your dashboard:** make a button that opens (HTTP GET) the launch URL.
  For Home Assistant, in `configuration.yaml`:
  ```yaml
  rest_command:
    scorched_earth:
      url: "http://raspberrypi.local:8080/api/launch"
  ```
  Then add a dashboard button with `tap_action: perform-action` →
  `rest_command.scorched_earth`.
- **Shortcuts / Siri:** "Get Contents of URL" → the launch link.

When the game opens, **press OK on the TV remote once**. That makes it full
screen and turns on the sound; browsers only allow those after a button
press. After that, play with the phones.

### If something's off

- **The TV opens the browser but the game doesn't start:** older TVs (before
  about 2018) may have a browser too old for js-dos. Check that `/play` works
  on your laptop. If it does, it's the TV.
- **The TV doesn't wake up:** check the "Turn on via Wi-Fi" setting. Then run
  `lgtv.py on` and read the message. Some TVs only wake over a network
  cable, so turn it on with the remote and the button will still open the
  game.
- **The TV asks to "Allow" again:** pair again. LG sometimes forgets the
  pairing after a firmware update.

### Pi plugged into a screen instead?

Without `lgtv.json`, the Play button runs the game on the Pi's own HDMI
output with DOSBox. Set that up with `setup-game.sh <zip> --hdmi`.
`game/tv.sh` then switches the TV over HDMI-CEC.

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
| `/api/launch` | — | wake the TV and open the game on it |
| `/api/quit` | `tv=off` (optional) | close the game (and turn the TV off) |
| `/api/tv` | `state=on\|off` | just the TV |
| `/api/status` | — | is the game showing on the TV? |
| `/play` | — | the game page itself (what the TV opens) |

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
