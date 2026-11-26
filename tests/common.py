"""Shared helpers for the QHome tests (standard library only)."""
import copy
import json
import os
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "python"))

import qh_hw  # noqa: E402
from qh_engine import Engine  # noqa: E402


def demo_config(with_scripts=True):
    with open(os.path.join(HERE, "fixtures", "demo", "config.json")) as f:
        cfg = json.load(f)
    if with_scripts:
        with open(os.path.join(HERE, "fixtures", "demo_workspace.json")) as f:
            cfg["scripts"] = {"workspace": json.load(f)}
    cfg["mqtt"]["mode"] = "off"
    return cfg


class Rig:
    """An Engine with a simulated local board, stepped by a background thread."""

    def __init__(self, cfg, mqtt=None, link_port=None, probe=False, disc_every=0.3):
        """probe=True lets the engine ask unassigned serial ports who is there (it then also
        writes "H" to real serial devices of this computer; needs QHOME_REAL_LINKS)."""
        self.dir = tempfile.mkdtemp(prefix="qhome-test-")
        with open(os.path.join(self.dir, "config.json"), "w") as f:
            json.dump(cfg, f)
        os.environ["QHOME_LINK_PORT"] = str(link_port or 0)
        os.environ["QHOME_USB_PROBE"] = "1" if probe else "0"
        self.engine = e = Engine(self.dir)
        e._disc_every = disc_every
        self.local = qh_hw.SimHW(lambda pin, val: e.hw_event(pin, val))
        e.load_config(True)
        e.started -= 5          # start scripts right away
        e.start(self.local, mqtt)
        self.run = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self):
        while self.run:
            self.engine.step(0.02)

    def wait(self, cond, timeout=5.0):
        end = time.time() + timeout
        while time.time() < end:
            if cond():
                return True
            time.sleep(0.02)
        return False

    def state(self, cid):
        return self.engine.state.get(cid)

    def close(self):
        self.run = False
        self.engine._disc_run = False       # stops the usb-discover thread
        self.thread.join(1)
        for tr in self.engine.transports.values():
            tr.stop()
        server = self.engine.ports.server
        if server is not None:
            try:
                server.close()
            except OSError:
                pass
        os.environ.pop("QHOME_USB_PROBE", None)


def clone(x):
    return copy.deepcopy(x)
