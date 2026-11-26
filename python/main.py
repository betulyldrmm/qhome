"""QHome: no-code I/O, block scripts, multi-board links, MQTT and Home Assistant for the UNO Q.

On the UNO Q this file is started by Arduino App Lab, which also opens the web page. On a
PC, `python python/main.py` starts the same app with a simulated board and opens
http://localhost:7000 in the default browser.

Environment:
  QHOME_MODE          auto (default) | sim | pc   pc = no local board, this computer is only the hub
  QHOME_PORT          web port (7000; App Lab only opens 7000)
  QHOME_DATA          folder for config.json / state.json
  QHOME_LINK_PORT     TCP port the USB helper connects to (7001)
  QHOME_REAL_LINKS    set: a simulated master still uses real USB / Wi-Fi boards (tests)
  QHOME_OPEN_BROWSER  auto (default) | 1 | 0   open the web page when the app starts
  QHOME_USB_PROBE     1 (default) | 0   0 = do not ask unassigned USB ports who is there
  QHOME_SIM_DISCOVER  simulator: pretend new boards were found, e.g.
                      esp32@wifi:porch,nano@usb:/dev/ttyACM9
"""
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import qh_hw  # noqa: E402
import qh_sys  # noqa: E402
import qh_web  # noqa: E402
from qh_engine import VERSION, Engine  # noqa: E402
from qh_mqtt import MqttHub  # noqa: E402
from qh_node import NodeAgent  # noqa: E402

WEB_PORT = int(os.environ.get("QHOME_PORT", "7000"))
DATA_DIR = os.environ.get("QHOME_DATA", os.path.join(ROOT, "data"))
MODE = os.environ.get("QHOME_MODE", "auto")

engine = Engine(DATA_DIR)
engine.web_port = WEB_PORT
qh_sys.configure(DATA_DIR, WEB_PORT)
engine.log("QHome %s starting (data folder: %s)" % (VERSION, DATA_DIR))
app = engine  # replaced by a NodeAgent below when this board is a node

need_info = True       # the microcontroller (re)started: its Serial Monitor text must be sent again


def _hw_boot(ver):
    """Bridge callback (another thread). It must not call the Bridge: it only sets a flag."""
    global need_info
    need_info = True
    try:                      # a newly flashed sketch reports its version here; keep it current
        if ver is not None and local is not None:
            local.version = int(ver)
    except (NameError, TypeError, ValueError):
        pass
    app.hw_boot(ver)


# Hardware and MQTT callbacks arrive on other threads; `app` only queues them.
local = qh_hw.create_local(lambda pin, val: app.hw_event(pin, val), _hw_boot,
                           lambda lid, line: app.hw_link_rx(lid, line), engine.log, MODE)
cfg = engine.load_config(has_local=local is not None)
mqtt = MqttHub(engine.log, lambda t, p: app.mqtt_message(t, p), lambda: app.mqtt_connected())

role = cfg["device"].get("role", "master")
if role == "node" and local is None:
    engine.log("Node mode needs a board; starting as master instead", "warn")
    role = "master"
if role == "node":
    app = NodeAgent(engine, local, mqtt)
    if local.probe():
        engine.log("Microcontroller connected (firmware v%s)" % local.version)
    engine.log("Node mode: handing this board's pins to the master at %s"
               % (cfg["device"].get("master_host") or "(no address set)"))
else:
    engine.start(local, mqtt)

FRONTEND_DIST = os.path.join(ROOT, "frontend", "dist")
qh_web.start(app, WEB_PORT, os.path.join(ROOT, "assets"),
             {"role": role, "sim": bool(local is not None and local.simulated),
              "has_local": local is not None, "link_port": engine.ports.port, "web_port": WEB_PORT},
             frontend_dir=FRONTEND_DIST)
ON_BOARD = local is not None and not local.simulated
if ON_BOARD and WEB_PORT != 7000:
    engine.log("App Lab opens port 7000; QHOME_PORT=%d will not be opened automatically" % WEB_PORT, "warn")


def open_browser():
    """Open the web page on a PC. On the UNO Q App Lab does that (see app.yaml)."""
    want = os.environ.get("QHOME_OPEN_BROWSER", "auto").strip().lower() or "auto"
    if want in ("0", "no", "off", "false"):
        return False
    if want == "auto":
        if ON_BOARD or qh_sys.in_container() or os.environ.get("CI") or os.environ.get("SSH_CONNECTION"):
            return False
        if sys.platform.startswith("linux") and not (os.environ.get("DISPLAY")
                                                     or os.environ.get("WAYLAND_DISPLAY")):
            return False                    # no desktop: webbrowser could start a text browser here

    def go():
        try:
            import webbrowser
            webbrowser.open("http://localhost:%d/" % WEB_PORT, new=2)
        except Exception:
            pass
    try:
        t = threading.Timer(0.8, go)        # never hold up the start
        t.daemon = True
        t.start()
    except Exception:
        return False
    return True


open_browser()


def _mqtt_port():
    """Port of the built-in broker, when this run has one (master role, MQTT 'internal')."""
    m = app.cfg.get("mqtt") or {}
    if role != "master" or m.get("mode") != "internal":
        return None
    try:
        return int(m.get("port") or 1883)
    except (TypeError, ValueError):
        return None


_last = {"sample": 0.0, "check": -100.0, "banner": None, "info": None}


def announce(now):
    """Every 10 s: print the address banner when it changed, and keep the Serial Monitor
    text on the microcontroller current (it shows the same address there)."""
    global need_info
    since = now - _last["check"]
    urgent = need_info and local is not None       # retried every 2 s until the board took it
    if 0 <= since < (2 if urgent else 10):
        return
    _last["check"] = now
    name, port = str(app.cfg["device"].get("name") or "QHome"), _mqtt_port()
    ips = qh_sys.ip_list()
    lines = qh_sys.banner(VERSION, name, ips, WEB_PORT, port, qh_sys.in_container())
    if lines != _last["banner"]:
        _last["banner"] = lines
        for line in lines:
            engine.log(line)
    if local is not None:
        text = qh_sys.monitor_text(VERSION, name, ips, WEB_PORT, port)
        if need_info or text != _last["info"]:
            if local.info(text) is not None:     # None: no contact yet, or firmware older than v5
                _last["info"] = text
                need_info = False


def housekeeping():
    now = time.time()
    if now - _last["sample"] >= 2 or now < _last["sample"]:
        _last["sample"] = now
        qh_sys.sample()
    announce(now)


def loop():
    app.step(0.1)
    try:
        housekeeping()
    except Exception as e:                       # never let the extras stop the app
        engine.log("System info problem: %r" % e, "err")
    if getattr(app, "want_restart", False):   # the role changed: start over in the new role
        time.sleep(0.5)
        os.environ["QHOME_OPEN_BROWSER"] = "0"   # the page is open already
        os.execv(sys.executable, [sys.executable] + sys.argv)


try:
    if local is None or local.simulated:
        while True:
            loop()
    else:
        from arduino.app_utils import App
        App.run(user_loop=loop)
except KeyboardInterrupt:
    pass
finally:
    try:
        topic = ("qlink/%s/status" if role == "node" else "%s/status") % engine.node()
        mqtt.shutdown(topic)
        time.sleep(0.3)
    except Exception:
        pass
