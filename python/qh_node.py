"""Node mode: this UNO Q hands its pins to another QHome master over Wi-Fi.

The node keeps no logic of its own. It connects to the master's MQTT broker and speaks
QLink (the same line protocol the Arduino satellites use) on qlink/<node>/down|up|status,
so the master sees this board in its Boards tab like any other remote board.
"""
import queue
import re
import time

import qh_engine as E
import qh_tz
from qh_hw import QLinkDevice


class NodeAgent:
    def __init__(self, engine, local, mqtt):
        self.store = engine            # reused for config storage and the log
        self.cfg = engine.cfg
        self.log = engine.log
        self.local, self.mqtt = local, mqtt
        self.q = queue.Queue()
        self.want_restart = False
        self.started = time.time()
        self.dev = QLinkDevice(local, "unoq", self._send)
        self._probe_at = 0
        self._connect()

    def _base(self):
        return "qlink/%s/" % self.cfg["device"]["node"]

    def _connect(self):
        d = self.cfg["device"]
        self.mqtt.subscribe(self._base() + "down")
        self.mqtt.configure({"mode": "external", "host": d.get("master_host", ""),
                             "ext_port": d.get("master_port", 1883),
                             "username": d.get("master_user", ""),
                             "password": d.get("master_pass", "")},
                            "qhome-node-" + d["node"], self._base() + "status")

    def _send(self, line):
        self.mqtt.publish(self._base() + "up", line)

    # callbacks (other threads): only queue
    def hw_event(self, pin, val):
        self.q.put(("ev", pin, val))

    def hw_boot(self, ver):
        self.q.put(("boot",))

    def hw_link_rx(self, lid, line):
        pass

    def mqtt_message(self, topic, payload):
        if topic == self._base() + "down":
            for line in payload.split("\n"):
                self.q.put(("line", line))

    def mqtt_connected(self):
        self.q.put(("up",))

    def step(self, budget=0.1):
        end = time.time() + budget
        while True:
            try:
                item = self.q.get(timeout=min(max(0.0, end - time.time()), 0.02))
            except queue.Empty:
                item = None
            if item:
                try:
                    if item[0] == "line":
                        self.dev.feed(item[1])
                    elif item[0] == "ev":
                        self.dev.event(item[1], item[2])
                    elif item[0] == "boot":
                        self.log("The microcontroller restarted; asking the master to set it up again", "warn")
                        self.dev.rebooted()
                    elif item[0] == "up":
                        self.mqtt.publish(self._base() + "status", "online", retain=True)
                        self.dev.rebooted()
                except Exception as e:
                    self.log("Node problem: %r" % e, "err")
            if time.time() >= end:
                break
        now = time.time()
        self.local.poll(now)
        if not self.local.connected and now - self._probe_at > 5:
            self._probe_at = now
            if self.local.probe():
                self.log("Microcontroller connected (firmware v%s)" % self.local.version)

    # web API surface
    def submit_config(self, cfg):
        E.migrate(cfg)
        d = cfg.get("device") or {}
        if not re.match(r"^[a-z][a-z0-9_]{0,31}$", d.get("node", "")):
            return ["Node name must start with a letter and use only a-z, 0-9 and _ "
                    "(it is this board's id on the master)."]
        tz = d.get("tz", qh_tz.DEFAULT)
        if not qh_tz.valid(tz):
            return ["Time zone '%s' is not known. Pick one from the list in Settings." % (tz,)]
        self.store._atomic_write(self.store.cfg_path, cfg)
        self.store.cfg = self.cfg = cfg
        if d.get("role") == "node":
            self._connect()
        return []

    def submit_command(self, *a):
        pass

    def sim_input(self, board, pin, value):
        return bool(getattr(self.local, "simulated", False) and self.local.sim_input(pin, value))

    def snapshot(self, since_log=0):
        st = self.mqtt.status()
        with self.store.lock:
            logs = [x for x in self.store.logs if x["n"] > since_log]
        return {"rev": 0, "states": {}, "boards": {}, "logs": logs, "mqtt": st, "matrix": {},
                "vars": {}, "running": 0, "uptime": int(time.time() - self.started),
                "node": {"master": self.cfg["device"].get("master_host", ""), "online": st.get("ok"),
                         "mcu": bool(self.local.connected)}}
