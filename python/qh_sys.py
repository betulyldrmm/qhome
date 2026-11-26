"""System facts for the dashboard and the start banner. Standard library only; every
reader returns None instead of raising, so the same code runs on the UNO Q (inside the
App Lab container), a Linux PC, Windows and macOS."""
import glob
import os
import platform
import shutil
import socket
import threading
import time

_lock = threading.Lock()
_cpu_prev = None          # (busy, total) jiffies of the previous sample
_cpu_pct = None
_data_dir = "."
_web_port = 7000
_last = None
_names = None          # (time, addresses) of the last finished host name lookup
_names_busy = False    # a lookup is running in its helper thread


def _read(path, binary=False):
    try:
        with open(path, "rb" if binary else "r") as f:
            return f.read()
    except (OSError, ValueError):
        return None


def in_container():
    return os.path.exists("/.dockerenv") or bool(os.environ.get("HOST_IP")) \
        or os.environ.get("BOARD_NAME") is not None


def cpu_percent():
    """Whole-machine CPU use since the previous call (Linux /proc/stat), else None."""
    global _cpu_prev, _cpu_pct
    txt = _read("/proc/stat")
    if not txt:
        return None
    try:
        f = [int(x) for x in txt.split("\n", 1)[0].split()[1:9]]
    except ValueError:
        return None
    if len(f) < 5:
        return None
    idle, total = f[3] + f[4], sum(f)          # idle + iowait
    with _lock:
        prev, _cpu_prev = _cpu_prev, (total - idle, total)
        if prev and total > prev[1]:
            _cpu_pct = round(100.0 * ((total - idle) - prev[0]) / (total - prev[1]), 1)
        return _cpu_pct


def load_avg():
    try:
        return [round(x, 2) for x in os.getloadavg()]
    except (OSError, AttributeError):
        return None


def memory():
    txt = _read("/proc/meminfo")
    if not txt:
        return None
    kv = {}
    for line in txt.splitlines():
        k, _, v = line.partition(":")
        try:
            kv[k] = int(v.split()[0]) * 1024
        except (ValueError, IndexError):
            pass
    total = kv.get("MemTotal")
    if not total:
        return None
    avail = kv.get("MemAvailable", kv.get("MemFree", 0) + kv.get("Buffers", 0) + kv.get("Cached", 0))
    used = max(0, total - avail)
    return {"total": total, "used": used, "pct": round(100.0 * used / total, 1)}


def disk(path):
    try:
        d = shutil.disk_usage(path)
        return {"total": d.total, "used": d.used, "pct": round(100.0 * d.used / d.total, 1) if d.total else 0.0}
    except (OSError, ValueError, TypeError):
        return None


def cpu_temp():
    """Hottest CPU-ish thermal zone in deg C, else None."""
    best = None
    for z in glob.glob("/sys/class/thermal/thermal_zone*"):
        raw, typ = _read(z + "/temp"), (_read(z + "/type") or "").strip().lower()
        try:
            t = int(raw.strip()) / 1000.0
        except (AttributeError, ValueError):
            continue
        if not -20 < t < 130:                    # unplugged / bogus sensors
            continue
        cpuish = any(k in typ for k in ("cpu", "soc", "x86_pkg", "acpitz", "core"))
        cand = (1 if cpuish else 0, t)
        if best is None or cand > best:
            best = cand
    return round(best[1], 1) if best else None


def os_uptime():
    txt = _read("/proc/uptime")
    try:
        return int(float(txt.split()[0]))
    except (AttributeError, ValueError, IndexError):
        return None


def board_model():
    for p in ("/sys/firmware/devicetree/base/model", "/proc/device-tree/model"):
        raw = _read(p, binary=True)
        if raw:
            return raw.rstrip(b"\x00\n").decode("utf-8", "replace")
    return None


def _is_container_net(ip):
    try:
        return ip.startswith("172.") and 16 <= int(ip.split(".")[1]) <= 31
    except (ValueError, IndexError):
        return False


def _is_ipv4(ip):
    try:
        socket.inet_aton(ip)
        return ip.count(".") == 3
    except (OSError, TypeError):
        return False


