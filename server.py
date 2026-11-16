#!/usr/bin/env python3
"""
Scorched Earth phone controller - runs on the Raspberry Pi that plays the game.

It creates a virtual USB keyboard + mouse (Linux uinput) and serves a touch
controller web page. Whatever window has focus on the Pi (DOSBox, or Chromium
running js-dos / DOS.Zone) receives the keys exactly as if a real keyboard
were plugged in, so it works on X11 and Wayland alike.

    sudo apt install python3-evdev
    python3 server.py              # then open http://<pi-ip>:8080 on your phone

Use --dry-run to test the web page on a machine without uinput.

HTTP API (also what Apple Shortcuts calls - plain GET requests work):
    GET  /api/tap?key=space            press + release one key
    GET  /api/tap?key=left&times=5     tap a key several times
    GET  /api/combo?keys=ctrl+left     hold modifiers, tap the last key
    GET  /api/type?text=hello          type a string
    GET  /api/seq?do=left*5,up*3,space a macro: comma-separated key*count
    POST /api/down?key=left  /api/up?key=left   hold / release (stuck keys
                                       are auto-released after 2 s)
    POST /api/mouse?dx=10&dy=-4        move the mouse
    POST /api/click?button=left        click
    GET  /api/keys                     list of key names
    GET  /api/launch                   turn the TV on and start the game on it
    GET  /api/quit[?tv=off]            close the game (and turn the TV off)
    GET  /api/tv?state=on|off          just the TV
    GET  /api/status                   is a TV page connected? which TV mode?
    GET  /play                         the game page the TV opens (js-dos)

TV modes:
  * LG over Wi-Fi (after `python3 tv/lgtv.py pair <ip>`): the TV's browser
    opens /play and the phone's buttons are relayed to it.
  * HDMI (no lgtv.json): DOSBox runs on the Pi's own screen (game/launch.sh).
"""

import argparse
import json
import queue
import socket
import os
import threading
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")
GAME = os.path.join(HERE, "game")


LGTV_CONF = os.path.join(HERE, "lgtv.json")
VENV_PY = os.path.join(HERE, ".venv", "bin", "python")


def _run(cmd, timeout):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return False, f"{os.path.basename(cmd[-1])} timed out"


def run_script(name, *args):
    """Run one of the game/*.sh helpers (HDMI mode)."""
    return _run(["bash", os.path.join(GAME, name), *args], 20)


def lgtv(*args):
    """Run tv/lgtv.py (LG Wi-Fi mode)."""
    py = VENV_PY if os.path.exists(VENV_PY) else "python3"
    return _run([py, os.path.join(HERE, "tv", "lgtv.py"), *args], 60)


def lg_mode():
    return os.path.exists(LGTV_CONF)


def local_ip_towards(host):
    """The Pi's own IP address on the network the TV is on."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((host, 9))
        return s.getsockname()[0]
    except OSError:
        return socket.gethostname() + ".local"
    finally:
        s.close()

# Friendly key names -> evdev KEY_* names
KEY_NAMES = {
    "left": "KEY_LEFT", "right": "KEY_RIGHT", "up": "KEY_UP", "down": "KEY_DOWN",
    "space": "KEY_SPACE", "enter": "KEY_ENTER", "return": "KEY_ENTER",
    "tab": "KEY_TAB", "esc": "KEY_ESC", "escape": "KEY_ESC",
    "backspace": "KEY_BACKSPACE", "delete": "KEY_DELETE", "insert": "KEY_INSERT",
    "pageup": "KEY_PAGEUP", "pagedown": "KEY_PAGEDOWN", "pgup": "KEY_PAGEUP",
    "pgdn": "KEY_PAGEDOWN", "home": "KEY_HOME", "end": "KEY_END",
    "shift": "KEY_LEFTSHIFT", "ctrl": "KEY_LEFTCTRL", "alt": "KEY_LEFTALT",
    "minus": "KEY_MINUS", "-": "KEY_MINUS", "equal": "KEY_EQUAL", "=": "KEY_EQUAL",
    "plus": "KEY_EQUAL", "comma": "KEY_COMMA", ",": "KEY_COMMA",
    "period": "KEY_DOT", ".": "KEY_DOT", "slash": "KEY_SLASH", "/": "KEY_SLASH",
    "semicolon": "KEY_SEMICOLON", ";": "KEY_SEMICOLON",
    "apostrophe": "KEY_APOSTROPHE", "'": "KEY_APOSTROPHE",
    "leftbracket": "KEY_LEFTBRACE", "[": "KEY_LEFTBRACE",
    "rightbracket": "KEY_RIGHTBRACE", "]": "KEY_RIGHTBRACE",
    "backslash": "KEY_BACKSLASH", "\\": "KEY_BACKSLASH", "`": "KEY_GRAVE",
    " ": "KEY_SPACE",
}
for c in "abcdefghijklmnopqrstuvwxyz0123456789":
    KEY_NAMES[c] = "KEY_" + c.upper()
for n in range(1, 13):
    KEY_NAMES[f"f{n}"] = f"KEY_F{n}"

# Characters that need shift when typed
SHIFTED = {
    "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7",
    "*": "8", "(": "9", ")": "0", "_": "-", "+": "=", ":": ";", '"': "'",
    "<": ",", ">": ".", "?": "/", "{": "[", "}": "]", "|": "\\", "~": "`",
}

MOUSE_BUTTONS = {"left": "BTN_LEFT", "right": "BTN_RIGHT", "middle": "BTN_MIDDLE"}

HOLD_TIMEOUT = 2.0   # auto-release a held key if the phone stops refreshing it
TAP_TIME = 0.03      # seconds a tapped key stays down (DOS needs a moment)


class WebRelay:
    """Pushes key/mouse events to game pages open on the TV (Server-Sent Events)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.clients = []  # one queue.Queue per open /play page

    def add(self):
        q = queue.Queue()
        with self.lock:
            self.clients.append(q)
        return q

    def remove(self, q):
        with self.lock:
            if q in self.clients:
                self.clients.remove(q)

    @property
    def active(self):
        return bool(self.clients)

    def send(self, event):
        data = json.dumps(event)
        with self.lock:
            for q in self.clients:
                q.put(data)


