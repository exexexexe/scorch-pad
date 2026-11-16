#!/usr/bin/env python3
"""
Control an LG webOS TV over Wi-Fi: wake it, open the game page in its web
browser, turn it off.

    python3 tv/lgtv.py find               # look for LG TVs on the network
    python3 tv/lgtv.py pair 192.168.1.50  # once: press "Allow" on the TV
    python3 tv/lgtv.py open http://pi:8080/play
    python3 tv/lgtv.py on | off | status

Pairing saves the TV's address, MAC and access key in lgtv.json next to
server.py. Waking a TV that is switched off needs the TV setting
"Turn on via Wi-Fi" (Settings > General > Devices > TV Management, or
"Mobile TV On" on older models).
"""
import asyncio
import json
import os
import re
import socket
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONF = os.path.join(ROOT, "lgtv.json")


def load():
    try:
        with open(CONF) as f:
            return json.load(f)
    except FileNotFoundError:
        sys.exit("No TV paired yet. Run: python3 tv/lgtv.py pair <TV IP address>")


def save(conf):
    fd = os.open(CONF, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(conf, f, indent=2)


def discover(timeout=3.0):
    """Find LG webOS TVs with an SSDP search."""
    msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n"
           'MAN: "ssdp:discover"\r\nMX: 2\r\n'
           "ST: urn:lge-com:service:webos-second-screen:1\r\n\r\n")
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    s.settimeout(0.5)
    s.sendto(msg.encode(), ("239.255.255.250", 1900))
    found, end = {}, time.time() + timeout
    while time.time() < end:
        try:
            data, (ip, _) = s.recvfrom(4096)
        except socket.timeout:
            continue
        text = data.decode(errors="replace")
        name = re.search(r"(?im)^SERVER:\s*(.+)$", text)
        found[ip] = name.group(1).strip() if name else "LG TV"
    return found


def mac_of(ip):
    out = subprocess.run(["ip", "neigh", "show", ip],
                         capture_output=True, text=True).stdout
    m = re.search(r"lladdr ([0-9a-f:]{17})", out)
    return m.group(1) if m else None


def wake(mac):
    """Wake-on-LAN magic packet."""
    pkt = b"\xff" * 6 + bytes.fromhex(mac.replace(":", "")) * 16
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    for port in (9, 7):
        s.sendto(pkt, ("255.255.255.255", port))


async def connect(conf, timeout=4.0):
    from aiowebostv import WebOsClient
    client = WebOsClient(conf["host"], conf.get("client_key"), connect_timeout=timeout)
    try:
        await client.connect()
    except BaseException:
        await client.disconnect()
        raise
    return client


async def connect_waking(conf, wait=30.0):
    """Connect, waking the TV with Wake-on-LAN first if it doesn't answer."""
    try:
        return await connect(conf, 3)
    except Exception:
        pass
    if not conf.get("mac"):
        raise SystemExit("TV is off and its MAC address is unknown - turn it on by hand.")
    print("TV is off - waking it…", flush=True)
    end = time.time() + wait
    while time.time() < end:
        wake(conf["mac"])
        try:
            return await connect(conf, 3)
        except Exception:
            await asyncio.sleep(1.5)
    raise SystemExit("TV didn't wake up. Is 'Turn on via Wi-Fi' enabled on the TV?")


async def main(argv):
    cmd = argv[1] if len(argv) > 1 else "status"

    if cmd == "find":
        tvs = discover()
        if not tvs:
            print("No LG TV found. Is it on and on the same Wi-Fi?")
        for ip, name in tvs.items():
            print(f"{ip}\t{name}")
        return

    if cmd == "pair":
        if len(argv) > 2:
            ip = argv[2]
        else:
            tvs = discover()
            if len(tvs) != 1:
                sys.exit("Give the TV's IP: python3 tv/lgtv.py pair <ip>   (try 'find')")
            ip = next(iter(tvs))
        from aiowebostv import WebOsClient
        print(f"Connecting to {ip} - press **Allow** / **Yes** on the TV screen now…", flush=True)
        client = WebOsClient(ip, connect_timeout=60)
        await client.connect()
        conf = {"host": ip, "client_key": client.client_key, "mac": mac_of(ip)}
        await client.disconnect()
        save(conf)
        print(f"Paired with {ip} (MAC {conf['mac'] or 'unknown'}). Saved to {CONF}")
        if not conf["mac"]:
            print("Couldn't read the MAC address, so waking the TV from off won't work.\n"
                  "Add it to lgtv.json as \"mac\": \"aa:bb:cc:dd:ee:ff\" "
                  "(TV: Settings > Network > Wi-Fi > Advanced).")
        return

    conf = load()
    if cmd == "status":
        try:
            c = await connect(conf, 3)
            print(f"TV {conf['host']} is on")
            await c.disconnect()
        except Exception:
            print(f"TV {conf['host']} is off or unreachable")
    elif cmd == "on":
        c = await connect_waking(conf)
        print("TV is on")
        await c.disconnect()
    elif cmd == "off":
        try:
            c = await connect(conf, 3)
        except Exception:
            print("TV already off")
            return
        await c.power_off()
        print("TV turned off")
    elif cmd == "open":
        url = argv[2]
        c = await connect_waking(conf)
        try:
            await c.request("system.launcher/open", {"target": url})
        except Exception:
            await c.request("system.launcher/launch",
                            {"id": "com.webos.app.browser", "params": {"target": url}})
        print(f"Opened {url} on the TV")
        await c.disconnect()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    asyncio.run(main(sys.argv))