def _route_ip():
    """This machine's default-route address. connect() on a UDP socket sends no packet."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return None


def _lookup_names():
    """Helper thread of _host_ips(): the one place that may wait for a name server."""
    global _names, _names_busy
    try:
        ips = list(socket.gethostbyname_ex(socket.gethostname())[2])
    except (OSError, UnicodeError):
        ips = []
    with _lock:
        _names, _names_busy = (time.time(), ips), False


def _host_ips():
    """Addresses the host name resolves to, from the last finished lookup ([] until one has
    finished). The lookup can wait for a name server for seconds, and this is called from the
    one thread that runs scripts and link traffic, so it runs in a helper thread: at most one
    at a time, at most every 30 s. Only the very first call waits for it, and only 0.3 s
    (a host name normally comes from the hosts file at once, so the first list is complete)."""
    global _names_busy
    now = time.time()
    with _lock:
        first = _names is None
        stale = first or now - _names[0] > 30 or now < _names[0]
        start = stale and not _names_busy
        if start:
            _names_busy = True
    if start:
        try:
            th = threading.Thread(target=_lookup_names, name="host-names", daemon=True)
            th.start()
            if first:
                th.join(0.3)
        except RuntimeError:                  # no new thread possible: try again next time
            with _lock:
                _names_busy = False
    done = _names
    return list(done[1]) if done else []


def _is_docker_bridge(host, own):
    """True when HOST_IP is not the board's LAN address but a Docker bridge of the board.

    arduino-app-cli takes "any running interface" when the board has no network at start, and
    that is a Docker bridge: docker0 (172.17.0.1) or the app's own network (172.18.0.1, ...).
    Seen from the container (own = its default-route address) that is either an address in the
    container's own /16, or, as the app is on its own compose network and not on docker0, the
    gateway address (it ends in .1) of another Docker network: both in 172.16.0.0/12, where
    Docker takes its networks from. A LAN address in 172.16.0.0/12 that does not end in .1
    (the board is not the router) is kept, and so is any address when the container itself is
    not in that range."""
    if not own or host == own:
        return False
    if host.split(".")[:2] == own.split(".")[:2]:
        return True
    return _is_container_net(host) and _is_container_net(own) and host.split(".")[3:] == ["1"]


def ip_list():
    """Addresses a browser on the LAN can use, best first. Sends nothing on the network itself
    (the host name lookup, outside a container only, is left to a helper thread)."""
    out = []

    def add(ip):
        if ip and _is_ipv4(ip) and ip not in out and not ip.startswith(("127.", "169.254.", "0.")):
            out.append(ip)
    cont = in_container()
    own = _route_ip()
    host = (os.environ.get("HOST_IP") or "").strip()        # set by arduino-app-cli: the board's address
    if host and _is_ipv4(host) and not (cont and _is_docker_bridge(host, own)):
        add(host)
    if own and not (cont and _is_container_net(own)):
        add(own)
    if not cont:
        for ip in _host_ips():
            add(ip)
    return out


def configure(data_dir, web_port):
    """Called once by main.py: where config.json lives (for the disk figure) and the web port."""
    global _data_dir, _web_port
    _data_dir, _web_port = data_dir or ".", int(web_port)


def _hostname():
    try:
        return socket.gethostname() or None
    except OSError:
        return None


def static_info():
    """Facts that do not change while the process runs (for /api/meta)."""
    cont = in_container()
    return {"hostname": None if cont else _hostname(),        # in a container it is the container id
            "board_model": board_model(), "board_name": os.environ.get("BOARD_NAME") or None,
            "os": "%s %s" % (platform.system(), platform.release()), "arch": platform.machine(),
            "python": platform.python_version(), "cpus": os.cpu_count(), "container": cont}


def sample():
    """Take a new sample, remember it and return it. Called by the main loop every 2 s."""
    global _last
    s = {"cpu": cpu_percent(), "load": load_avg(), "mem": memory(), "disk": disk(_data_dir),
         "temp": cpu_temp(), "os_uptime": os_uptime(), "ips": ip_list(), "port": _web_port}
    _last = s
    return s


def last():
    """The remembered sample (web handlers use this, so two browsers do not shorten each
    other's CPU window); takes one first when there is none yet."""
    return _last if _last is not None else sample()


_RULE = "=" * 60


def banner(version, name, ips, port, mqtt_port=None, container=False):
    """Lines of the start banner for the Python console and the Log tab."""
    lines = [_RULE, " QHome %s (%s) is running. Open it in a browser:" % (version, name)]
    for ip in list(ips)[:3]:
        lines.append("   http://%s:%d" % (ip, port))
    if not container:
        lines.append("   http://localhost:%d   (on this computer)" % port)
    elif not ips:
        lines.append("   http://<board-name>.local:%d" % port)
    if mqtt_port:
        lines.append(" MQTT broker: %s:%d" % (ips[0], mqtt_port) if ips
                     else " MQTT broker: port %d" % mqtt_port)
    lines.append(_RULE)
    return lines


def monitor_text(version, name, ips, port, mqtt_port=None):
    """Text the microcontroller prints on its Serial Monitor (q_info): plain ASCII, <= 190 chars."""
    name = str(name).encode("ascii", "replace").decode("ascii")
    name = "".join(ch if " " <= ch <= "~" else "?" for ch in name)
    if mqtt_port:
        third = "MQTT %s:%d" % (ips[0], mqtt_port) if ips else "MQTT port %d" % mqtt_port
    else:
        third = None
    second = "http://%s:%d" % (ips[0], port) if ips else "No network address yet. Web port %d" % port
    rest = "\n".join(x for x in (second, third) if x)
    head = "QHome %s (" % version
    room = 190 - len(rest) - 2 - len(head)    # a long device name is cut, never the address
    return (head + name[:max(0, room)] + ")\n" + rest)[:190]


if __name__ == "__main__":
    import json
    sample()
    time.sleep(0.3)
    print(json.dumps(dict(static_info(), **sample()), indent=1))
    print("\n".join(banner("x", "QHome", ip_list(), 7000, 1883, in_container())))