class Device:
    """Sends input to the game.

    If a game page is open on the TV (/play), events go there over Wi-Fi.
    Otherwise they go to a virtual keyboard/mouse on the Pi itself (uinput),
    for a game running on a screen plugged into the Pi.
    """

    def __init__(self, dry_run=False):
        self.dry = dry_run
        self.lock = threading.Lock()
        self.held = {}  # key name -> last refresh time
        self.relay = WebRelay()
        self.ui = None
        if not dry_run:
            try:
                from evdev import UInput, ecodes
                self.e = ecodes
                keys = sorted({getattr(ecodes, v) for v in KEY_NAMES.values()})
                buttons = [getattr(ecodes, v) for v in MOUSE_BUTTONS.values()]
                self.ui = UInput(
                    {ecodes.EV_KEY: keys + buttons,
                     ecodes.EV_REL: [ecodes.REL_X, ecodes.REL_Y, ecodes.REL_WHEEL]},
                    name="scorched-phone-controller",
                )
                time.sleep(0.5)  # let the desktop pick up the new device
            except Exception as e:  # no evdev / no permission: web relay only
                print(f"Virtual keyboard unavailable ({e}); "
                      "controls only reach the TV page (/play).")
        threading.Thread(target=self._watchdog, daemon=True).start()

    def _code(self, name):
        return getattr(self.e, KEY_NAMES[name])

    def _emit_key(self, name, value):
        if self.relay.active:
            self.relay.send({"t": "key", "k": name, "d": value})
        elif self.ui:
            self.ui.write(self.e.EV_KEY, self._code(name), value)
            self.ui.syn()
        if self.dry:
            print(f"  key {name} {'down' if value else 'up'}")

    def down(self, name):
        with self.lock:
            if name not in self.held:
                self._emit_key(name, 1)
            self.held[name] = time.time()

    def up(self, name):
        with self.lock:
            if self.held.pop(name, None) is not None:
                self._emit_key(name, 0)

    def release_all(self):
        with self.lock:
            for name in list(self.held):
                self._emit_key(name, 0)
            self.held.clear()

    def tap(self, name, times=1, mods=()):
        with self.lock:
            for m in mods:
                self._emit_key(m, 1)
            for _ in range(times):
                self._emit_key(name, 1)
                time.sleep(TAP_TIME)
                self._emit_key(name, 0)
                time.sleep(TAP_TIME)
            for m in reversed(mods):
                self._emit_key(m, 0)

    def type_text(self, text):
        for ch in text:
            if ch == "\n":
                self.tap("enter")
            elif ch in SHIFTED:
                self.tap(SHIFTED[ch], mods=("shift",))
            elif ch.isalpha() and ch.isupper():
                self.tap(ch.lower(), mods=("shift",))
            elif ch in KEY_NAMES:
                self.tap(ch)

    def mouse(self, dx, dy, wheel=0):
        if self.dry:
            print(f"  mouse dx={dx} dy={dy} wheel={wheel}")
        if self.relay.active:
            self.relay.send({"t": "move", "dx": dx, "dy": dy})
            return
        if not self.ui:
            return
        with self.lock:
            if dx:
                self.ui.write(self.e.EV_REL, self.e.REL_X, dx)
            if dy:
                self.ui.write(self.e.EV_REL, self.e.REL_Y, dy)
            if wheel:
                self.ui.write(self.e.EV_REL, self.e.REL_WHEEL, wheel)
            self.ui.syn()

    def click(self, button="left", state=None):
        if self.dry:
            print(f"  mouse {button} {state or 'click'}")
        steps = {None: (1, 0), "down": (1,), "up": (0,)}[state]
        for i, v in enumerate(steps):
            if i:
                time.sleep(TAP_TIME)
            if self.relay.active:
                self.relay.send({"t": "btn", "b": button, "d": v})
            elif self.ui:
                with self.lock:
                    self.ui.write(self.e.EV_KEY, getattr(self.e, MOUSE_BUTTONS[button]), v)
                    self.ui.syn()

    def _watchdog(self):
        while True:
            time.sleep(0.25)
            now = time.time()
            with self.lock:
                for name, t in list(self.held.items()):
                    if now - t > HOLD_TIMEOUT:
                        self._emit_key(name, 0)
                        del self.held[name]


def norm_key(k):
    k = (k or "").strip()
    if len(k) == 1:
        return k.lower()
    return k.lower().replace("_", "").replace(" ", "")


class Handler(BaseHTTPRequestHandler):
    device: Device = None
    token: str = ""
    server_version = "ScorchController/1.0"

    def log_message(self, fmt, *args):
        if self.server.verbose:
            super().log_message(fmt, *args)

    # ---- helpers ---------------------------------------------------------
    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body)
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _ok(self, **extra):
        self._send(200, {"ok": True, **extra})

    def _err(self, msg, code=400):
        self._send(code, {"ok": False, "error": msg})

    def _key(self, q, field="key"):
        k = norm_key(q.get(field, [""])[0])
        if k not in KEY_NAMES:
            raise ValueError(f"unknown key '{k}' - see /api/keys")
        return k

    # ---- routing ---------------------------------------------------------
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST")
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode() if length else ""
        self._handle(extra=body)

    def do_GET(self):
        self._handle()

    def do_HEAD(self):
        self._handle()

    def _handle(self, extra=""):
        url = urlparse(self.path)
        q = parse_qs(url.query)
        if extra:
            # Allow form-encoded or JSON bodies (Shortcuts can send either)
            try:
                data = json.loads(extra)
                if isinstance(data, dict):
                    for k, v in data.items():
                        q.setdefault(k, [str(v)])
            except ValueError:
                for k, v in parse_qs(extra).items():
                    q.setdefault(k, v)

        path = url.path.rstrip("/") or "/"
        if not path.startswith("/api"):
            return self._static(path)

        if self.token and q.get("token", [""])[0] != self.token \
                and self.headers.get("X-Token") != self.token:
            return self._err("bad or missing token", 403)

        d = self.device
        if path == "/api/events":
            return self._events()
        try:
            if path == "/api/tap":
                times = max(1, min(100, int(q.get("times", ["1"])[0])))
                d.tap(self._key(q), times)
            elif path == "/api/down":
                d.down(self._key(q))
            elif path == "/api/up":
                d.up(self._key(q))
            elif path == "/api/release":
                d.release_all()
            elif path == "/api/combo":
                parts = [norm_key(p) for p in q.get("keys", [""])[0].replace(" ", "+").split("+") if p]
                bad = [p for p in parts if p not in KEY_NAMES]
                if not parts or bad:
                    return self._err(f"bad keys {bad}")
                d.tap(parts[-1], mods=tuple(parts[:-1]))
            elif path == "/api/type":
                d.type_text(q.get("text", [""])[0][:500])
            elif path == "/api/seq":
                steps = []
                for item in q.get("do", [""])[0].split(","):
                    item = item.strip()
                    if not item:
                        continue
                    name, _, n = item.partition("*")
                    if name.startswith("wait"):
                        steps.append(("wait", float(n or 0.5)))
                        continue
                    name = norm_key(name)
                    if name not in KEY_NAMES:
                        return self._err(f"unknown key '{name}'")
                    steps.append((name, max(1, min(100, int(n or 1)))))
                for name, n in steps:
                    if name == "wait":
                        time.sleep(min(n, 10))
                    else:
                        d.tap(name, n)
            elif path == "/api/mouse":
                d.mouse(int(float(q.get("dx", ["0"])[0])),
                        int(float(q.get("dy", ["0"])[0])),
                        int(float(q.get("wheel", ["0"])[0])))
            elif path == "/api/click":
                b = q.get("button", ["left"])[0]
                if b not in MOUSE_BUTTONS:
                    return self._err("button must be left/right/middle")
                st = q.get("state", [None])[0]
                d.click(b, st if st in ("down", "up") else None)
            elif path == "/api/launch":
                d.release_all()
                if self.server.dry:
                    print("  launch game")
                    return self._ok(message="dry run")
                if lg_mode():
                    with open(LGTV_CONF) as f:
                        tv_host = json.load(f)["host"]
                    port = self.server.server_address[1]
                    url = f"http://{local_ip_towards(tv_host)}:{port}/play"
                    if self.token:
                        url += f"?token={self.token}"
                    if d.relay.active:
                        d.relay.send({"t": "reload"})  # restart a game already open
                    ok, out = lgtv("open", url)
                else:
                    ok, out = run_script("launch.sh")
                return self._send(200 if ok else 500, {"ok": ok, "message": out})
            elif path == "/api/quit":
                if self.server.dry:
                    return self._ok(message="dry run")
                tv_off = q.get("tv", [""])[0] == "off"
                if lg_mode():
                    d.relay.send({"t": "stop"})
                    ok, out = lgtv("off") if tv_off else (True, "Game closed")
                else:
                    ok, out = run_script("quit.sh", *(["tv-off"] if tv_off else []))
                return self._send(200 if ok else 500, {"ok": ok, "message": out})
            elif path == "/api/tv":
                state = q.get("state", ["on"])[0]
                if state not in ("on", "off"):
                    return self._err("state must be on or off")
                if self.server.dry:
                    return self._ok(message="dry run")
                ok, out = lgtv(state) if lg_mode() else run_script("tv.sh", state)
                return self._send(200 if ok else 500, {"ok": ok, "message": out})
            elif path in ("/api/status", "/api/ping"):
                return self._ok(screens=len(d.relay.clients),
                                tv="lg" if lg_mode() else "hdmi",
                                keyboard=bool(d.ui))
            elif path == "/api/keys":
                return self._send(200, sorted(KEY_NAMES))
            else:
                return self._err("unknown endpoint", 404)
        except ValueError as e:
            return self._err(str(e))
        self._ok()

    def _events(self):
        """Server-Sent Events stream for the game page on the TV."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        relay = self.device.relay
        q = relay.add()
        try:
            self.wfile.write(b"retry: 2000\n\n")
            self.wfile.flush()
            while True:
                try:
                    msg = f"data: {q.get(timeout=5)}\n\n"
                except queue.Empty:
                    msg = ": ping\n\n"  # also detects a closed page
                self.wfile.write(msg.encode())
                self.wfile.flush()
        except OSError:
            pass
        finally:
            relay.remove(q)

    def _static(self, path):
        if path == "/":
            path = "/index.html"
        elif path == "/play":
            path = "/play.html"
        full = os.path.normpath(os.path.join(STATIC, path.lstrip("/")))
        if not full.startswith(STATIC) or not os.path.isfile(full):
            return self._send(404, "not found", "text/plain")
        types = {".html": "text/html; charset=utf-8", ".js": "text/javascript",
                 ".css": "text/css", ".json": "application/json",
                 ".png": "image/png", ".svg": "image/svg+xml",
                 ".webmanifest": "application/manifest+json",
                 ".wasm": "application/wasm", ".mjs": "text/javascript",
                 ".jsdos": "application/zip", ".woff": "font/woff"}
        ext = os.path.splitext(full)[1]
        with open(full, "rb") as f:
            self._send(200, f.read(), types.get(ext, "application/octet-stream"))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--token", default=os.environ.get("SCORCH_TOKEN", ""),
                    help="optional shared secret required on /api calls")
    ap.add_argument("--dry-run", action="store_true",
                    help="print key presses instead of sending them")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    Handler.device = Device(dry_run=args.dry_run)
    Handler.token = args.token
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    srv.verbose = args.verbose or args.dry_run
    srv.dry = args.dry_run
    print(f"Scorched Earth controller on http://{args.host}:{args.port}"
          f"{'  (dry run)' if args.dry_run else ''}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        Handler.device.release_all()


if __name__ == "__main__":
    main()
