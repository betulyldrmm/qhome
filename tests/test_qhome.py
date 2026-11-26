"""Engine, block scripts, validation and multi-board tests. Run:  python -m unittest discover tests"""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # also for: python -m unittest tests.test_qhome

from common import Rig, clone, demo_config  # noqa: E402

import json  # noqa: E402
import socket  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import types  # noqa: E402
from datetime import datetime  # noqa: E402

import qh_boards  # noqa: E402
import qh_engine  # noqa: E402
import qh_font as font  # noqa: E402
import qh_hw  # noqa: E402
import qh_script  # noqa: E402
import qh_sys  # noqa: E402
import qh_tz  # noqa: E402
from qh_mqtt import MqttHub  # noqa: E402
from qh_node import NodeAgent  # noqa: E402

N = lambda v: {"shadow": {"type": "math_number", "fields": {"NUM": v}}}  # noqa: E731


def ws(*stacks):
    return {"blocks": {"languageVersion": 0, "blocks": list(stacks)}, "variables": [{"name": "n", "id": "vn"}]}


def chain(*blocks):
    for a, b in zip(blocks, blocks[1:]):
        a["next"] = {"block": b}
    return blocks[0]


class Validation(unittest.TestCase):
    def test_demo_is_valid(self):
        self.assertEqual(qh_engine.validate(demo_config()), [])

    def test_pin_used_twice(self):
        cfg = demo_config()
        cfg["components"].append({"id": "x", "type": "switch_output", "name": "X", "board": "main", "pin": 2, "props": {}})
        self.assertTrue(any("used by both" in e for e in qh_engine.validate(cfg)))

    def test_pin_capability(self):
        cfg = demo_config()
        cfg["components"].append({"id": "x", "type": "dac_output", "name": "X", "board": "garage", "pin": 5, "props": {}})
        self.assertTrue(any("cannot do that" in e for e in qh_engine.validate(cfg)))

    def test_link_pins_are_reserved(self):
        cfg = demo_config()   # 'lab' hangs on the master's SDA/SCL, 'garage' is a classic UNO on USB
        for board, pin in (("main", 20), ("garage", 0), ("lab", 18)):
            c = clone(cfg)
            c["components"].append({"id": "x", "type": "switch_output", "name": "X", "board": board, "pin": pin, "props": {}})
            self.assertTrue(any("board link" in e for e in qh_engine.validate(c)), (board, pin))

    def test_board_rules(self):
        cfg = demo_config()
        cfg["boards"].append({"id": "b2", "name": "b2", "model": "nano", "link": {"type": "i2c", "bus": "wire", "address": 16}})
        cfg["boards"].append({"id": "w", "name": "w", "model": "r4w", "link": {"type": "wifi"}})
        cfg["boards"].append({"id": "u", "name": "u", "model": "uno", "link": {"type": "wifi"}})
        errs = " ".join(qh_engine.validate(cfg))
        self.assertIn("already used on the same bus", errs)
        self.assertIn("need MQTT", errs)
        self.assertIn("cannot be connected by 'wifi'", errs)

    def test_script_references(self):
        cfg = demo_config(False)
        cfg["scripts"]["workspace"] = ws(chain({"type": "ev_start"}, {"type": "do_turn", "fields": {"ENT": "nope", "TO": "on"}}),
                                         chain({"type": "ev_start"}, {"type": "do_set", "fields": {"ENT": "relay"}, "inputs": {"VALUE": N(1)}}))
        errs = qh_engine.validate(cfg)
        self.assertEqual(len(errs), 2, errs)

    def test_migrate_v1(self):
        old = {"version": 1, "device": {"name": "x", "node": "qhome"}, "mqtt": {"mode": "off"},
               "components": [{"id": "r", "type": "switch_output", "name": "R", "pin": 7, "props": {}}],
               "automations": [{"id": "a"}]}
        notes = qh_engine.migrate(old)
        self.assertEqual(old["components"][0]["board"], "main")
        self.assertNotIn("automations", old)
        self.assertEqual(len(notes), 2)
        self.assertEqual(qh_engine.validate(old), [])

    def test_every_model_pin_table(self):
        for name, m in qh_boards.MODELS.items():
            ids = [p["id"] for p in m["pins"]]
            self.assertEqual(len(ids), len(set(ids)), name)
            laid = [p for _, pins in m["layout"] for p in pins]
            self.assertEqual(sorted(map(str, laid)), sorted(map(str, ids)), name)


class Scripts(unittest.TestCase):
    def setUp(self):
        self.rig = Rig(demo_config())

    def tearDown(self):
        self.rig.close()

    def test_demo_scripts_across_boards(self):
        r = self.rig
        self.assertTrue(r.wait(lambda: all(r.engine.online.get(b) for b in ("main", "garage", "lab"))))
        self.assertTrue(r.wait(lambda: r.engine.scripts.variables().get("blink") == "3"), "start script")
        self.assertTrue(r.wait(lambda: r.state("away") is True), "every-second script")
        self.assertTrue(r.wait(lambda: r.state("button") is False))
        r.engine.sim_input("main", 2, 0)                       # press the door button
        self.assertTrue(r.wait(lambda: r.state("relay") is True), "relay on the USB board")
        garage = r.engine.transports["garage"].sim
        self.assertEqual(garage.out.get(7), 1, "the write reached the remote board")
        self.assertEqual(r.state("fan"), {"on": True, "level": 70.0})
        self.assertEqual(r.local.out.get(9), round(0.7 * 4095))
        self.assertTrue(str(r.state("matrix")).startswith("T "))
        self.assertEqual(r.state("status_led"), "off")
        self.assertTrue(r.wait(lambda: r.state("status_led") == "green", 3), "runs on after the wait")
        self.assertEqual(r.local.leds.get(3), qh_hw.RGB_BITS["green"])

    def test_retrigger_restarts_script(self):
        r = self.rig
        r.wait(lambda: r.state("button") is False)
        for _ in range(2):
            r.engine.sim_input("main", 2, 0)
            time.sleep(0.3)
            r.engine.sim_input("main", 2, 1)
            time.sleep(0.3)
        self.assertEqual(r.engine.scripts.variables().get("count"), "2")
        self.assertEqual(r.state("relay"), False, "toggled twice")

    def test_remote_adc_scaling(self):
        r = self.rig                                           # the Nano has a 10-bit ADC
        self.assertTrue(r.wait(lambda: r.state("ldr") is not None))
        self.assertTrue(0 <= r.state("ldr") <= 100)

    def test_threshold_edge_and_runaway_loop(self):
        r = self.rig
        cfg = demo_config(False)
        cfg["scripts"]["workspace"] = ws(
            chain({"type": "ev_above", "id": "h1", "fields": {"ENT": "temp", "OP": "above"}, "inputs": {"VALUE": N(-1)}},
                  {"type": "math_change", "fields": {"VAR": {"id": "vn"}}, "inputs": {"DELTA": N(1)}}),
            chain({"type": "ev_start", "id": "h2"},
                  {"type": "ctl_forever", "inputs": {"DO": {"block": {"type": "do_toggle", "fields": {"ENT": "away"}}}}}))
        self.assertEqual(r.engine.submit_config(cfg), [])
        time.sleep(1.5)                                        # temp is always above -1: armed only once
        self.assertEqual(r.engine.scripts.variables().get("n"), "0", "no edge, no trigger")
        self.assertEqual(r.engine.scripts.running(), 1, "the forever loop keeps running without blocking")
        self.assertTrue(r.wait(lambda: r.state("temp") is not None))

    def test_board_offline_event(self):
        r = self.rig
        cfg = demo_config(False)
        cfg["scripts"]["workspace"] = ws(chain({"type": "ev_board", "fields": {"BOARD": "garage", "TO": "offline"}},
                                               {"type": "do_turn", "fields": {"ENT": "away", "TO": "on"}}))
        self.assertEqual(r.engine.submit_config(cfg), [])
        self.assertTrue(r.wait(lambda: r.engine.online.get("garage")))
        r.engine.post(("link_state", "garage", False))
        self.assertTrue(r.wait(lambda: r.state("away") is True))
        self.assertFalse(r.engine.online["garage"])


class QLink(unittest.TestCase):
    def test_round_trip(self):
        events, boots, to_dev, to_hw = [], [], [], []
        sim = qh_hw.SimHW(lambda pin, val: dev.event(pin, val), adc_max=1023)
        dev = qh_hw.QLinkDevice(sim, "uno", to_hw.append)
        hw = qh_hw.QLinkHW("b", lambda p, v: events.append((p, v)), boots.append, lambda *a: None)
        hw.send = to_dev.append
        hw.set_link(True)

        def pump():
            while to_dev or to_hw:
                while to_dev:
                    dev.feed(to_dev.pop(0))
                while to_hw:
                    hw.feed(to_hw.pop(0))
        hw.poll(time.time())
        pump()
        self.assertTrue(hw.connected)
        self.assertEqual((hw.remote_model, boots), ("uno", [dev.boot_id]))
        hw.configure(4, qh_hw.M_DIN_PU, 1000, 30)
        hw.write_digital(7, 1)
        hw.write_analog(9, 2048)
        pump()
        self.assertEqual(events, [(4, 1)])
        self.assertEqual((sim.out[7], sim.out[9]), (1, 2048))
        dev.rebooted()                                         # board restarts: master handshakes again
        pump()
        self.assertFalse(hw.connected)
        hw.poll(time.time() + 2)
        pump()
        self.assertTrue(hw.connected)
        self.assertEqual(len(boots), 2)
        hw.feed("garbage \x00 line")                           # noise is ignored
        hw.feed("E x y")


def start_master(cfg, port, **rig_args):
    """A Rig whose engine runs the built-in MQTT broker on `port`."""
    cfg["mqtt"].update(mode="internal", port=port)
    holder, early = {}, []        # the broker calls back while the Rig is still being built

    def deliver(*item):
        if "rig" not in holder:
            return early.append(item)
        e = holder["rig"].engine
        e.mqtt_message(*item) if item else e.mqtt_connected()
    mq = MqttHub(lambda *a: None, deliver, deliver)
    rig = holder["rig"] = Rig(cfg, mqtt=mq, **rig_args)
    for item in early:
        deliver(*item)
    return rig


class FakeNode:
    """A UNO Q in node mode: its own store, a simulated microcontroller, MQTT to the master."""

    def __init__(self, name, port):
        store = qh_engine.Engine(tempfile.mkdtemp(prefix="qhome-node-"))
        store.load_config(True)
        store.cfg["device"].update(role="node", node=name, master_host="127.0.0.1", master_port=port)
        self.name = name
        self.hw = qh_hw.SimHW(lambda pin, val: self.agent.hw_event(pin, val))
        self.mq = MqttHub(lambda *a: None, lambda t, p: self.agent.mqtt_message(t, p),
                          lambda: self.agent.mqtt_connected())
        self.agent = NodeAgent(store, self.hw, self.mq)
        self.run = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while self.run:
            self.agent.step(0.02)

    def stop(self, offline=True):
        self.run = False
        time.sleep(0.1)
        if offline:
            self.mq.shutdown("qlink/%s/status" % self.name)


class Observer:
    """An MQTT client that remembers the last payload of every topic it sees."""

    def __init__(self, port, *filters):
        self.seen = {}
        self.mq = MqttHub(lambda *a: None, lambda t, p: self.seen.__setitem__(t, p), lambda: None)
        for f in filters:
            self.mq.subscribe(f)
        self.mq.configure({"mode": "external", "host": "127.0.0.1", "ext_port": port}, "observer", "observer/status")

    def close(self):
        self.mq.shutdown("observer/status")


class FakeUsbBoard:
    """Stands in for the USB helper with one satellite behind it (answers QLink H and P)."""

    def __init__(self, link_port, name="fake0", model="nano", boot="1a2b", silent=False):
        self.model, self.boot, self.silent = model, boot, silent
        self.rx = []
        self.sock = socket.create_connection(("127.0.0.1", link_port), timeout=5)
        self.sock.sendall(("@usb %s\n" % name).encode())
        self.run = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        buf = b""
        self.sock.settimeout(0.2)
        while self.run:
            try:
                data = self.sock.recv(256)
            except socket.timeout:
                continue
            except OSError:
                return
            if not data:
                return
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.decode().strip()
                self.rx.append(line)
                if self.silent:
                    continue
                try:
                    if line == "H":
                        self.sock.sendall(("booting...\nh 1 %s %s\n" % (self.model, self.boot)).encode())
                    elif line == "P":
                        self.sock.sendall(("p %s\n" % self.boot).encode())
                    elif line.startswith("C "):
                        self.sock.sendall(("c %s %s\n" % tuple(line.split()[1:3])).encode())
                except OSError:
                    return

    def close(self):
        self.run = False
        try:
            self.sock.close()
        except OSError:
            pass


class WifiNode(unittest.TestCase):
    """Two QHome instances: a master with the built-in broker and a UNO Q in node mode."""

    def test_node_hands_pins_to_master(self):
        port = 18931
        cfg = demo_config(False)
        cfg["boards"] = [cfg["boards"][0], {"id": "attic", "name": "Attic Q", "model": "unoq", "link": {"type": "wifi"}}]
        cfg["components"] = [
            {"id": "win", "type": "binary_input", "name": "Window", "board": "attic", "pin": 3, "props": {}},
            {"id": "lamp", "type": "switch_output", "name": "Lamp", "board": "attic", "pin": 8, "props": {}},
            {"id": "led", "type": "rgb_led", "name": "LED", "board": "attic", "pin": "LED4", "props": {}},
            {"id": "mx", "type": "led_matrix", "name": "MX", "board": "attic", "pin": "MATRIX", "props": {"startup_text": "HI"}}]
        os.environ["QHOME_REAL_LINKS"] = "1"
        rig = start_master(cfg, port)
        node = FakeNode("attic", port)
        node_hw = node.hw
        try:
            self.assertTrue(rig.wait(lambda: rig.engine.online.get("attic"), 8), "node comes online over MQTT")
            self.assertTrue(rig.wait(lambda: node_hw.modes.get(3) == qh_hw.M_DIN_PU), "pins configured on the node")
            self.assertTrue(rig.wait(lambda: rig.state("win") is False))
            node_hw.sim_input(3, 0)
            self.assertTrue(rig.wait(lambda: rig.state("win") is True), "input event travels to the master")
            rig.engine.submit_command("lamp", "on")
            rig.engine.submit_command("led", "set", "blue")
            self.assertTrue(rig.wait(lambda: node_hw.out.get(8) == 1 and node_hw.leds.get(4) == 4))
            self.assertTrue(rig.wait(lambda: "7" in node_hw.matrix_frame or "4" in node_hw.matrix_frame), "matrix frame")
            self.assertEqual(node_hw.matrix_frame, font.centered(font.text_columns("HI"), 4))
            rig.engine.submit_command("mx", "anim", "wave")    # frames are built on the master: every mode works
            frames = set()
            self.assertTrue(rig.wait(lambda: frames.add(node_hw.matrix_frame) or len(frames) >= 3, 4), "animation on the node")
            self.assertEqual(rig.state("mx"), "[anim:wave]")
            self.assertNotIn("mx", node.agent.snapshot(), "a node has no matrix modes of its own")
            self.assertEqual(rig.engine.discovered, {}, "a configured board is never 'found'")
            node.stop()                                        # stops answering, its status turns to "offline"
            self.assertTrue(rig.wait(lambda: not rig.engine.online.get("attic"), 5), "master notices")
        finally:
            node.run = False
            os.environ.pop("QHOME_REAL_LINKS", None)
            rig.close()


# ===================================================================== 2.1: boards
def sw(cid, board, pin, typ="switch_output", **props):
    return {"id": cid, "type": typ, "name": cid, "board": board, "pin": pin, "props": props}


class Boards(unittest.TestCase):
    NEW = ("nanor4", "esp32", "esp32c3", "esp8266")

    def test_model_list(self):
        self.assertEqual(list(qh_boards.MODELS), ["unoq", "uno", "nano", "mega", "r4m", "r4w",
                                                  "nanor4", "esp32", "esp32c3", "esp8266"])
        links = {k: m["links"] for k, m in qh_boards.MODELS.items()}
        self.assertEqual(links["nanor4"], ["usb", "uart", "i2c"])
        for k in ("esp32", "esp32c3", "esp8266"):
            self.assertEqual(links[k], ["usb", "uart", "wifi"], k)     # no I2C link on ESP boards
        self.assertEqual(qh_boards.MODELS["esp32"]["uart_pins"], [16, 17])
        self.assertEqual(qh_boards.MODELS["esp32"]["serial_pins"], [3, 1])
        for k, m in qh_boards.MODELS.items():
            if k != "esp32":
                self.assertEqual(m["uart_pins"], m["serial_pins"], k)
            self.assertIsInstance(m["usb_shares_uart"], bool, k)
        json.dumps(qh_boards.public_models())                            # what /api/meta sends
        self.assertNotIn("pin_by_id", qh_boards.public_models()["unoq"])

    def test_drawing_covers_every_pin_once(self):
        for name, m in qh_boards.MODELS.items():
            ids = [p["id"] for p in m["pins"]]
            drawn = qh_boards.board_pin_ids(m)
            self.assertEqual(len(drawn), len(set(drawn)), name)
            self.assertEqual(sorted(map(str, drawn)), sorted(map(str, ids)), name)
            b = m["board"]
            self.assertTrue(b["w"] > 0 and b["h"] > 0, name)
            for hd in b["headers"]:
                self.assertIn(hd["side"], ("top", "bottom", "left", "right", "inner"), name)
                n, cols = len(hd["pins"]), hd.get("cols") or len(hd["pins"])
                self.assertEqual(n % cols, 0, (name, hd["name"]))
                for i, e in enumerate(hd["pins"]):                    # every pin centre inside the outline
                    x, y = hd["x"] + i % cols, hd["y"] + i // cols
                    self.assertTrue(0 < x < b["w"] and 0 < y < b["h"], (name, hd["name"], i))
                    if isinstance(e, dict):
                        self.assertIsInstance(e["pad"], str)
                        if "same" in e:
                            self.assertIn(e["same"], m["pin_by_id"], (name, e))
                    else:
                        self.assertIn(e, m["pin_by_id"], (name, e))
            for pt in b["parts"]:
                self.assertIn(pt["type"], ("usb", "jack", "btn", "chip", "module", "conn", "led", "matrix", "rgb"))
                self.assertTrue(-3 <= pt["x"] and pt["x"] + pt["w"] <= b["w"] + 0.01, (name, pt))
                self.assertTrue(0 <= pt["y"] and pt["y"] + pt["h"] <= b["h"] + 0.01, (name, pt))
                if "pin" in pt:
                    self.assertIn(pt["pin"], m["pin_by_id"], (name, pt))
            for k in ("serial_pins", "uart_pins", "i2c_pins"):
                self.assertEqual(len(m[k]), 2, (name, k))
                for pin in m[k]:
                    self.assertIn(pin, m["pin_by_id"], (name, k))

    def test_real_positions(self):
        """USB on the left: the UNO footprint reads SCL SDA AREF GND D13..D8, gap, D7..D0."""
        def at(model, pin):
            for hd in qh_boards.MODELS[model]["board"]["headers"]:
                cols = hd.get("cols") or len(hd["pins"])
                for i, e in enumerate(hd["pins"]):
                    if e == pin:
                        return hd["side"], hd["x"] + i % cols, hd["y"] + i // cols
        for model in ("unoq", "uno", "r4m", "r4w"):
            self.assertEqual(at(model, 13)[0], "top")
            self.assertLess(at(model, 13)[1], at(model, 8)[1], model)
            self.assertLess(at(model, 8)[1] + 1, at(model, 7)[1], model)     # the gap between the two headers
            self.assertLess(at(model, 7)[1], at(model, 0)[1], model)
            self.assertEqual(at(model, 14)[0], "bottom")
            self.assertLess(at(model, 14)[1], at(model, 19)[1], model)
        top = qh_boards.MODELS["esp32"]["board"]["headers"][0]["pins"]
        bottom = qh_boards.MODELS["esp32"]["board"]["headers"][1]["pins"]
        self.assertEqual(top[:3], [{"pad": "VIN"}, {"pad": "GND"}, 13])
        self.assertEqual(bottom[-2:], [22, 23])
        parts = qh_boards.MODELS["unoq"]["board"]["parts"]
        self.assertEqual(sorted(p["pin"] for p in parts if "pin" in p), ["LED1", "LED2", "LED3", "LED4", "MATRIX"])

    def test_reserved_pins(self):
        def res(model, link, others=()):
            b = {"id": "b", "model": model, "link": {"type": link}}
            return set(qh_boards.reserved_pins(b, [b] + list(others)))
        self.assertEqual(res("esp32", "uart"), {16, 17})
        self.assertEqual(res("esp32", "usb"), {3, 1})
        self.assertEqual(res("esp32", "wifi"), set())
        self.assertEqual(res("esp32c3", "usb"), set())
        self.assertEqual(res("esp32c3", "uart"), {20, 21})
        self.assertEqual(res("esp8266", "usb"), {3, 1})
        self.assertEqual(res("esp8266", "uart"), {3, 1})
        self.assertEqual(res("nanor4", "usb"), set())
        self.assertEqual(res("nanor4", "uart"), {0, 1})
        self.assertEqual(res("nanor4", "i2c"), {18, 19})
        self.assertEqual(res("uno", "usb"), {0, 1})
        uart = {"id": "u", "model": "esp32", "link": {"type": "uart"}}
        i2c = {"id": "i", "model": "nano", "link": {"type": "i2c", "bus": "wire", "address": 16}}
        qwiic = {"id": "q", "model": "nano", "link": {"type": "i2c", "bus": "qwiic", "address": 17}}
        self.assertEqual(qh_boards.reserved_pins({"id": "main", "model": "unoq", "link": {"type": "local"}}, [uart, i2c]),
                         {0: "host_uart", 1: "host_uart", 20: "host_i2c", 21: "host_i2c"})
        self.assertEqual(res("unoq", "local", [qwiic]), set())

    def test_devices_on_new_models(self):
        cfg = demo_config(False)
        for n, model in enumerate(self.NEW):
            m, bid = qh_boards.MODELS[model], "b%d" % n
            board = {"id": bid, "name": bid, "model": model, "link": {"type": "usb", "port": "p%d" % n}}
            cfg["boards"].append(board)
            free = [p for p in m["pins"] if p["id"] not in qh_boards.reserved_pins(board, cfg["boards"])]
            out = [p for p in free if "dout" in p["caps"]][-1]
            adc = next(p for p in free if "adc" in p["caps"] and p is not out)
            cfg["components"] += [sw("o%d" % n, bid, out["id"]), sw("a%d" % n, bid, adc["id"], "analog_sensor")]
        self.assertEqual(qh_engine.validate(cfg), [])
        for board, pin, typ, want in (("b1", 6, "switch_output", "no pin selected"),        # ESP32 flash pin
                                      ("b1", 34, "switch_output", "cannot do that"),        # input only
                                      ("b3", 16, "pwm_output", "cannot do that"),           # NodeMCU D0
                                      ("b1", 3, "switch_output", "board link"),             # ESP32 USB = GPIO3/1
                                      ("main", 30, "switch_output", "no pin selected")):   # old JMISC pin
            c = clone(cfg)
            c["components"].append(sw("x", board, pin, typ))
            errs = qh_engine.validate(c)
            self.assertTrue(len(errs) == 1 and want in errs[0], (board, pin, errs))

    def test_new_boards_run_in_the_simulator(self):
        cfg = demo_config(False)
        cfg["boards"] = [cfg["boards"][0],
                         {"id": "porch", "name": "Porch", "model": "esp32", "link": {"type": "wifi"}},
                         {"id": "desk", "name": "Desk", "model": "esp8266", "link": {"type": "usb", "port": "auto"}}]
        cfg["components"] = [sw("light", "porch", 23), sw("lux", "porch", 34, "analog_sensor", calib="voltage"),
                             sw("a0", "desk", 17, "analog_sensor", calib="raw", decimals=0)]
        cfg["mqtt"]["mode"] = "external"          # Wi-Fi boards need MQTT in the setup; the rig has no hub
        self.assertEqual(qh_engine.validate(cfg), [])
        rig = Rig(cfg)
        try:
            self.assertTrue(rig.wait(lambda: rig.engine.online.get("porch") and rig.engine.online.get("desk")))
            self.assertEqual(rig.engine.hws["porch"].remote_model, "esp32")
            rig.engine.submit_command("light", "on")
            self.assertTrue(rig.wait(lambda: rig.engine.transports["porch"].sim.out.get(23) == 1))
            self.assertTrue(rig.wait(lambda: rig.state("lux") is not None and rig.state("a0") is not None))
            self.assertTrue(0 <= rig.state("lux") <= 3.3, "12-bit ADC, 3.3 V full scale")
            self.assertTrue(0 <= rig.state("a0") <= 1023, "10-bit ADC")
        finally:
            rig.close()


class Jmisc(unittest.TestCase):
    def test_migrate_drops_bottom_connector_devices(self):
        cfg = demo_config(False)
        cfg["boards"].append({"id": "big", "name": "Mega", "model": "mega", "link": {"type": "usb", "port": "x"}})
        cfg["components"] += [sw("old1", "main", 30), sw("old2", "main", 49, "binary_input"),
                              sw("keep24", "main", 24), sw("mega30", "big", 30)]
        n = len(cfg["components"])
        notes = qh_engine.migrate(cfg)
        self.assertEqual(notes, ["Removed 2 device(s) on the UNO Q bottom connector (JMISC), which is no longer "
                                 "supported: old1, old2."])
        ids = [c["id"] for c in cfg["components"]]
        self.assertEqual(len(ids), n - 2)
        self.assertTrue("mega30" in ids and "keep24" in ids and "matrix" in ids)
        self.assertEqual(qh_engine.validate(cfg), [])
        self.assertEqual(qh_engine.migrate(cfg), [], "nothing left to do the second time")

    def test_unoq_has_no_jmisc_pins(self):
        m = qh_boards.MODELS["unoq"]
        self.assertEqual(max(p["id"] for p in m["pins"] if isinstance(p["id"], int)), 24)
        self.assertEqual([g for g, _ in m["layout"]][-1], "jspi")
        self.assertNotIn("jmisc", json.dumps(qh_boards.public_models()).lower())

    def test_old_file_loads_with_a_note(self):
        cfg = demo_config(False)
        cfg["components"].append(sw("old1", "main", 30))
        d = tempfile.mkdtemp(prefix="qhome-test-")
        with open(os.path.join(d, "config.json"), "w") as f:
            json.dump(cfg, f)
        e = qh_engine.Engine(d)
        e.load_config(True)
        self.assertNotIn("old1", e.comps())
        self.assertTrue(any("Removed 1 device(s)" in x["msg"] and x["lvl"] == "warn" for x in e.logs))


# ===================================================================== 2.1: time zone
class TimeZone(unittest.TestCase):
    def test_migrate_offset(self):
        for old, new in ((3, "UTC+3"), (5.5, "UTC+5:30"), (-3.5, "UTC-3:30"), ("x", qh_tz.DEFAULT),
                         (0, "UTC"), (99, "UTC+14"), (5.75, "UTC+5:45")):
            cfg = demo_config(False)
            del cfg["device"]["tz"]
            cfg["device"]["tz_offset"] = old
            self.assertEqual(qh_engine.migrate(cfg), [], "no note for the time zone step")
            self.assertEqual(cfg["device"].get("tz"), new, old)
            self.assertNotIn("tz_offset", cfg["device"])
            self.assertEqual(qh_engine.validate(cfg), [])
        cfg = demo_config(False)
        cfg["device"].update(tz="UTC+1", tz_offset=9)
        qh_engine.migrate(cfg)
        self.assertEqual(cfg["device"], dict(cfg["device"], tz="UTC+1"))
        self.assertNotIn("tz_offset", cfg["device"])
        self.assertEqual(qh_engine.DEFAULT_CONFIG["device"]["tz"], "Europe/Istanbul")
        self.assertNotIn("tz_offset", qh_engine.DEFAULT_CONFIG["device"])

    def test_old_file_keeps_its_offset(self):
        cfg = demo_config(False)
        del cfg["device"]["tz"]
        cfg["device"]["tz_offset"] = 5.5
        d = tempfile.mkdtemp(prefix="qhome-test-")
        with open(os.path.join(d, "config.json"), "w") as f:
            json.dump(cfg, f)
        e = qh_engine.Engine(d)
        e.load_config(True)
        self.assertEqual(e.cfg["device"]["tz"], "UTC+5:30")       # not overwritten by the default
        lt, want = e.local_time(), time.gmtime(time.time() + 19800)
        self.assertEqual((lt.tm_hour, lt.tm_min, lt.tm_wday, lt.tm_yday),
                         (want.tm_hour, want.tm_min, want.tm_wday, want.tm_yday))

    def test_valid(self):
        for bad in ("Mars/Base", "UTC+15", "UTC-12:15", "", "../../etc/passwd", "utc", "UTC+3:10", None, 3, ["UTC"]):
            cfg = demo_config(False)
            cfg["device"]["tz"] = bad
            errs = qh_engine.validate(cfg)
            self.assertTrue(len(errs) == 1 and "Time zone" in errs[0], (bad, errs))
        for good in ("UTC", "UTC-9:30", "UTC+14", "UTC-12", "Europe/Istanbul"):
            cfg = demo_config(False)
            cfg["device"]["tz"] = good
            self.assertEqual(qh_engine.validate(cfg), [], good)
        cfg = demo_config(False)
        del cfg["device"]["tz"]
        self.assertEqual(qh_engine.validate(cfg), [], "missing = the default")

    def test_fixed_names(self):
        names = qh_tz.fixed_names()
        self.assertEqual(len(names), 56)
        self.assertEqual((names[0], names[-1]), ("UTC-12", "UTC+14"))
        self.assertTrue(all(qh_tz.valid(n) for n in names))
        self.assertEqual([qh_tz.fixed_minutes(n) for n in ("UTC", "UTC+5:30", "UTC-3", "UTC+15", "x")],
                         [0, 330, -180, None, None])
        self.assertEqual(qh_tz.fixed_name(-570), "UTC-9:30")

    @unittest.skipUnless(qh_tz.zones(), "this computer has no time zone database")
    def test_describe_with_daylight_saving(self):
        d = qh_tz.describe("Europe/Berlin", 1783000000)            # July 2026
        self.assertEqual((d["offset"], d["dst"], d["label"], d["exact"]), (120, True, "UTC+2", True))
        d = qh_tz.describe("Europe/Berlin", 1795300000)            # November 2026
        self.assertEqual((d["offset"], d["dst"], d["label"], d["abbr"]), (60, False, "UTC+1", "CET"))
        self.assertEqual(d["local"], "2026-11-21T23:26:40")
        self.assertEqual(sorted(d), ["abbr", "dst", "epoch", "exact", "label", "local", "offset", "tz"])
        self.assertIn("Europe/Istanbul", qh_tz.zones())
        self.assertFalse(any(z.startswith(("Etc/", "posix/", "right/")) or "/" not in z for z in qh_tz.zones()))
        self.assertEqual(qh_tz.zones(), sorted(qh_tz.zones()))

    def test_describe_fixed(self):
        d = qh_tz.describe("UTC+5:30", 1795300000)
        self.assertEqual((d["tz"], d["offset"], d["label"], d["dst"], d["exact"], d["epoch"]),
                         ("UTC+5:30", 330, "UTC+5:30", False, True, 1795300000))
        self.assertEqual(d["local"], "2026-11-22T03:56:40")
        json.dumps(qh_tz.describe(None))                           # a broken setting still answers

    def test_without_a_zone_database(self):
        keep = qh_tz.zoneinfo, qh_tz._zones
        qh_tz.zoneinfo, qh_tz._zones = None, []
        try:
            tz, exact = qh_tz.resolve("Europe/Istanbul")
            self.assertEqual((tz.utcoffset(None).total_seconds(), exact), (10800, False))
            self.assertTrue(qh_tz.valid("Foo/Bar"))
            self.assertFalse(qh_tz.valid("../../etc/passwd"))
            self.assertEqual(qh_tz.describe("Europe/Berlin", 1783000000)["offset"], 60)   # standard time only
            self.assertFalse(qh_tz.describe("Europe/Berlin")["exact"])
            self.assertEqual(qh_tz.zones(), [])
            cfg = demo_config(False)
            cfg["device"]["tz"] = "Europe/Berlin"
            rig = Rig(cfg)
            try:
                lt, want = rig.engine.local_time(), time.gmtime(time.time() + 3600)
                rig.engine.local_time()
                self.assertEqual((lt.tm_hour, lt.tm_min), (want.tm_hour, want.tm_min))
                warns = [x["msg"] for x in rig.engine.logs if "No time zone database" in x["msg"]]
                self.assertEqual(warns, ["No time zone database on this computer; using UTC+1 without "
                                         "daylight saving for 'Europe/Berlin'"], "logged once per zone")
            finally:
                rig.close()
        finally:
            qh_tz.zoneinfo, qh_tz._zones = keep

    def test_engine_local_time(self):
        cfg = demo_config(False)
        cfg["device"]["tz"] = "UTC+5:30"
        rig = Rig(cfg)
        try:
            for _ in range(3):                                     # retry across a minute boundary
                lt, want = rig.engine.local_time(), time.gmtime(time.time() + 19800)
                if (lt.tm_hour, lt.tm_min) == (want.tm_hour, want.tm_min):
                    break
            self.assertEqual((lt.tm_hour, lt.tm_min, lt.tm_wday), (want.tm_hour, want.tm_min, want.tm_wday))
            cfg2 = clone(cfg)
            cfg2["device"]["tz"] = "UTC-9:30"
            self.assertEqual(rig.engine.submit_config(cfg2), [])
            self.assertTrue(rig.wait(lambda: rig.engine.cfg["device"]["tz"] == "UTC-9:30"))
            lt, want = rig.engine.local_time(), time.gmtime(time.time() - 34200)
            self.assertEqual(lt.tm_hour, want.tm_hour)
            cfg2["device"]["tz"] = "Mars/Base"
            self.assertTrue(rig.engine.submit_config(cfg2))
        finally:
            rig.close()

    def test_at_time_fires_once_per_day(self):
        """The night the clocks go back has 02:30 twice; the script must run once."""
        now = [datetime(2026, 10, 25, 2, 30, 5)]
        eng = types.SimpleNamespace(local_time=lambda: now[0].timetuple(), log=lambda *a: None)
        rt = qh_script.Runtime(eng)
        rt.load(ws(chain({"type": "ev_time", "id": "t1", "fields": {"AT": "2:30", "DAYS": "all"}},
                         {"type": "do_log", "inputs": {"TEXT": {"shadow": {"type": "text", "fields": {"TEXT": "x"}}}}})))
        rt._timers(0)
        self.assertEqual(len(rt.threads), 1)
        rt.threads = []
        now[0] = datetime(2026, 10, 25, 2, 31, 0)
        rt._timers(0)
        now[0] = datetime(2026, 10, 25, 2, 30, 0)                  # the same minute again
        rt._timers(0)
        self.assertEqual(len(rt.threads), 0, "second 02:30 of the same day")
        now[0] = datetime(2026, 10, 26, 2, 30, 0)
        rt._timers(0)
        self.assertEqual(len(rt.threads), 1, "next day")

    def test_node_checks_the_zone(self):
        store = qh_engine.Engine(tempfile.mkdtemp(prefix="qhome-node-"))
        store.load_config(True)
        mq = types.SimpleNamespace(subscribe=lambda *a: None, configure=lambda *a: None, publish=lambda *a, **k: None,
                                   status=lambda: {"ok": False})
        agent = NodeAgent(store, qh_hw.SimHW(lambda *a: None), mq)
        cfg = clone(store.cfg)
        cfg["device"].update(role="node", node="attic", tz="Mars/Base")
        errs = agent.submit_config(cfg)
        self.assertTrue(len(errs) == 1 and "Time zone" in errs[0], errs)
        cfg["device"]["tz"] = "UTC+2"
        self.assertEqual(agent.submit_config(cfg), [])
        del cfg["device"]["tz"]
        cfg["device"]["tz_offset"] = 1
        self.assertEqual(agent.submit_config(cfg), [])
        self.assertEqual(agent.cfg["device"]["tz"], "UTC+1")


# ===================================================================== 2.1: system info, banner, q_info
class SystemInfo(unittest.TestCase):
    @staticmethod
    def is_num(x):
        return isinstance(x, (int, float)) and not isinstance(x, bool)

    def test_static_info(self):
        s = qh_sys.static_info()
        self.assertEqual(sorted(s), ["arch", "board_model", "board_name", "container", "cpus", "hostname", "os", "python"])
        for k in ("hostname", "board_model", "board_name"):
            self.assertTrue(s[k] is None or isinstance(s[k], str), k)
        for k in ("os", "arch", "python"):
            self.assertIsInstance(s[k], str, k)
        self.assertTrue(s["cpus"] is None or isinstance(s["cpus"], int))
        self.assertIsInstance(s["container"], bool)
        json.dumps(s)

    def check_sample(self, s):
        self.assertEqual(sorted(s), ["cpu", "disk", "ips", "load", "mem", "os_uptime", "port", "temp"])
        self.assertTrue(s["cpu"] is None or (self.is_num(s["cpu"]) and 0 <= s["cpu"] <= 100))
        self.assertTrue(s["load"] is None or (len(s["load"]) == 3 and all(self.is_num(x) for x in s["load"])))
        for k in ("mem", "disk"):
            if s[k] is not None:
                self.assertEqual(sorted(s[k]), ["pct", "total", "used"], k)
                self.assertTrue(isinstance(s[k]["total"], int) and isinstance(s[k]["used"], int), k)
                self.assertTrue(self.is_num(s[k]["pct"]) and 0 <= s[k]["pct"] <= 100, k)
        self.assertTrue(s["temp"] is None or self.is_num(s["temp"]))
        self.assertTrue(s["os_uptime"] is None or isinstance(s["os_uptime"], int))
        self.assertTrue(isinstance(s["ips"], list) and all(isinstance(x, str) for x in s["ips"]))
        self.assertFalse(any(x.startswith("127.") for x in s["ips"]))
        self.assertIsInstance(s["port"], int)
        json.dumps(s)

    def test_sample(self):
        keep = qh_sys._data_dir, qh_sys._web_port, qh_sys._last
        try:
            qh_sys.configure(tempfile.gettempdir(), 7123)
            qh_sys._last = None
            first = qh_sys.last()                                  # takes a sample when there is none
            self.check_sample(first)
            self.assertIs(qh_sys.last(), first, "last() never samples again")
            time.sleep(0.05)
            s = qh_sys.sample()
            self.check_sample(s)
            self.assertIs(qh_sys.last(), s)
            self.assertEqual(s["port"], 7123)
            self.assertIsNotNone(s["disk"], "the data folder is on some disk")
            qh_sys.configure(os.path.join(tempfile.gettempdir(), "no", "such", "folder"), 7123)
            self.assertIsNone(qh_sys.sample()["disk"])             # a reader that fails gives None
        finally:
            qh_sys._data_dir, qh_sys._web_port, qh_sys._last = keep

    def test_ip_list_prefers_host_ip(self):
        keep = {k: os.environ.get(k) for k in ("HOST_IP", "BOARD_NAME")}
        route = qh_sys._route_ip
        try:
            os.environ["HOST_IP"], os.environ["BOARD_NAME"] = "192.168.1.50", "unoq"
            qh_sys._route_ip = lambda: "172.18.0.3"                # the container's own address
            self.assertTrue(qh_sys.in_container())
            self.assertEqual(qh_sys.ip_list(), ["192.168.1.50"])
            self.assertIsNone(qh_sys.static_info()["hostname"], "it would be the container id")
            self.assertEqual(qh_sys.static_info()["board_name"], "unoq")
            os.environ["HOST_IP"] = "172.18.0.1"                   # no network at start: the Docker bridge
            self.assertEqual(qh_sys.ip_list(), [])
            os.environ["HOST_IP"] = "127.0.0.1"
            self.assertEqual(qh_sys.ip_list(), [])
            os.environ["HOST_IP"] = "not an address"
            self.assertEqual(qh_sys.ip_list(), [])
        finally:
            qh_sys._route_ip = route
            for k, v in keep.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_banner(self):
        rule = "=" * 60
        self.assertEqual(qh_sys.banner("2.1.0", "Home", ["192.168.1.50", "10.0.0.7"], 7000, 1883), [
            rule, " QHome 2.1.0 (Home) is running. Open it in a browser:",
            "   http://192.168.1.50:7000", "   http://10.0.0.7:7000",
            "   http://localhost:7000   (on this computer)", " MQTT broker: 192.168.1.50:1883", rule])
        self.assertEqual(qh_sys.banner("2.1.0", "Home", [], 7000, 1883, container=True), [
            rule, " QHome 2.1.0 (Home) is running. Open it in a browser:",
            "   http://<board-name>.local:7000", " MQTT broker: port 1883", rule])
        self.assertEqual(qh_sys.banner("2.1.0", "Home", ["192.168.1.50"], 8000, None, container=True), [
            rule, " QHome 2.1.0 (Home) is running. Open it in a browser:", "   http://192.168.1.50:8000", rule])
        self.assertEqual(qh_sys.banner("2.1.0", "Home", [], 7000), [
            rule, " QHome 2.1.0 (Home) is running. Open it in a browser:",
            "   http://localhost:7000   (on this computer)", rule])
        many = qh_sys.banner("2.1.0", "Home", ["10.0.0.%d" % i for i in range(1, 6)], 7000)
        self.assertEqual(len([x for x in many if "10.0.0." in x]), 3, "at most three addresses")

    def test_monitor_text(self):
        self.assertEqual(qh_sys.monitor_text("2.1.0", "Home", ["192.168.1.50", "10.0.0.7"], 7000, 1883),
                         "QHome 2.1.0 (Home)\nhttp://192.168.1.50:7000\nMQTT 192.168.1.50:1883")
        self.assertEqual(qh_sys.monitor_text("2.1.0", "Home", [], 7000),
                         "QHome 2.1.0 (Home)\nNo network address yet. Web port 7000")
        self.assertEqual(qh_sys.monitor_text("2.1.0", "Home", ["192.168.1.50"], 7000),
                         "QHome 2.1.0 (Home)\nhttp://192.168.1.50:7000")
        t = qh_sys.monitor_text("2.1.0", "Çatı katı", ["192.168.1.50"], 7000)
        self.assertEqual(t.split("\n")[0], "QHome 2.1.0 (?at? kat?)")
        for name in ("x" * 500, "ğ" * 300, "a\nb" * 90):
            t = qh_sys.monitor_text("2.1.0", name, ["192.168.100.150"], 7000, 1883)
            self.assertLessEqual(len(t), 190)
            self.assertTrue(t.isascii() and len(t.split("\n")) == 3, t)
            self.assertTrue(t.endswith("\nhttp://192.168.100.150:7000\nMQTT 192.168.100.150:1883"), "the address is never cut")


class SerialMonitorInfo(unittest.TestCase):
    def test_sim(self):
        hw = qh_hw.SimHW(lambda *a: None)
        self.assertEqual((hw.version, hw.info_text), (5, ""))
        self.assertEqual(hw.info("x"), 1)
        self.assertEqual(hw.info_text, "x")
        text = qh_sys.monitor_text(qh_engine.VERSION, "QHome Demo", ["192.168.1.50"], 7000, 1883)
        self.assertEqual(hw.info(text), len(text))
        self.assertEqual(hw.info_text.split("\n"), ["QHome 2.1.0 (QHome Demo)", "http://192.168.1.50:7000",
                                                    "MQTT 192.168.1.50:1883"])

    def test_local_needs_firmware_5(self):
        calls = []

        class Bridge:
            fail = False

            def call(self, name, *args, **kw):
                calls.append((name, args, kw))
                if self.fail:
                    raise TimeoutError("no such method")
                return len(args[0])
        hw = object.__new__(qh_hw.LocalHW)
        hw._b, hw.connected, hw.version, hw.log = Bridge(), True, 4, lambda *a: None
        self.assertIsNone(hw.info("hello"))
        hw.version = None
        self.assertIsNone(hw.info("hello"))
        self.assertEqual(calls, [], "older firmware has no q_info: it is not called")
        hw.version = 5
        self.assertEqual(hw.info("hello"), 5)
        self.assertEqual(calls, [("q_info", ("hello",), {"timeout": 3})])
        self.assertEqual(hw.info("y" * 500), 190, "cut to what the sketch stores")
        hw.connected = False
        self.assertIsNone(hw.info("hello"))
        self.assertEqual(len(calls), 2)
        hw.connected, hw._b.fail = True, True
        self.assertIsNone(hw.info("hello"))
        self.assertTrue(hw.connected, "an optional call never marks the microcontroller as lost")


# ===================================================================== 2.1: LED matrix modes
class MatrixFont(unittest.TestCase):
    def px(self, frame, x, y):
        return frame[y * font.W + x]

    def test_icons(self):
        self.assertEqual(list(font.ICONS), ["smile", "sad", "heart", "check", "cross", "wifi", "house",
                                            "sun", "moon", "bell", "warn", "lock", "up", "down"])
        self.assertEqual(font.MODES, ("text", "clock", "value", "bar", "anim", "icon", "status", "ip", "off"))
        self.assertEqual(font.ANIMS, ("heartbeat", "wave", "rain", "sparkle", "spinner", "bounce"))
        for name, rows in font.ICONS.items():
            self.assertEqual([len(r) for r in rows], [13] * 8, name)
            f = font.icon(name, 4)
            self.assertEqual(len(f), 104)
            self.assertEqual(set(f), {"0", "4"}, name)
            self.assertEqual(f, font.scale(font.icon(name), 4))
        self.assertIsNone(font.icon("nope"))
        self.assertEqual(font.scale("7310" * 26, 1), "1110" * 26, "lit stays lit")
        self.assertEqual(font.from_rows(["#"] * 8, 9)[:13], "7" + "0" * 12)

    def test_animations(self):
        for a in font.ANIMS:
            frames = set()
            for i in range(51):
                f = font.anim(a, i / 10.0, 5)
                self.assertEqual(len(f), 104, a)
                self.assertTrue(set(f) <= set("01234567"), a)
                self.assertEqual(f, font.anim(a, i / 10.0, 5), a)
                frames.add(f)
            self.assertGreaterEqual(len(frames), 2, a)
        self.assertEqual(font.anim("nope", 1, 5), font.blank())
        self.assertEqual([font.anim_step(1.0, s) for s in (1, 5, 9, 0, 50)], [2, 6, 10, 2, 10])

    def test_clock(self):
        f = font.clock(9, 41, 0, 7)
        self.assertTrue(all(self.px(f, x, y) == "0" for x in (0, 1, 2) for y in range(1, 6)), "no leading zero")
        a, b = font.clock(23, 59, 0, 7), font.clock(23, 59, 1, 7)
        diff = [(i % 13, i // 13) for i in range(104) if a[i] != b[i]]
        self.assertEqual(diff, [(5, 7), (6, 7)], "only the dots blink")
        self.assertEqual(font.clock(13, 5, 0, 7, h12=True), font.clock(1, 5, 0, 7))
        self.assertEqual(font.clock(0, 5, 0, 7, h12=True), font.clock(12, 5, 0, 7))
        hours = {self.px(a, x, y) for x in range(0, 6) for y in range(1, 6)} - {"0"}
        minutes = {self.px(a, x, y) for x in range(6, 13) for y in range(1, 6)} - {"0"}
        self.assertEqual(hours, {"7"})
        self.assertTrue(len(minutes) == 1 and int(minutes.pop()) < 7, "minutes are dimmer")
        self.assertEqual(font.clock(23, 59, 1, 7, blink=False), a)

    def test_bar(self):
        rows = lambda f: [f[y * 13:(y + 1) * 13] for y in (2, 3, 4, 5)]  # noqa: E731
        self.assertEqual(rows(font.bar(0, 7)), ["0" * 13] * 4)
        self.assertEqual(rows(font.bar(1, 7)), ["7" * 13] * 4)
        half = rows(font.bar(0.5, 7))[0]
        self.assertTrue(half.startswith("7" * 6) and half[6] not in "07" and half[7:] == "0" * 6, half)
        self.assertEqual(font.bar(2, 7), font.bar(1, 7))
        self.assertEqual(font.bar(-1, 7), font.bar(0, 7))

    def test_graph(self):
        f = font.graph([0, 10], 0, 10, 7)
        self.assertEqual([self.px(f, 11, y) != "0" for y in range(8)], [False] * 7 + [True])
        self.assertTrue(all(self.px(f, 12, y) != "0" for y in range(8)))
        self.assertEqual(self.px(f, 12, 0), "7")
        self.assertTrue(all(self.px(f, x, y) == "0" for x in range(11) for y in range(8)))
        self.assertEqual(font.graph([], 0, 1, 7), font.blank())
        self.assertEqual(len(font.graph([5, 5], 0, 0, 7)), 104)       # flat line with automatic scale
        self.assertEqual(len(font.graph(range(40), 0, 0, 7)), 104)    # only the newest 13 are drawn

    def test_scrolling_by_the_clock(self):
        self.assertEqual(font.scroll_offset(20, 0, 100), -13)
        self.assertEqual([font.scroll_offset(20, i / 10.0 + 0.001, 100) for i in range(4)], [-13, -12, -11, -10])
        self.assertEqual(font.scroll_offset(20, 3.4001, 100), -13, "wraps after 34 steps")
        self.assertEqual(font.scroll_offset(20, 1.0001, 50), 7, "40-99 ms really is faster")
        hi = font.text_columns("HI")
        self.assertEqual(font.text_frame(hi, 99, 100, 4), font.centered(hi, 4))
        long = font.text_columns("HELLO WORLD")
        self.assertEqual(font.text_frame(long, 0, 100, 4), font.blank(), "enters from the right edge")
        self.assertEqual(font.text_frame(long, 1.3001, 100, 4), font.render(long, 0, 4))

    def test_fit_value(self):
        self.assertEqual(font.fit_value("23", "C"), "23C")
        self.assertEqual(font.fit_value("5", "V"), "5 V")
        self.assertEqual(font.fit_value("23.5", "°C"), "23.5")
        self.assertEqual(font.fit_value("ON", ""), "ON")

    def test_status(self):
        f = font.status([True, True, False], 3, True, 0.0, 7)
        self.assertEqual(len(f), 104)
        self.assertEqual((self.px(f, 0, 7), self.px(f, 1, 7), self.px(f, 12, 0)), ("7", "7", "7"))
        self.assertNotEqual(self.px(f, 2, 7), "7", "the offline board is dim or dark")
        self.assertNotEqual(font.status([False], 1, None, 0.0, 7), font.status([False], 1, None, 0.5, 7), "blinks")
        self.assertEqual(self.px(font.status([True], 1, None, 0.0, 7), 12, 0), "0", "MQTT off: no dot")


def mx_config(**props):
    """Master only: the matrix, the room sensor (temp), a fan and a virtual switch."""
    cfg = demo_config(False)
    cfg["boards"] = cfg["boards"][:1]
    cfg["components"] = [c for c in cfg["components"] if c.get("board") in ("main", None)]
    next(c for c in cfg["components"] if c["id"] == "matrix")["props"] = dict(props)
    return cfg


class MatrixModes(unittest.TestCase):
    def rig(self, **props):
        self.r = Rig(mx_config(**props))
        self.addCleanup(self.r.close)
        self.assertTrue(self.r.wait(lambda: self.r.engine.online.get("main") and self.r.engine.mx["matrix"]["last"]))
        return self.r

    def cmd(self, action, value=None, cid="matrix"):
        self.r.engine.submit_command(cid, action, value)

    def frame(self):
        return self.r.local.matrix_frame

    def expect(self, state, frame=None, msg=None):
        r = self.r
        ok = r.wait(lambda: r.state("matrix") == state and (frame is None or self.frame() == frame), 3)
        self.assertTrue(ok, msg or "wanted %r, state is %r" % (state, r.state("matrix")))

    def mx(self):
        return self.r.engine.snapshot()["mx"]["matrix"]

    def test_props_table(self):
        props = {p["key"]: p for p in qh_engine.TYPES["led_matrix"]["props"]}
        self.assertEqual(list(props), ["brightness", "mode", "startup_text", "source", "bar_style", "bar_min",
                                       "bar_max", "graph_secs", "anim", "speed", "icon", "clock_12h", "scroll_ms"])
        self.assertEqual(props["mode"]["options"], list(font.MODES))
        self.assertEqual(props["source"], {"key": "source", "type": "device", "default": "",
                                           "kinds": list(qh_script.MX_SOURCES), "show": "mode=value|bar"})
        self.assertEqual(props["scroll_ms"]["show"], "mode=text|value|status|ip")
        self.assertEqual(props["icon"]["options"], list(font.ICONS))
        self.assertEqual(qh_engine.props_of({"type": "led_matrix", "props": {"startup_text": "A"}})["mode"], "text")
        json.dumps(qh_engine.TYPES)

    def test_default_setup_is_text(self):
        r = self.rig()                                          # a setup from 2.0: no mode
        self.expect("QHOME", font.centered(font.text_columns("QHOME"), 4))
        self.assertEqual(self.mx(), {"mode": "text", "auto": True, "left": 0})
        self.assertEqual(sorted(r.engine.snapshot()["mx"]), ["matrix"])

    def test_clock(self):
        r = self.rig(mode="clock", brightness=7)
        self.expect("[clock]")
        for _ in range(20):                                     # retry across a second boundary
            lt = r.engine.local_time()
            want = font.clock(lt.tm_hour, lt.tm_min, lt.tm_sec, 7)
            if r.wait(lambda: self.frame() == want, 0.3):
                break
        else:
            self.fail("the clock frame never matched")
        self.assertEqual(self.mx(), {"mode": "clock", "auto": True, "left": 0})
        cfg = clone(r.engine.cfg)
        cfg["components"][1]["props"]["clock_12h"] = True
        self.assertEqual(cfg["components"][1]["id"], "matrix")
        self.assertEqual(r.engine.submit_config(cfg), [])
        self.assertEqual(r.state("matrix"), "[clock]")

    def test_icon_and_back(self):
        self.rig()
        self.cmd("icon", "heart")
        self.expect("[icon:heart]", font.icon("heart", 4))
        self.assertEqual(self.mx(), {"mode": "icon", "auto": False, "left": 0})
        self.cmd("auto")
        self.expect("QHOME")
        self.assertTrue(self.mx()["auto"])
        self.cmd("icon")                                        # no name: the icon of the setup
        self.expect("[icon:smile]", font.icon("smile", 4))
        self.cmd("home")
        self.expect("QHOME")

    def test_legacy_commands(self):
        self.rig()
        self.cmd("icon", "7" * 104)
        self.expect("[icon]", "4" * 104)
        self.cmd("text", "HI")
        self.expect("HI", font.centered(font.text_columns("HI"), 4))
        self.cmd("set", "T {temp}")
        self.assertTrue(self.r.wait(lambda: str(self.r.state("matrix")).startswith("T ") and "--" not in self.r.state("matrix")))
        self.cmd("clear")
        self.expect("", font.blank())
        self.assertEqual(self.mx(), {"mode": "off", "auto": False, "left": 0})
        self.cmd("text", "A")
        self.cmd("off")
        self.expect("", font.blank())

    def test_every_action(self):
        r = self.rig(anim="rain", icon="sun", source="temp")
        for action, value, state, mode in (
                ("anim", "spinner", "[anim:spinner]", "anim"), ("anim", "nope", "[anim:rain]", "anim"),
                ("anim", None, "[anim:rain]", "anim"), ("bar", "temp", "[bar:temp]", "bar"),
                ("bar", "", "[bar:temp]", "bar"), ("clock", None, "[clock]", "clock"),
                ("mode", "icon:heart", "[icon:heart]", "icon"), ("mode", "anim:wave", "[anim:wave]", "anim"),
                ("mode", "bar:fan", "[bar:fan]", "bar"), ("mode", "text:HELLO", "HELLO", "text"),
                ("mode", "clock", "[clock]", "clock"), ("mode", "off", "", "off"), ("mode", "icon", "[icon:sun]", "icon"),
                ("mode", " Clock ", "[clock]", "clock"), ("mode", "text:A:B", "A:B", "text")):
            self.cmd(action, value)
            self.expect(state, msg="%s %r -> %r, not %r" % (action, value, r.state("matrix"), state))
            self.assertEqual(self.mx(), {"mode": mode, "auto": False, "left": 0}, (action, value))
        self.cmd("status")
        self.expect("1/1", font.status([True], 1, None, 0, 4))
        self.cmd("ip")
        addr = r.engine.web_address()
        self.expect(addr or "NO NETWORK")
        if addr:
            self.assertTrue(addr.endswith(":7000") and addr.count(".") == 3, addr)
        self.cmd("mode", "auto")
        self.expect("QHOME")
        before = len(r.engine.logs)
        for action, value in (("party", None), ("mode", "party:hard"), ("mode", "mode:clock"), ("toggle", None)):
            self.cmd(action, value)
        self.assertTrue(r.wait(lambda: len([x for x in list(r.engine.logs)[before:] if "does not know" in x["msg"]]) == 4))
        self.assertIn("Matrix 'matrix' does not know 'party'", [x["msg"] for x in r.engine.logs])
        self.assertEqual((r.state("matrix"), self.mx()["auto"]), ("QHOME", True), "unknown actions change nothing")

    def test_timed_override_returns_to_the_override(self):
        r = self.rig()
        self.cmd("icon", "heart")
        self.expect("[icon:heart]")
        self.cmd("text", {"text": "A", "secs": 1.0})
        self.expect("A", font.centered(font.text_columns("A"), 4))
        m = self.mx()
        self.assertEqual((m["mode"], m["auto"], m["left"]), ("text", False, 1))
        self.expect("[icon:heart]", font.icon("heart", 4), "back to the icon, not to the setup")
        self.assertEqual(self.mx(), {"mode": "icon", "auto": False, "left": 0})
        self.cmd("auto")
        self.expect("QHOME")
        self.cmd("mode", {"value": "icon:bell", "secs": 0.8})      # timed, over the setup
        self.expect("[icon:bell]")
        self.assertFalse(self.mx()["auto"])
        self.expect("QHOME")
        self.assertEqual(self.mx(), {"mode": "text", "auto": True, "left": 0})
        self.cmd("icon", {"value": "up", "secs": 30})
        self.expect("[icon:up]")
        self.assertEqual(self.mx()["left"], 30)
        self.cmd("auto")                                           # drops both overrides
        self.expect("QHOME")
        self.cmd("text", {"text": "KEEP", "secs": 0})              # no time: a plain override
        self.expect("KEEP")
        time.sleep(0.3)
        self.assertEqual((r.state("matrix"), self.mx()["left"]), ("KEEP", 0))

    def test_value_mode_follows_the_device(self):
        r = self.rig(mode="value", source="temp")
        self.assertTrue(r.wait(lambda: r.state("temp") is not None))
        seen = []                                                  # (time, the text of the reading then)

        def follows():
            """The matrix shows a reading the sensor had within the last 1.5 s. The text is drawn
            again once a second and the simulated sensor reports every 0.5 s, so "equal right
            now" can be true for only a few milliseconds per second and a poll may never see it."""
            now = time.time()
            seen.append((now, font.fit_value(r.engine.fmt_value("temp"), "C")))
            del seen[:-200]
            shown = r.state("matrix")
            return any(txt == shown for at, txt in seen if now - at < 1.5)
        self.assertTrue(r.wait(follows, 4), r.state("matrix"))
        self.assertNotEqual(r.state("matrix"), "--")
        first = r.state("matrix")
        self.assertTrue(r.wait(lambda: follows() and r.state("matrix") != first, 4), "the text is drawn again as the value moves")
        self.assertEqual(self.mx()["mode"], "value")
        self.cmd("value", "away")
        self.expect("OFF")
        r.engine.submit_command("away", "on")
        self.expect("ON")
        self.cmd("value")                                          # no device: the source of the setup
        self.assertTrue(r.wait(follows, 4), r.state("matrix"))
        self.cmd("value", "gone")
        self.expect("--")

    def test_bar_and_graph(self):
        r = self.rig(mode="bar", source="fan", bar_min=0, bar_max=100, brightness=7)
        self.expect("[bar:fan]", font.bar(0, 7))
        r.engine.submit_command("fan", "set", 50)
        self.expect("[bar:fan]", font.bar(0.5, 7))
        r.engine.submit_command("fan", "set", 100)
        self.expect("[bar:fan]", font.bar(1, 7))
        cfg = clone(r.engine.cfg)
        cfg["components"][1]["props"].update(bar_style="graph", bar_min=0, bar_max=0, graph_secs=1)
        self.assertEqual(r.engine.submit_config(cfg), [])
        self.expect("[bar:fan]", font.graph([100.0], 0, 0, 7))
        r.engine.submit_command("fan", "set", 20)
        want = [font.graph([100.0] * n + [20.0], 0, 0, 7) for n in (1, 2)]    # 2: a slow computer
        self.assertTrue(r.wait(lambda: self.frame() in want, 4), "one column per second")
        self.cmd("bar", "gone")
        self.expect("[bar:gone]", font.centered(font.text_columns("--"), 7))

    def test_source_is_validated(self):
        for props, ok in (({"mode": "value", "source": "temp"}, True), ({"mode": "value", "source": "away"}, True),
                          ({"mode": "bar", "source": "temp"}, True), ({"mode": "bar", "source": "fan"}, True),
                          ({"mode": "bar", "source": ""}, False), ({"mode": "bar"}, False),
                          ({"mode": "bar", "source": "away"}, False), ({"mode": "value", "source": "nope"}, False),
                          ({"mode": "value", "source": "matrix"}, False), ({"mode": "value", "source": "status_led"}, False),
                          ({"mode": "value", "source": ["temp"]}, False),
                          ({"mode": "text", "source": "nope"}, True), ({"mode": "clock"}, True)):
            errs = qh_engine.validate(mx_config(**props))
            self.assertEqual(errs, [] if ok else ["Matrix: pick the device whose value the matrix shows."], props)

    def test_save_clears_the_override_only_for_an_edited_matrix(self):
        r = self.rig()
        self.cmd("icon", "heart")
        self.cmd("text", {"text": "TMP", "secs": 60})
        self.expect("TMP")
        cfg = clone(r.engine.cfg)
        cfg["components"][0]["name"] = "Another name"              # unrelated change
        cfg["components"][1]["props"]["mode"] = "text"             # spelled out, but the same as before
        self.assertEqual(r.engine.submit_config(cfg), [])
        self.assertTrue(r.wait(lambda: r.engine.cfg["components"][0]["name"] == "Another name"))
        time.sleep(0.2)
        self.assertEqual(r.state("matrix"), "TMP", "the override survives")
        cfg = clone(cfg)
        cfg["components"][1]["props"]["startup_text"] = "NEW"
        self.assertEqual(r.engine.submit_config(cfg), [])
        self.expect("NEW", font.centered(font.text_columns("NEW"), 4))
        self.assertEqual(self.mx(), {"mode": "text", "auto": True, "left": 0})

    def test_overrides_are_not_kept_over_a_restart(self):
        r = self.rig()
        self.cmd("icon", "heart")
        self.expect("[icon:heart]")
        r.engine._state_dirty = time.time() - 3                    # write state.json now
        self.assertTrue(r.wait(lambda: os.path.exists(r.engine.state_path)))
        with open(r.engine.state_path) as f:
            self.assertEqual(sorted(k for k in json.load(f) if k.startswith("_")), [])
        e2 = qh_engine.Engine(r.dir)
        e2.load_config(True)
        e2._init_states()
        self.assertIsNone(e2.mx["matrix"]["over"])

    def test_scroll_keeps_its_place_when_only_the_value_changes(self):
        r = self.rig(startup_text="TEMPERATURE {temp}", scroll_ms=40)
        self.assertTrue(r.wait(lambda: r.state("temp") is not None))
        seen = set()
        r.wait(lambda: seen.add(self.frame()) or False, 2.5)       # the value changes twice a second
        self.assertGreater(len(seen), 15, "it scrolls on instead of starting over")

    def test_script_blocks(self):
        txt = lambda s: {"shadow": {"type": "text", "fields": {"TEXT": s}}}  # noqa: E731
        ent = {"ENT": "matrix"}
        cfg = mx_config()
        good = ws(chain({"type": "ev_state", "id": "h1", "fields": {"ENT": "away", "TO": "on"}},
                        {"type": "do_mx_icon", "fields": dict(ent, ICON="heart")},
                        {"type": "ctl_wait", "inputs": {"SECS": N(0.3)}},
                        {"type": "do_mx_anim", "fields": dict(ent, ANIM="rain")},
                        {"type": "ctl_wait", "inputs": {"SECS": N(0.3)}},
                        {"type": "do_mx_value", "fields": dict(ent, SRC="fan", AS="bar")},
                        {"type": "ctl_wait", "inputs": {"SECS": N(0.3)}},
                        {"type": "do_mx_value", "fields": dict(ent, SRC="away", AS="value")},
                        {"type": "ctl_wait", "inputs": {"SECS": N(0.3)}},
                        {"type": "do_mx_mode", "fields": dict(ent, MODE="clock")},
                        {"type": "ctl_wait", "inputs": {"SECS": N(0.3)}},
                        {"type": "do_show_for", "fields": ent, "inputs": {"TEXT": txt("BYE"), "SECS": N(0.8)}},
                        {"type": "ctl_wait", "inputs": {"SECS": N(0.3)}},
                        {"type": "do_show_for", "fields": ent, "inputs": {"TEXT": txt("NEVER"), "SECS": N(0)}},
                        {"type": "math_change", "fields": {"VAR": {"id": "vn"}}, "inputs": {"DELTA": N(1)}},
                        {"type": "do_mx_mode", "fields": dict(ent, MODE="auto")}))
        cfg["scripts"]["workspace"] = good
        self.assertEqual(qh_engine.validate(cfg), [])
        for field, value, want in (("ICON", "nope", "Script 1: unknown matrix icon."),
                                   ("ANIM", "nope", "Script 1: unknown matrix animation."),
                                   ("MODE", "text", "Script 1: unknown matrix mode."),
                                   ("SRC", "status_led", "Script 1: pick the device whose value the matrix shows."),
                                   ("SRC", "", "Script 1: pick the device whose value the matrix shows.")):
            bad = clone(cfg)
            b = bad["scripts"]["workspace"]["blocks"]["blocks"][0]
            while field not in b.get("fields", {}):
                b = b["next"]["block"]
            b["fields"][field] = value
            self.assertEqual(qh_engine.validate(bad), [want], (field, value))
        bad = clone(cfg)
        bad["scripts"]["workspace"]["blocks"]["blocks"][0]["next"]["block"]["fields"]["ENT"] = "fan"
        self.assertEqual(len(qh_engine.validate(bad)), 1, "the matrix dropdown only takes a matrix")
        self.assertEqual(qh_script.ENTITY_FIELDS["do_mx_value.SRC"], qh_script.MX_SOURCES)
        for t in ("do_show_for", "do_mx_icon", "do_mx_anim", "do_mx_value", "do_mx_mode"):
            self.assertEqual(qh_script.ENTITY_FIELDS[t], ("led_matrix",))
            self.assertIn(t, qh_script.STATEMENTS)
        self.assertEqual(qh_script.MX_BLOCK_MODES, ("auto", "clock", "status", "ip", "off"))

        self.r = r = Rig(cfg)
        self.addCleanup(r.close)
        seen = []
        watch = r.engine.set_state
        r.engine.set_state = lambda cid, v, force=False: (seen.append(v) if cid == "matrix" else None, watch(cid, v, force))[1]
        self.assertTrue(r.wait(lambda: r.state("matrix") == "QHOME"))
        r.engine.submit_command("away", "on")
        self.expect("BYE")
        t0 = time.time()
        self.assertEqual(r.engine.scripts.variables()["n"], "0", "the script waits while the text is shown")
        self.assertTrue(r.wait(lambda: r.engine.scripts.variables()["n"] == "1", 3))
        self.assertGreater(time.time() - t0, 0.3)
        self.expect("QHOME")
        self.assertEqual(seen[-8:], ["[icon:heart]", "[anim:rain]", "[bar:fan]", "ON", "[clock]", "BYE",
                                     "[clock]", "QHOME"])
        self.assertEqual(r.engine.scripts.running(), 0)

    def test_show_for_reverts_even_when_the_script_is_restarted(self):
        txt = {"shadow": {"type": "text", "fields": {"TEXT": "WAIT"}}}
        cfg = mx_config()
        cfg["scripts"]["workspace"] = ws(chain(
            {"type": "ev_state", "id": "h1", "fields": {"ENT": "away", "TO": "change"}},
            {"type": "do_show_for", "fields": {"ENT": "matrix"}, "inputs": {"TEXT": txt, "SECS": N(0.6)}},
            {"type": "math_change", "fields": {"VAR": {"id": "vn"}}, "inputs": {"DELTA": N(1)}}))
        self.r = r = Rig(cfg)
        self.addCleanup(r.close)
        r.engine.submit_command("away", "on")
        self.expect("WAIT")
        self.assertEqual(r.engine.submit_config(mx_config()), [])   # the scripts are removed mid-wait
        self.expect("QHOME", msg="the timed text ends by itself")
        self.assertEqual(r.engine.scripts.running(), 0)

    def test_mqtt_mode_topics(self):
        port = 18934
        self.r = r = start_master(mx_config(), port)
        self.addCleanup(r.close)
        obs = Observer(port, "qhome/#", "homeassistant/#")
        self.addCleanup(obs.close)
        self.assertTrue(r.wait(lambda: obs.seen.get("qhome/matrix/mode") == "text" and obs.seen.get("qhome/matrix/state") == "QHOME", 8),
                        "state and mode are published retained")
        topic = "homeassistant/select/qhome/matrix_mode/config"
        self.assertTrue(r.wait(lambda: topic in obs.seen))
        d = json.loads(obs.seen[topic])
        self.assertEqual((d["state_topic"], d["command_topic"], d["unique_id"], d["name"]),
                         ("qhome/matrix/mode", "qhome/matrix/mode/set", "qhome_matrix_mode", "Matrix mode"))
        self.assertEqual(d["options"], ["auto"] + list(font.MODES))
        self.assertEqual(json.loads(obs.seen["homeassistant/text/qhome/matrix/config"])["command_topic"], "qhome/matrix/set")
        obs.mq.publish("qhome/matrix/mode/set", "icon:heart")
        self.expect("[icon:heart]", font.icon("heart", 4))
        self.assertTrue(r.wait(lambda: obs.seen.get("qhome/matrix/mode") == "icon" and obs.seen["qhome/matrix/state"] == "[icon:heart]"))
        obs.mq.publish("qhome/matrix/set", "HELLO")                # the Home Assistant text entity, as before
        self.expect("HELLO")
        self.assertTrue(r.wait(lambda: obs.seen.get("qhome/matrix/mode") == "text"))
        obs.mq.publish("qhome/matrix/mode/set", "clock")
        self.assertTrue(r.wait(lambda: obs.seen.get("qhome/matrix/mode") == "clock" and obs.seen["qhome/matrix/state"] == "[clock]"))
        obs.mq.publish("qhome/fan/mode/set", "clock")              # not a matrix: ignored
        obs.mq.publish("qhome/matrix/mode/set", "auto")
        self.expect("QHOME")
        self.assertTrue(r.wait(lambda: obs.seen.get("qhome/matrix/mode") == "text"), "auto is never a state")
        self.assertEqual(r.state("fan"), {"on": False, "level": 100})
        cfg = mx_config()
        cfg["mqtt"].update(mode="internal", port=port)
        cfg["components"] = [c for c in cfg["components"] if c["id"] != "matrix"]
        self.assertEqual(r.engine.submit_config(cfg), [])
        self.assertTrue(r.wait(lambda: obs.seen.get(topic) == ""), "a removed matrix leaves Home Assistant")


# ===================================================================== 2.1: boards while the master runs
class LiveBoards(unittest.TestCase):
    """F1: saving a setup must not disturb the boards that did not change."""

    def setUp(self):
        self.rig = r = Rig(demo_config())
        self.addCleanup(r.close)
        self.assertTrue(r.wait(lambda: all(r.engine.online.get(b) for b in ("main", "garage", "lab"))))
        self.assertTrue(r.wait(lambda: r.state("temp") is not None and r.state("ldr") is not None))
        self.configs = []
        keep = r.local.configure
        r.local.configure = lambda *a: (self.configs.append(a), keep(*a))[1]
        self.drops = []
        down = r.engine._board_down
        r.engine._board_down = lambda bid: (self.drops.append(bid) if r.engine.online.get(bid) else None, down(bid))[1]

    def logs(self, text):
        return [x["msg"] for x in self.rig.engine.logs if text in x["msg"]]

    def apply(self, cfg):
        e = self.rig.engine
        n = len(self.logs("Setup applied"))
        self.assertEqual(e.submit_config(cfg), [])
        self.assertTrue(self.rig.wait(lambda: len(self.logs("Setup applied")) > n))

    def test_add_board_keeps_other_links(self):
        r, e = self.rig, self.rig.engine
        tr, hw, lab = e.transports["garage"], e.hws["garage"], e.transports["lab"]
        garage_sim = tr.sim
        e.submit_command("relay", "on")
        self.assertTrue(r.wait(lambda: garage_sim.out.get(7) == 1))
        cfg = clone(e.cfg)
        cfg["boards"].append({"id": "shed", "name": "Shed", "model": "esp32", "link": {"type": "usb", "port": "x"}})
        cfg["components"].append(sw("pump", "shed", 23))
        self.apply(cfg)
        self.assertTrue(r.wait(lambda: e.online.get("shed")), "the new board comes online")
        self.assertIs(e.transports["garage"], tr)
        self.assertIs(e.hws["garage"], hw)
        self.assertIs(e.transports["lab"], lab)
        self.assertEqual(self.drops, [], "no board went offline")
        self.assertEqual(self.logs("is offline"), [])
        self.assertEqual(len(self.logs("Board 'garage' is online")), 1)
        self.assertEqual(self.configs, [], "no pin of the local board was set up again")
        self.assertEqual(garage_sim.out.get(7), 1, "the relay stayed on")
        self.assertEqual(garage_sim.modes.get(7), qh_hw.M_DOUT)
        e.submit_command("pump", "on")
        self.assertTrue(r.wait(lambda: e.transports["shed"].sim.out.get(23) == 1), "devices on the new board work")
        cfg = clone(e.cfg)                                           # and removing it again
        cfg["boards"].pop()
        cfg["components"].pop()
        self.apply(cfg)
        self.assertNotIn("shed", e.transports)
        self.assertNotIn("shed", e.online)
        self.assertNotIn("shed", e.snapshot()["boards"])
        self.assertIs(e.transports["garage"], tr)
        self.assertEqual(self.drops, [])

    def test_rename_board_is_not_a_rebuild(self):
        r, e = self.rig, self.rig.engine
        before = dict(e.transports), dict(e.hws)
        cfg = clone(e.cfg)
        cfg["boards"][1]["name"] = "Car port"
        self.apply(cfg)
        self.assertEqual((dict(e.transports), dict(e.hws)), before)
        self.assertEqual(e.boards()["garage"]["name"], "Car port")
        self.assertEqual(self.drops, [])
        self.assertEqual(self.configs, [])
        self.assertEqual(len(self.logs("is online")), 2, "garage and lab, once each")
        self.assertTrue(all(e.online[b] for b in ("main", "garage", "lab")))

    def test_changed_link_rebuilds_only_that_board(self):
        r, e = self.rig, self.rig.engine
        garage, lab = e.transports["garage"], e.transports["lab"]
        cfg = clone(e.cfg)
        cfg["boards"][1]["link"] = {"type": "usb", "port": "other"}
        self.apply(cfg)
        self.assertIsNot(e.transports["garage"], garage)
        self.assertIs(e.transports["lab"], lab)
        self.assertTrue(r.wait(lambda: e.online.get("garage")))
        self.assertEqual(len(self.logs("Board 'garage' is online")), 2)
        self.assertEqual(len(self.logs("Board 'lab' is online")), 1)
        self.assertEqual(self.configs, [])
        self.assertTrue(r.wait(lambda: e.transports["garage"].sim.modes.get(7) == qh_hw.M_DOUT), "set up from scratch")
        cfg = clone(e.cfg)                                           # a changed model is a rebuild too
        cfg["boards"][2]["model"] = "uno"
        self.apply(cfg)
        self.assertIsNot(e.transports["lab"], lab)
        self.assertTrue(r.wait(lambda: e.hws["lab"].remote_model == "uno"))

class LinkSlots(unittest.TestCase):
    """Wired links live on the master's microcontroller, which has four slots (link ids)."""

    def test_link_ids_are_reused(self):
        def wired(bid, addr):
            return {"id": bid, "name": bid, "model": "nano", "link": {"type": "i2c", "bus": "qwiic", "address": addr}}
        cfg = demo_config(False)
        cfg["boards"] = [cfg["boards"][0], wired("a", 20), wired("b", 21), wired("c", 22)]
        cfg["components"] = []
        d = tempfile.mkdtemp(prefix="qhome-test-")
        with open(os.path.join(d, "config.json"), "w") as f:
            json.dump(cfg, f)
        os.environ.update(QHOME_LINK_PORT="0", QHOME_USB_PROBE="0")
        e = qh_engine.Engine(d)
        local = qh_hw.SimHW(lambda *a: None)
        local.simulated = False                      # a real master: wired boards get a McuTransport
        opened, closed = [], []
        local.link_open = lambda lid, *a: (opened.append(lid), 1)[1]
        local.link_close = lambda lid: (closed.append(lid), 1)[1]
        e.load_config(True)
        try:
            e.start(local, None)
            self.assertFalse(e._disc_run, "QHOME_USB_PROBE=0")
            self.assertEqual(e._lids, {"a": 0, "b": 1, "c": 2})
            e.step(0.05)
            self.assertEqual(sorted(opened), [0, 1, 2])
            a, c = e.transports["a"], e.transports["c"]
            new = clone(cfg)
            new["boards"] = [cfg["boards"][0], wired("a", 20), wired("c", 22), wired("d", 23), wired("e", 24)]
            e._apply_config(new)
            self.assertEqual(e._lids, {"a": 0, "c": 2, "d": 1, "e": 3}, "the smallest free slot is taken")
            self.assertEqual(e.lid_board, {0: "a", 2: "c", 1: "d", 3: "e"})
            self.assertEqual(closed, [1], "only the removed board's link was closed")
            self.assertTrue(e.transports["a"] is a and e.transports["c"] is c)
            self.assertEqual((a.lid, e.transports["d"].lid, e.transports["e"].lid), (0, 1, 3))
            e.post(("mcu_link", 1, "h 1 nano 1a2b"))
            e.step(0.05)
            self.assertTrue(e.online["d"] and not e.online["a"], "lines of a slot reach the board that owns it now")
        finally:
            e._disc_run = False
            for tr in e.transports.values():
                tr.stop()
            if e.ports.server:
                e.ports.server.close()
            os.environ.pop("QHOME_USB_PROBE", None)


class Discovery(unittest.TestCase):
    def setUp(self):
        os.environ["QHOME_REAL_LINKS"] = "1"
        self.addCleanup(lambda: os.environ.pop("QHOME_REAL_LINKS", None))

    def base(self):
        cfg = demo_config(False)
        cfg["boards"] = cfg["boards"][:1]
        cfg["components"] = [c for c in cfg["components"] if c.get("board") in ("main", None)]
        return cfg

    def test_discover_wifi_node(self):
        port = 18932
        rig = start_master(self.base(), port)
        self.addCleanup(rig.close)
        e = rig.engine
        self.assertEqual(e.snapshot()["discovered"], [])
        node = FakeNode("attic", port)
        self.addCleanup(node.stop, False)
        self.assertTrue(rig.wait(lambda: (e.discovered.get("wifi:attic") or {}).get("model") == "unoq", 8))
        rev = e.rev
        found = e.snapshot()["discovered"]
        self.assertEqual(len(found), 1)
        d = found[0]
        self.assertEqual(sorted(d), ["boot", "id", "key", "link", "model", "proto", "t"])
        self.assertEqual((d["key"], d["link"], d["id"], d["model"], d["proto"]), ("wifi:attic", "wifi", "attic", "unoq", 1))
        self.assertEqual(d["boot"], node.agent.dev.boot_id)
        self.assertLess(abs(d["t"] - time.time()), 30)
        json.dumps(found)
        self.assertFalse(e.online.get("attic"))
        cfg = clone(e.cfg)                                            # what "Add" in the banner leads to
        cfg["boards"].append({"id": "attic", "name": "attic", "model": d["model"], "link": {"type": "wifi"}})
        cfg["components"].append(sw("lamp", "attic", 8))
        self.assertEqual(e.submit_config(cfg), [])
        self.assertTrue(rig.wait(lambda: e.online.get("attic"), 8), "the found board is online after Save")
        self.assertEqual(e.discovered, {})
        self.assertGreater(e.rev, rev)
        e.submit_command("lamp", "on")
        self.assertTrue(rig.wait(lambda: node.hw.out.get(8) == 1), "its pins work at once")
        cfg = clone(e.cfg)                                            # removed from the setup: found again
        cfg["boards"].pop()
        cfg["components"].pop()
        self.assertEqual(e.submit_config(cfg), [])
        self.assertTrue(rig.wait(lambda: (e.discovered.get("wifi:attic") or {}).get("model") == "unoq", 8))

    def test_discover_wifi_offline_removes(self):
        port = 18933
        rig = start_master(self.base(), port)
        self.addCleanup(rig.close)
        e = rig.engine
        node = FakeNode("attic", port)
        self.assertTrue(rig.wait(lambda: (e.discovered.get("wifi:attic") or {}).get("model") == "unoq", 8))
        node.stop()                                                   # publishes "offline"
        self.assertTrue(rig.wait(lambda: "wifi:attic" not in e.discovered, 5))
        self.assertEqual(e.snapshot()["discovered"], [])

    def test_discover_wifi_silent_board_and_unknown_model(self):
        port = 18935
        rig = start_master(self.base(), port)
        self.addCleanup(rig.close)
        e = rig.engine
        obs = Observer(port, "qlink/#")
        self.addCleanup(obs.close)
        self.assertTrue(rig.wait(lambda: obs.mq.status()["ok"], 8))
        asked = []
        keep = e.publish
        e.publish = lambda topic, payload, retain=False: (asked.append((topic, payload)), keep(topic, payload, retain))[1]
        obs.mq.publish("qlink/porch/status", "online", retain=True)
        self.assertTrue(rig.wait(lambda: "wifi:porch" in e.discovered, 5))
        self.assertEqual(e.discovered["wifi:porch"]["model"], None, "there, but it has not said what it is")
        self.assertTrue(rig.wait(lambda: obs.seen.get("qlink/porch/down") == "H"), "the master asks with H")
        self.assertTrue(rig.wait(lambda: len(asked) == 3, 9), "asked three times, 3 s apart")
        time.sleep(0.5)
        self.assertEqual(asked, [("qlink/porch/down", "H")] * 3)
        obs.mq.publish("qlink/porch/up", "E 4 1\nh 1 esp99 beef")     # firmware newer than this QHome
        self.assertTrue(rig.wait(lambda: e.discovered["wifi:porch"]["model"] == "esp99"))
        self.assertEqual((e.discovered["wifi:porch"]["proto"], e.discovered["wifi:porch"]["boot"]), (1, "beef"))
        obs.mq.publish("qlink/porch/up", "B cafe")                    # it restarted (maybe reflashed): asked again
        self.assertTrue(rig.wait(lambda: len(asked) == 4))
        obs.mq.publish("qlink/porch/up", "h 1 esp32 cafe")
        self.assertTrue(rig.wait(lambda: e.discovered["wifi:porch"]["model"] == "esp32"))
        obs.mq.publish("qlink/porch/status", "", retain=True)         # retained status cleared
        self.assertTrue(rig.wait(lambda: e.discovered == {}))
        for n in range(20):                                           # a flood stays bounded
            obs.mq.publish("qlink/b%d/status" % n, "online")
        self.assertTrue(rig.wait(lambda: len(e.discovered) == qh_engine.DISCOVERED_MAX))
        time.sleep(0.3)
        self.assertEqual(len(e.snapshot()["discovered"]), 16)
        self.assertEqual(e.snapshot()["discovered"], sorted(e.snapshot()["discovered"], key=lambda d: d["key"]))

    def test_discover_ignores_bad_id(self):
        port = 18936
        rig = start_master(self.base(), port)
        self.addCleanup(rig.close)
        e = rig.engine
        for _ in range(2):
            e.mqtt.publish("qlink/Bad-Id/status", "online", retain=True)
            e.mqtt.publish("qlink/Bad-Id/up", "h 1 uno 1a2b")
        e.mqtt.publish("qlink/ok_id/status", "online")
        self.assertTrue(rig.wait(lambda: "wifi:ok_id" in e.discovered))
        self.assertEqual(list(e.discovered), ["wifi:ok_id"])
        logs = [x for x in e.logs if "Bad-Id" in x["msg"]]
        self.assertEqual([(x["msg"], x["lvl"]) for x in logs],
                         [("A board announces the id 'Bad-Id', which is not a valid board id", "warn")])

    def link_port(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        return port

    def test_discover_usb_helper_port(self):
        lp = self.link_port()
        rig = Rig(self.base(), link_port=lp, probe=True)
        self.addCleanup(rig.close)
        e = rig.engine
        dev = FakeUsbBoard(lp)
        self.addCleanup(dev.close)
        key = "usb:helper:fake0"
        self.assertTrue(rig.wait(lambda: key in e.discovered, 8))
        d = e.snapshot()["discovered"][0]
        self.assertEqual(sorted(d), ["boot", "key", "link", "model", "port", "proto", "t"])
        self.assertEqual((d["key"], d["link"], d["port"], d["model"], d["proto"], d["boot"]),
                         (key, "usb", "helper:fake0", "nano", 1, "1a2b"))
        ports = [p for p in e.ports.list() if p["name"] == "helper:fake0"]
        self.assertEqual(ports, [{"name": "helper:fake0", "busy": False}], "the connection was handed back, not closed")
        n = dev.rx.count("H")
        time.sleep(1.0)
        self.assertEqual(dev.rx.count("H"), n, "a port is asked once, not on every round")
        cfg = clone(e.cfg)
        cfg["boards"].append({"id": "shed", "name": "Arduino Nano", "model": "nano",
                              "link": {"type": "usb", "port": "helper:fake0"}})
        cfg["components"].append(sw("pump", "shed", 7))
        self.assertEqual(e.submit_config(cfg), [])
        self.assertTrue(rig.wait(lambda: e.online.get("shed"), 8), "the found board works after Save")
        self.assertEqual(e.discovered, {})
        self.assertTrue(rig.wait(lambda: "C 7 4 1000 0" in dev.rx))
        time.sleep(1.0)
        self.assertEqual(e.discovered, {}, "a port in use is not offered again")

    def test_discover_usb_silent_port(self):
        lp = self.link_port()
        rig = Rig(self.base(), link_port=lp, probe=True)
        self.addCleanup(rig.close)
        e = rig.engine
        dev = FakeUsbBoard(lp, name="mute0", silent=True)
        self.addCleanup(dev.close)
        t0 = time.time()
        self.assertTrue(rig.wait(lambda: "usb:helper:mute0" in e.discovered, 10))
        self.assertGreater(time.time() - t0, 3.0, "it waits for boards that restart when the port opens")
        d = e.discovered["usb:helper:mute0"]
        self.assertEqual((d["model"], d["proto"], d["boot"], d["port"]), (None, None, None, "helper:mute0"))
        self.assertGreaterEqual(dev.rx.count("H"), 4, "asked every half second")
        dev.close()                                                   # unplugged
        e.ports.helper.pop("helper:mute0").close()
        self.assertTrue(rig.wait(lambda: e.discovered == {}, 5))

    def test_discover_skips_claimed_port(self):
        lp = self.link_port()
        cfg = self.base()
        cfg["boards"].append({"id": "garage", "name": "Garage", "model": "uno", "link": {"type": "usb", "port": "auto"}})
        rig = Rig(cfg, link_port=lp, probe=True)
        self.addCleanup(rig.close)
        e = rig.engine
        time.sleep(0.8)                                               # the board waits for a port
        dev = FakeUsbBoard(lp, model="uno")
        self.addCleanup(dev.close)
        self.assertTrue(rig.wait(lambda: e.online.get("garage"), 10), "the waiting board takes the new port itself")
        time.sleep(1.0)
        self.assertEqual(e.discovered, {})
        self.assertEqual(e.transports["garage"].text, "helper:fake0")

    def test_probe_can_be_switched_off(self):
        lp = self.link_port()
        rig = Rig(self.base(), link_port=lp, probe=False)             # QHOME_USB_PROBE=0
        self.addCleanup(rig.close)
        dev = FakeUsbBoard(lp)
        self.addCleanup(dev.close)
        self.assertTrue(rig.wait(lambda: any(p["name"] == "helper:fake0" for p in rig.engine.ports.list())))
        time.sleep(1.0)
        self.assertEqual((dev.rx, rig.engine.discovered), ([], {}))
        self.assertFalse(rig.engine._disc_run)

    def test_probe_api(self):
        lp = self.link_port()
        rig = Rig(self.base(), link_port=lp, probe=False)
        self.addCleanup(rig.close)
        hub = rig.engine.ports
        dev = FakeUsbBoard(lp)
        self.addCleanup(dev.close)
        self.assertTrue(rig.wait(lambda: "helper:fake0" in hub.helper))
        self.assertEqual(hub.probe("helper:fake0"), (1, "nano", "1a2b"))
        self.assertEqual((hub.claimed, list(hub.helper)), (set(), ["helper:fake0"]))
        hub.claimed.add("helper:fake0")                               # a transport holds it
        self.assertIs(hub.probe("helper:fake0"), False)
        self.assertEqual(dev.rx.count("H"), 1, "a claimed port is never written to")
        hub.claimed.clear()
        self.assertIs(hub.probe("helper:gone"), False)
        self.assertIs(hub.probe(os.path.join(rig.dir, "no-such-tty")), False)
        dev.silent = True
        t0 = time.time()
        self.assertIsNone(hub.probe("helper:fake0", timeout=0.7))
        self.assertTrue(0.6 < time.time() - t0 < 2)
        self.assertEqual(hub.claimed, set())


class SimDiscovery(unittest.TestCase):
    def test_sim_discover_env(self):
        os.environ["QHOME_SIM_DISCOVER"] = "nano@usb:x, unoq@wifi:attic,bogus,esp32@wifi:Bad-Id,uno@usb:"
        cfg = demo_config(False)
        cfg["mqtt"]["mode"] = "external"                              # Wi-Fi boards need MQTT in the setup
        try:
            rig = Rig(cfg)
        finally:
            os.environ.pop("QHOME_SIM_DISCOVER")
        self.addCleanup(rig.close)
        e = rig.engine
        found = e.snapshot()["discovered"]
        self.assertEqual([(d["key"], d["model"], d["proto"], d["boot"]) for d in found],
                         [("usb:x", "nano", 1, "sim0"), ("wifi:attic", "unoq", 1, "sim0")])
        self.assertEqual((found[0]["port"], found[1]["id"]), ("x", "attic"))
        warns = [x["msg"] for x in e.logs if "QHOME_SIM_DISCOVER" in x["msg"]]
        self.assertEqual(len(warns), 1)
        self.assertTrue("'bogus'" in warns[0] and "'esp32@wifi:Bad-Id'" in warns[0] and "'uno@usb:'" in warns[0])
        cfg = clone(e.cfg)
        cfg["boards"].append({"id": "attic", "name": "attic", "model": "unoq", "link": {"type": "wifi"}})
        self.assertEqual(e.submit_config(cfg), [])
        self.assertTrue(rig.wait(lambda: e.online.get("attic")), "a simulated board like every other")
        self.assertEqual(type(e.transports["attic"]).__name__, "SimTransport")
        self.assertEqual([d["key"] for d in e.snapshot()["discovered"]], ["usb:x"])
        cfg = clone(e.cfg)
        cfg["boards"].append({"id": "desk", "name": "Arduino Nano", "model": "nano", "link": {"type": "usb", "port": "x"}})
        self.assertEqual(e.submit_config(cfg), [])
        self.assertTrue(rig.wait(lambda: e.online.get("desk") and e.discovered == {}))
        self.assertEqual([x["msg"] for x in e.logs if "is offline" in x["msg"]], [], "the other boards were not disturbed")

    def test_env_is_ignored_on_a_real_master(self):
        e = qh_engine.Engine(tempfile.mkdtemp(prefix="qhome-test-"))
        e.load_config(False)
        self.assertFalse(e.sim_discover({"link": "wifi", "id": "porch", "model": "esp32"}), "no local board")
        e.local = types.SimpleNamespace(simulated=False)
        self.assertFalse(e.sim_discover({"link": "wifi", "id": "porch", "model": "esp32"}))
        self.assertFalse(e.sim_discover(None))
        self.assertTrue(e.q.empty())

    def test_sim_discover_add_and_clear(self):
        rig = Rig(demo_config(False))
        self.addCleanup(rig.close)
        e = rig.engine
        rev = e.rev
        self.assertTrue(e.sim_discover({"link": "wifi", "id": "porch", "model": "esp32"}))
        self.assertTrue(e.sim_discover({"link": "usb", "port": "/dev/ttyACM9", "model": "nano"}))
        self.assertTrue(e.sim_discover({"link": "usb", "port": "/dev/ttyACM8", "model": None}))
        self.assertTrue(rig.wait(lambda: len(e.discovered) == 3))
        self.assertGreater(e.rev, rev)
        self.assertEqual([(d["key"], d["model"]) for d in e.snapshot()["discovered"]],
                         [("usb:/dev/ttyACM8", None), ("usb:/dev/ttyACM9", "nano"), ("wifi:porch", "esp32")])
        self.assertTrue(e.sim_discover({"link": "wifi", "id": "porch", "model": "esp32c3"}), "replaces the entry")
        self.assertTrue(rig.wait(lambda: e.discovered["wifi:porch"]["model"] == "esp32c3"))
        for bad in ({"link": "wifi", "id": "Bad-Id", "model": "esp32"}, {"link": "wifi", "model": "esp32"},
                    {"link": "usb", "port": "", "model": "nano"}, {"link": "i2c", "id": "x"}, {"link": "usb", "port": 5},
                    {"link": "wifi", "id": "ok", "model": "ESP 32"}, "porch", 5, [], {}):
            self.assertFalse(e.sim_discover(bad), bad)
        self.assertTrue(e.sim_discover({"link": "wifi", "id": "garage", "model": "uno"}))   # that id is configured
        self.assertTrue(e.sim_discover({"link": "usb", "port": "auto", "model": "uno"}))    # garage's port
        time.sleep(0.3)
        self.assertEqual(len(e.discovered), 3)
        rev = e.rev
        self.assertTrue(e.sim_discover(None))
        self.assertTrue(rig.wait(lambda: e.discovered == {}))
        self.assertGreater(e.rev, rev)
        self.assertEqual(e.snapshot()["discovered"], [])


class WebApi(unittest.TestCase):
    """The HTTP surface of 2.1, against a real server on a free port."""

    @classmethod
    def setUpClass(cls):
        import urllib.request
        import qh_web
        cls.urllib = urllib.request
        urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))   # never a proxy
        cfg = demo_config(False)
        cfg["mqtt"]["mode"] = "external"
        cls.rig = Rig(cfg)
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        cls.port = s.getsockname()[1]
        s.close()
        cls.keep = qh_sys._data_dir, qh_sys._web_port, qh_sys._last
        qh_sys.configure(cls.rig.dir, cls.port)
        qh_sys._last = None
        cls.rig.engine.web_port = cls.port
        assets = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
        cls.srv = qh_web.start(cls.rig.engine, cls.port, assets,
                               {"role": "master", "sim": True, "has_local": True, "link_port": 7001, "web_port": cls.port})

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.rig.close()
        qh_sys._data_dir, qh_sys._web_port, qh_sys._last = cls.keep

    def get(self, path):
        with self.urllib.urlopen("http://127.0.0.1:%d%s" % (self.port, path), timeout=5) as r:
            return json.loads(r.read())

    def post(self, path, body):
        req = self.urllib.Request("http://127.0.0.1:%d%s" % (self.port, path), json.dumps(body).encode(),
                                  {"Content-Type": "application/json"})
        try:
            with self.urllib.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except Exception as e:                                        # HTTPError carries the JSON body too
            return e.code, json.loads(e.read())

    def test_meta(self):
        m = self.get("/api/meta")
        for k in ("role", "sim", "has_local", "link_port", "types", "models", "colors", "version", "entity_fields",
                  "web_port", "sys", "matrix", "tz"):
            self.assertIn(k, m)
        self.assertEqual((m["version"], m["web_port"]), ("2.1.0", self.port))
        self.assertEqual(list(m["models"]), list(qh_boards.MODELS))
        self.assertEqual(m["models"]["esp32"]["uart_pins"], [16, 17])
        self.assertEqual(m["models"]["unoq"]["board"]["w"], 27)
        self.assertEqual(m["models"]["esp8266"]["pins"][0], {"id": 16, "label": "D0", "caps": ["din", "dout"],
                                                             "notes": ["no_pullup"], "alt": "GPIO16"})
        self.assertEqual(m["matrix"]["modes"], list(font.MODES))
        self.assertEqual(m["matrix"]["anims"], list(font.ANIMS))
        self.assertEqual(list(m["matrix"]["icons"]), list(font.ICONS))
        self.assertTrue(all(len(f) == 104 and set(f) <= {"0", "7"} for f in m["matrix"]["icons"].values()))
        self.assertEqual(sorted(m["tz"]), ["db", "default", "fixed", "zones"])
        self.assertEqual((m["tz"]["default"], len(m["tz"]["fixed"]), m["tz"]["db"]),
                         ("Europe/Istanbul", 56, bool(m["tz"]["zones"])))
        self.assertEqual(m["sys"], qh_sys.static_info())
        self.assertEqual(m["entity_fields"]["do_mx_value.SRC"], list(qh_script.MX_SOURCES))
        self.assertEqual([p["key"] for p in m["types"]["led_matrix"]["props"]][:3], ["brightness", "mode", "startup_text"])

    def test_state(self):
        s = self.get("/api/state?log=0")
        for k in ("rev", "states", "boards", "logs", "mqtt", "matrix", "vars", "running", "uptime",
                  "mx", "discovered", "sys", "time"):
            self.assertIn(k, s)
        self.assertEqual(s["mx"], {"matrix": {"mode": "text", "auto": True, "left": 0}})
        self.assertEqual(sorted(s["sys"]), ["cpu", "disk", "ips", "load", "mem", "os_uptime", "port", "temp"])
        self.assertEqual(s["sys"]["port"], self.port)
        self.assertEqual(sorted(s["time"]), ["abbr", "dst", "epoch", "exact", "label", "local", "offset", "tz"])
        self.assertEqual(s["time"]["tz"], "Europe/Istanbul")
        self.assertLess(abs(s["time"]["epoch"] - time.time()), 5)
        if qh_tz.zones():
            self.assertEqual((s["time"]["offset"], s["time"]["label"], s["time"]["exact"]), (180, "UTC+3", True))

    def test_time_zone_is_saved_and_checked(self):
        cfg = self.get("/api/config")
        self.assertEqual(cfg["device"]["tz"], "Europe/Istanbul")
        bad = clone(cfg)
        bad["device"]["tz"] = "Mars/Base"
        code, r = self.post("/api/config", bad)
        self.assertEqual((code, r["ok"], r["errors"]),
                         (422, False, ["Time zone 'Mars/Base' is not known. Pick one from the list in Settings."]))
        new = clone(cfg)
        new["device"]["tz"] = "UTC-9:30"
        self.assertEqual(self.post("/api/config", new)[1], {"ok": True, "errors": [], "restart": False})
        self.assertTrue(self.rig.wait(lambda: self.get("/api/state")["time"]["tz"] == "UTC-9:30"))
        t = self.get("/api/state")["time"]
        self.assertEqual((t["offset"], t["label"], t["dst"]), (-570, "UTC-9:30", False))
        old = clone(cfg)                                              # a setup file from 2.0
        del old["device"]["tz"]
        old["device"]["tz_offset"] = 3
        self.assertEqual(self.post("/api/config", old)[0], 200)
        self.assertTrue(self.rig.wait(lambda: self.get("/api/config")["device"].get("tz") == "UTC+3"))
        self.assertNotIn("tz_offset", self.get("/api/config")["device"])
        self.assertEqual(self.post("/api/config", cfg)[0], 200)

    def test_jmisc_pin_is_rejected_or_dropped(self):
        cfg = self.get("/api/config")
        new = clone(cfg)                                              # a 2.1 setup: a removed pin is an error
        new["components"].append(sw("y", "main", 30))
        code, r = self.post("/api/config", new)
        self.assertEqual((code, r["errors"]), (422, ["y: no pin selected."]))
        old = clone(cfg)                                              # a setup file written by 2.0: migrated
        del old["device"]["tz"]
        old["device"]["tz_offset"] = 3
        old["components"].append(sw("y", "main", 30))
        self.assertEqual(self.post("/api/config", old)[0], 200)
        note = "Removed 1 device(s) on the UNO Q bottom connector (JMISC), which is no longer supported: y."
        self.assertTrue(self.rig.wait(lambda: any(x["msg"] == note for x in self.get("/api/state")["logs"])))
        self.assertNotIn("y", [c["id"] for c in self.get("/api/config")["components"]])
        self.assertEqual(self.post("/api/config", cfg)[0], 200)

    def test_matrix_commands(self):
        self.assertEqual(self.post("/api/cmd", {"id": "matrix", "action": "mode", "value": "icon:heart"}), (200, {"ok": True}))
        self.assertTrue(self.rig.wait(lambda: self.get("/api/state")["states"]["matrix"]["v"] == "[icon:heart]"))
        s = self.get("/api/state")
        self.assertEqual((s["mx"]["matrix"], s["matrix"]["matrix"]),
                         ({"mode": "icon", "auto": False, "left": 0}, font.icon("heart", 4)))
        self.post("/api/cmd", {"id": "matrix", "action": "text", "value": {"text": "HI", "secs": 0.5}})
        self.assertTrue(self.rig.wait(lambda: self.get("/api/state")["states"]["matrix"]["v"] == "HI"))
        self.assertTrue(self.rig.wait(lambda: self.get("/api/state")["states"]["matrix"]["v"] == "[icon:heart]"))
        self.post("/api/cmd", {"id": "matrix", "action": "auto"})
        self.assertTrue(self.rig.wait(lambda: self.get("/api/state")["mx"]["matrix"]["auto"]))

    def test_sim_discover(self):
        self.assertEqual(self.post("/api/sim", {"discover": {"link": "wifi", "id": "porch", "model": "esp32"}}), (200, {"ok": True}))
        self.assertEqual(self.post("/api/sim", {"discover": {"link": "usb", "port": "/dev/ttyACM9", "model": "nano"}}), (200, {"ok": True}))
        self.assertTrue(self.rig.wait(lambda: len(self.get("/api/state")["discovered"]) == 2))
        d = self.get("/api/state")["discovered"]
        self.assertEqual([(x["key"], x["link"], x["model"], x["proto"], x["boot"]) for x in d],
                         [("usb:/dev/ttyACM9", "usb", "nano", 1, "sim0"), ("wifi:porch", "wifi", "esp32", 1, "sim0")])
        self.assertEqual(self.post("/api/sim", {"discover": {"link": "smoke"}}), (200, {"ok": False}))
        cfg = self.get("/api/config")
        cfg["boards"].append({"id": "porch", "name": "porch", "model": "esp32", "link": {"type": "wifi"}})
        cfg["components"].append(sw("porch_light", "porch", 23))
        self.assertEqual(self.post("/api/config", cfg)[0], 200)
        self.assertTrue(self.rig.wait(lambda: self.get("/api/state")["boards"].get("porch", {}).get("online")))
        self.assertEqual([x["key"] for x in self.get("/api/state")["discovered"]], ["usb:/dev/ttyACM9"])
        self.assertEqual(self.post("/api/sim", {"discover": None}), (200, {"ok": True}))
        self.assertTrue(self.rig.wait(lambda: self.get("/api/state")["discovered"] == []))
        self.assertEqual(self.post("/api/sim", {"board": "main", "pin": 2, "value": 0}), (200, {"ok": True}))  # as before
        self.assertEqual(self.post("/api/sim", [1])[0], 400)

    def test_node_role_has_sys_and_time(self):
        import qh_web
        store = qh_engine.Engine(tempfile.mkdtemp(prefix="qhome-node-"))
        store.load_config(True)
        store.cfg["device"].update(role="node", node="attic", tz="UTC+2")
        mq = types.SimpleNamespace(subscribe=lambda *a: None, configure=lambda *a: None, publish=lambda *a, **k: None,
                                   status=lambda: {"ok": False, "mode": "external", "text": "-"})
        agent = NodeAgent(store, qh_hw.SimHW(lambda *a: None), mq)
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        srv = qh_web.start(agent, port, ".", {"role": "node", "sim": True, "has_local": True, "link_port": None})
        try:
            with self.urllib.urlopen("http://127.0.0.1:%d/api/state" % port, timeout=5) as r:
                st = json.loads(r.read())
            self.assertEqual((st["time"]["tz"], st["time"]["offset"]), ("UTC+2", 120))
            self.assertIn("cpu", st["sys"])
            self.assertTrue("mx" not in st and "discovered" not in st and "node" in st)
            with self.urllib.urlopen("http://127.0.0.1:%d/api/meta" % port, timeout=5) as r:
                meta = json.loads(r.read())
            self.assertEqual((meta["role"], meta["web_port"]), ("node", port))
            req = self.urllib.Request("http://127.0.0.1:%d/api/sim" % port, b'{"discover": null}')
            with self.urllib.urlopen(req, timeout=5) as r:
                self.assertEqual(json.loads(r.read()), {"ok": False})
        finally:
            srv.shutdown()
            srv.server_close()


# ===================================================================== 2.1: faults found in review
class OldSetupScripts(unittest.TestCase):
    """Dropping the devices of the old bottom connector must leave a setup that can be saved."""

    def old(self):
        cfg = demo_config(False)
        del cfg["device"]["tz"]
        cfg["device"]["tz_offset"] = 3                                # written by 2.0
        cfg["components"] += [sw("oldbtn", "main", 31, "binary_input"), sw("oldpump", "main", 30)]
        cfg["scripts"]["workspace"] = ws(
            chain({"type": "ev_state", "id": "a", "fields": {"ENT": "oldbtn", "TO": "on"}},
                  {"type": "do_toggle", "fields": {"ENT": "relay"}}),
            chain({"type": "ev_state", "id": "b", "fields": {"ENT": "button", "TO": "on"}},
                  {"type": "do_toggle", "fields": {"ENT": "relay"}}),
            chain({"type": "ev_start", "id": "c"},
                  {"type": "ctl_if", "inputs": {"COND": {"block": {"type": "get_on", "fields": {"ENT": "oldbtn"}}},
                                                "DO": {"block": {"type": "do_turn", "fields": {"ENT": "oldpump", "TO": "on"}}}}}))
        return cfg

    def test_migrate_leaves_a_valid_setup(self):
        cfg = self.old()
        notes = qh_engine.migrate(cfg)
        self.assertEqual(len(notes), 2, notes)
        self.assertIn("oldbtn, oldpump", notes[0])
        self.assertIn("Switched off 2 block script(s)", notes[1])
        self.assertIn("Script 1, Script 3", notes[1], "numbered as the validation messages number them")
        self.assertIn("Enable Block", notes[1])
        self.assertEqual(qh_engine.validate(cfg), [], "a later Save & apply is not refused")
        tops = cfg["scripts"]["workspace"]["blocks"]["blocks"]
        self.assertEqual([qh_script.enabled(b) for b in tops], [False, True, False])
        self.assertEqual(tops[0]["fields"]["ENT"], "oldbtn", "the script is kept for the user to repair")
        self.assertEqual([h["id"] for h in qh_script.hats(cfg["scripts"]["workspace"])], ["b"])
        self.assertEqual(qh_engine.migrate(cfg), [], "nothing left to do the second time")

    def test_matrix_that_showed_a_dropped_device(self):
        cfg = self.old()
        cfg["scripts"]["workspace"] = ws()
        cfg["components"].append(sw("oldlvl", "main", 40, "analog_sensor"))
        next(c for c in cfg["components"] if c["id"] == "matrix")["props"] = {"mode": "value", "source": "oldlvl"}
        notes = qh_engine.migrate(cfg)
        self.assertEqual(len(notes), 2, notes)
        self.assertIn("shows its text again", notes[1])
        self.assertEqual(next(c for c in cfg["components"] if c["id"] == "matrix")["props"],
                         {"mode": "text", "source": ""})
        self.assertEqual(qh_engine.validate(cfg), [])

    def test_engine_runs_and_saves_after_the_upgrade(self):
        rig = Rig(self.old())                                         # the old file is on the disk
        self.addCleanup(rig.close)
        e = rig.engine
        self.assertTrue(any("Switched off 2 block script(s)" in x["msg"] for x in e.logs))
        self.assertEqual(len(e.scripts.hats), 1)
        self.assertTrue(rig.wait(lambda: e.online.get("garage") and rig.state("button") is False))
        e.sim_input("main", 2, 0)                                     # the script that is still whole runs
        self.assertTrue(rig.wait(lambda: rig.state("relay") is True))
        cfg = clone(e.cfg)
        cfg["device"]["name"] = "Renamed"                             # any unrelated change
        self.assertEqual(e.submit_config(cfg), [])
        self.assertTrue(rig.wait(lambda: e.cfg["device"]["name"] == "Renamed"))

    def test_a_block_switched_off_in_the_editor_is_not_run(self):
        """Blockly saves "Disable Block" as disabledReasons (older files: enabled false)."""
        cfg = demo_config(False)
        off = {"type": "do_turn", "fields": {"ENT": "relay", "TO": "on"}, "disabledReasons": ["MANUALLY_DISABLED"]}
        cfg["scripts"]["workspace"] = ws(
            chain({"type": "ev_start", "id": "a"}, off, {"type": "do_turn", "fields": {"ENT": "away", "TO": "on"}}),
            chain({"type": "ev_start", "id": "b", "disabledReasons": ["MANUALLY_DISABLED"]},
                  {"type": "do_turn", "fields": {"ENT": "nope", "TO": "on"}}),
            chain({"type": "ev_start", "id": "c", "enabled": False},
                  {"type": "do_turn", "fields": {"ENT": "nope", "TO": "on"}}))
        self.assertEqual(qh_engine.validate(cfg), [], "a script that is switched off is not checked")
        rig = Rig(cfg)
        self.addCleanup(rig.close)
        self.assertTrue(rig.wait(lambda: rig.state("away") is True))
        self.assertFalse(rig.state("relay"), "the block that is switched off was skipped")


class StateFile(unittest.TestCase):
    """state.json holds the outputs for "after a restart: as it was"."""

    def saved(self, rig):
        try:
            with open(rig.engine.state_path) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def test_a_live_matrix_does_not_hold_up_the_save(self):
        cfg = mx_config(mode="value", source="temp", scroll_ms=40)
        rig = Rig(cfg)
        self.addCleanup(rig.close)
        e = rig.engine
        self.assertTrue(rig.wait(lambda: e.online.get("main") and rig.state("temp") is not None))
        stop = []

        def wiggle():                                                 # a value that changes all the time
            n = 0
            while not stop:
                n += 1
                e.sim_input("main", 14, 2000 + (n % 50) * 200)
                time.sleep(0.05)
        th = threading.Thread(target=wiggle, daemon=True)
        th.start()
        self.addCleanup(th.join, 1)
        self.addCleanup(stop.append, 1)
        seen = set()
        rig.wait(lambda: seen.add(rig.state("matrix")) or len(seen) >= 3, 4)
        self.assertGreaterEqual(len(seen), 3, "the matrix state follows the value")
        e.submit_command("away", "on")
        e.submit_command("fan", "set", 40)
        self.assertTrue(rig.wait(lambda: self.saved(rig).get("away") is True, 4.5),
                        "the outputs are saved although the matrix keeps changing")
        got = self.saved(rig)
        self.assertEqual(got["fan"], {"on": True, "level": 40.0})
        self.assertNotIn("matrix", got, "a matrix always starts from its setup")

    def test_the_save_is_a_deadline_not_a_quiet_time(self):
        rig = Rig(mx_config())
        self.addCleanup(rig.close)
        e = rig.engine
        self.assertTrue(rig.wait(lambda: e.online.get("main")))
        t0, n = time.time(), 0
        while time.time() - t0 < 3.6 and self.saved(rig).get("away") is None:
            n += 1
            e.submit_command("away", "toggle")                        # an output that never rests
            time.sleep(0.2)
        self.assertLess(time.time() - t0, 3.5, "saved about 2 s after the first change")
        self.assertGreater(n, 5)

    def test_matrix_changes_alone_write_nothing(self):
        rig = Rig(mx_config())
        self.addCleanup(rig.close)
        e = rig.engine
        self.assertTrue(rig.wait(lambda: e.online.get("main") and e.mx["matrix"]["last"]))
        time.sleep(0.3)
        e._state_dirty = 0
        if os.path.exists(e.state_path):
            os.remove(e.state_path)
        e.submit_command("matrix", "text", "A")
        self.assertTrue(rig.wait(lambda: rig.state("matrix") == "A"))
        self.assertEqual(e._state_dirty, 0)


class SkippedHour(unittest.TestCase):
    """The night the clocks go forward has no 02:00-02:59: a script set to such a time runs when
    the hour is skipped, once, and only for a real daylight-saving change."""

    def rt(self, zone, *hats):
        tz, exact = qh_tz.resolve(zone)
        if not exact or zone not in qh_tz.zones():
            self.skipTest("no time zone database on this computer")
        clock = [0.0]
        cfg = demo_config(False)
        cfg["device"]["tz"] = zone
        eng = qh_engine.Engine(tempfile.mkdtemp(prefix="qhome-dst-"))
        eng.cfg = cfg
        real = time.time

        def local_time():                                             # Engine.local_time on a fake clock
            time.time = lambda: clock[0]
            try:
                return qh_engine.Engine.local_time(eng)
            finally:
                time.time = real
        fake = types.SimpleNamespace(local_time=local_time, log=lambda *a: None)
        rt = qh_script.Runtime(fake)
        rt.load(ws(*[chain({"type": "ev_time", "id": hid, "fields": {"AT": at, "DAYS": days}},
                           {"type": "do_log", "inputs": {"TEXT": {"shadow": {"type": "text", "fields": {"TEXT": "x"}}}}})
                     for hid, at, days in hats]))
        return rt, clock

    def run_span(self, rt, clock, start, hours, step=20):
        """-> [(hat id, local 'HH:MM' at launch)] for every launch between two UTC times."""
        import calendar
        fired = []
        t = calendar.timegm(start + (0,))
        end = t + int(hours * 3600)
        while t <= end:
            clock[0] = t
            rt._timers(t)
            for th in rt.threads:
                lt = rt.e.local_time()
                fired.append((th.hat["id"], "%02d:%02d" % (lt.tm_hour, lt.tm_min)))
            rt.threads = []
            t += step
        return fired

    def test_local_time_carries_the_utc_offset(self):
        rt, clock = self.rt("Europe/Berlin", ("a", "02:30", "all"))
        clock[0] = 1774745400                                         # 2026-03-29 00:50 UTC = 01:50 CET
        lt = rt.e.local_time()
        self.assertEqual((lt.tm_hour, lt.tm_min, lt.tm_gmtoff, lt.tm_wday, lt.tm_isdst), (1, 50, 3600, 6, 0))
        clock[0] += 1200                                              # 01:10 UTC = 03:10 CEST
        lt = rt.e.local_time()
        self.assertEqual((lt.tm_hour, lt.tm_min, lt.tm_gmtoff, lt.tm_isdst), (3, 10, 7200, 1))

    def test_time_in_the_skipped_hour_runs_once(self):
        rt, clock = self.rt("Europe/Berlin", ("a", "02:30", "all"), ("b", "02:00", "all"), ("c", "02:59", "weekdays"),
                            ("d", "03:00", "all"), ("e", "01:59", "all"), ("f", "03:30", "all"), ("g", "02:15", "sun"))
        fired = self.run_span(rt, clock, (2026, 3, 29, 0, 20, 0), 2)  # Sunday; 01:00 UTC: 02:00 -> 03:00
        self.assertEqual(sorted(fired), [("a", "03:00"), ("b", "03:00"), ("d", "03:00"), ("e", "01:59"),
                                         ("f", "03:30"), ("g", "03:00")],
                         "the skipped times run at 03:00 (not the weekday one: it is Sunday)")

    def test_ordinary_days_and_the_night_the_clocks_go_back(self):
        rt, clock = self.rt("Europe/Berlin", ("a", "02:30", "all"))
        self.assertEqual(self.run_span(rt, clock, (2026, 3, 27, 23, 0, 0), 4), [("a", "02:30")])
        fired = self.run_span(rt, clock, (2026, 10, 24, 22, 0, 0), 52)          # 25 October has 02:30 twice
        self.assertEqual(fired, [("a", "02:30")] * 3, "once a day, also on the long night")

    def test_half_hour_zone_and_midnight_change(self):
        rt, clock = self.rt("Australia/Lord_Howe", ("a", "02:10", "all"), ("b", "02:40", "all"))
        fired = self.run_span(rt, clock, (2026, 10, 3, 14, 0, 0), 3)            # 02:00 -> 02:30 on 4 October
        self.assertEqual(sorted(fired), [("a", "02:30"), ("b", "02:40")])
        rt, clock = self.rt("Asia/Beirut", ("a", "00:30", "all"), ("b", "23:50", "all"))
        fired = self.run_span(rt, clock, (2026, 3, 28, 21, 0, 0), 2)            # 00:00 -> 01:00 on 29 March
        self.assertEqual(sorted(fired), [("a", "01:00"), ("b", "23:50")])

    def test_only_a_daylight_saving_change_counts(self):
        rt, clock = self.rt("Europe/Berlin", ("a", "02:30", "all"), ("b", "12:30", "all"))
        import calendar
        clock[0] = t = calendar.timegm((2026, 3, 28, 22, 0, 0))       # the computer sleeps through the night
        rt._timers(t)
        clock[0] = t = t + 9 * 3600
        rt._timers(t)
        self.assertEqual(rt.threads, [], "timers missed while asleep are not replayed")
        clock[0] = t = calendar.timegm((2026, 6, 1, 9, 0, 0))         # 11:00 in Berlin
        rt._timers(t)
        rt.e.local_time = lambda: time.struct_time((2026, 6, 1, 14, 0, 0, 0, 152, 0, "+05", 18000))
        rt.clock_changed()                                            # the user picked another zone: 14:00 now
        rt._timers(t)
        self.assertEqual(rt.threads, [], "12:30 was not skipped by a clock change")

    def test_engine_tells_the_timers_about_a_new_zone(self):
        cfg = demo_config(False)
        cfg["device"]["tz"] = "UTC"
        rig = Rig(cfg)
        self.addCleanup(rig.close)
        e = rig.engine
        self.assertTrue(rig.wait(lambda: e.scripts._clock is not None))
        calls = []
        e.scripts.clock_changed = lambda: calls.append(1)
        cfg2 = clone(e.cfg)
        cfg2["device"]["name"] = "x"
        self.assertEqual(e.submit_config(cfg2), [])
        self.assertTrue(rig.wait(lambda: e.cfg["device"]["name"] == "x"))
        self.assertEqual(calls, [])
        cfg2 = clone(cfg2)
        cfg2["device"]["tz"] = "UTC+3"
        self.assertEqual(e.submit_config(cfg2), [])
        self.assertTrue(rig.wait(lambda: calls == [1]))


class Addresses(unittest.TestCase):
    def env(self, **kv):
        keep = {k: os.environ.get(k) for k in ("HOST_IP", "BOARD_NAME")}
        route = qh_sys._route_ip

        def undo():
            qh_sys._route_ip = route
            for k, v in keep.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        self.addCleanup(undo)
        for k, v in kv.items():
            os.environ[k] = v

    def test_docker_bridge_of_another_network_is_not_an_address(self):
        """No network when the app starts: HOST_IP is docker0 (172.17.0.1), while the app's
        container sits on its own network (172.18.x)."""
        self.env(BOARD_NAME="unoq", HOST_IP="172.17.0.1")
        qh_sys._route_ip = lambda: "172.18.0.2"
        self.assertEqual(qh_sys.ip_list(), [])
        self.assertEqual(qh_sys.banner("2.1.0", "Home", qh_sys.ip_list(), 7000, 1883, True)[2:4],
                         ["   http://<board-name>.local:7000", " MQTT broker: port 1883"])
        self.assertIn("No network address yet. Web port 7000", qh_sys.monitor_text("2.1.0", "Home", qh_sys.ip_list(), 7000))
        for bridge in ("172.18.0.1", "172.19.0.1", "172.31.255.1", "172.18.5.9"):
            os.environ["HOST_IP"] = bridge
            self.assertEqual(qh_sys.ip_list(), [], bridge)

    def test_lan_addresses_in_the_same_range_are_kept(self):
        self.env(BOARD_NAME="unoq", HOST_IP="172.20.5.10")            # an office LAN in 172.16.0.0/12
        qh_sys._route_ip = lambda: "172.18.0.2"
        self.assertEqual(qh_sys.ip_list(), ["172.20.5.10"])
        for lan in ("192.168.1.50", "10.0.0.1", "172.32.0.1", "172.15.0.1"):
            os.environ["HOST_IP"] = lan
            self.assertEqual(qh_sys.ip_list(), [lan])
        os.environ["HOST_IP"] = "172.17.0.1"
        qh_sys._route_ip = lambda: None                               # nothing known about the container
        self.assertEqual(qh_sys.ip_list(), ["172.17.0.1"])
        qh_sys._route_ip = lambda: "10.0.3.7"                         # the container is not on a Docker 172 net
        self.assertEqual(qh_sys.ip_list(), ["172.17.0.1", "10.0.3.7"])

    def test_host_name_lookup_never_holds_up_the_caller(self):
        keep = qh_sys._names, qh_sys._names_busy, socket.gethostbyname_ex
        calls = []

        def slow(name):
            calls.append(name)
            time.sleep(1.0)
            return (name, [], ["10.9.8.7", "127.0.1.1"])

        def undo():
            end = time.time() + 3
            while qh_sys._names_busy and time.time() < end:
                time.sleep(0.02)
            qh_sys._names, qh_sys._names_busy, socket.gethostbyname_ex = keep
        self.addCleanup(undo)
        socket.gethostbyname_ex = slow
        qh_sys._names, qh_sys._names_busy = None, False
        t0 = time.time()
        self.assertEqual(qh_sys._host_ips(), [], "nothing known yet")
        self.assertEqual(qh_sys._host_ips(), [])
        self.assertLess(time.time() - t0, 0.7, "the first call waits a moment at most, the next not at all")
        self.assertEqual(len(calls), 1, "one lookup at a time")
        end = time.time() + 3
        while qh_sys._names_busy and time.time() < end:
            time.sleep(0.02)
        self.assertEqual(qh_sys._host_ips(), ["10.9.8.7", "127.0.1.1"])
        self.assertEqual(len(calls), 1, "cached for 30 s")
        qh_sys._names = (time.time() - 31, ["10.9.8.7"])              # stale: refreshed behind the scenes
        t0 = time.time()
        self.assertEqual(qh_sys._host_ips(), ["10.9.8.7"])
        self.assertEqual(qh_sys._host_ips(), ["10.9.8.7"])
        self.assertLess(time.time() - t0, 0.2)
        self.assertEqual(len(calls), 2)
        socket.gethostbyname_ex = lambda name: (_ for _ in ()).throw(socket.gaierror("no such host"))
        end = time.time() + 3
        while qh_sys._names_busy and time.time() < end:
            time.sleep(0.02)
        qh_sys._names = None
        self.assertEqual(qh_sys._host_ips(), [], "a lookup that fails gives no address")
        self.assertFalse(qh_sys._names_busy)


class QLinkSubscriptions(unittest.TestCase):
    def test_one_subscription_per_qlink_topic(self):
        """Two subscriptions matching one topic make some brokers (EMQX) send every message once
        per subscription, and every QLink line of a Wi-Fi board would be handled twice."""
        from qh_mqtt import topic_match
        os.environ["QHOME_REAL_LINKS"] = "1"
        self.addCleanup(lambda: os.environ.pop("QHOME_REAL_LINKS", None))
        port = 18937
        cfg = demo_config(False)
        cfg["boards"] = [cfg["boards"][0], {"id": "attic", "name": "Attic Q", "model": "unoq", "link": {"type": "wifi"}},
                         {"id": "porch", "name": "Porch", "model": "esp32", "link": {"type": "wifi"}}]
        cfg["components"] = [sw("lamp", "attic", 8)]
        rig = start_master(cfg, port)
        self.addCleanup(rig.close)
        e = rig.engine
        self.assertTrue(rig.wait(lambda: e.transports["attic"].up and e.transports["porch"].up))
        for topic in ("qlink/attic/up", "qlink/attic/status", "qlink/porch/up", "qlink/porch/status", "qlink/new1/up"):
            hits = [f for f in e.mqtt.local_filters if topic_match(f, topic)]
            self.assertEqual(len(hits), 1, "%s is matched by %r" % (topic, hits))
        node = FakeNode("attic", port)                                # and the one subscription is enough
        self.addCleanup(node.stop, False)
        self.assertTrue(rig.wait(lambda: e.online.get("attic"), 8))
        e.submit_command("lamp", "on")
        self.assertTrue(rig.wait(lambda: node.hw.out.get(8) == 1))
        self.assertEqual(e.transports["attic"].text, "MQTT")


class PtyBoard:
    """A QHome satellite on a pseudo terminal: a real serial device with a real name."""

    def __init__(self, model="uno", boot="1a2b"):
        self.master, slave = os.openpty()
        self.name = os.ttyname(slave)
        os.close(slave)
        self.model, self.boot, self.rx, self.run = model, boot, [], True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        import select
        buf = b""
        while self.run:
            try:
                if not select.select([self.master], [], [], 0.1)[0]:
                    continue
                data = os.read(self.master, 256)
            except OSError:
                time.sleep(0.05)                                      # nobody has the other end open
                continue
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.decode("ascii", "replace").strip()
                self.rx.append(line)
                try:
                    if line == "H":
                        os.write(self.master, ("h 1 %s %s\n" % (self.model, self.boot)).encode())
                    elif line == "P":
                        os.write(self.master, ("p %s\n" % self.boot).encode())
                    elif line.startswith("C "):
                        os.write(self.master, ("c %s %s\n" % tuple(line.split()[1:3])).encode())
                except OSError:
                    pass

    def close(self):
        self.run = False
        time.sleep(0.15)
        try:
            os.close(self.master)
        except OSError:
            pass


@unittest.skipUnless(hasattr(os, "openpty") and os.name == "posix", "needs pseudo terminals")
class PortNames(unittest.TestCase):
    """One serial device has several names (/dev/serial/by-id/... points to /dev/ttyACM0). A
    setup may use one and the port list show the other: it is still one port."""

    def alias(self, dev):
        d = tempfile.mkdtemp(prefix="qhome-byid-")
        link = os.path.join(d, "usb-Arduino_UNO-if00")
        os.symlink(dev.name, link)
        return link

    def test_port_key(self):
        import qh_link
        dev = PtyBoard()
        self.addCleanup(dev.close)
        link = self.alias(dev)
        self.assertEqual(qh_link.port_key(link), qh_link.port_key(dev.name))
        self.assertEqual(qh_link.port_key(dev.name), os.path.realpath(dev.name))
        for same in ("helper:ttyACM0", "tcp://10.0.0.5:7001", ""):
            self.assertEqual(qh_link.port_key(same), same)
        self.assertEqual(qh_link.port_key(None), "")

    def test_a_port_held_under_one_name_is_not_probed_under_another(self):
        import qh_link
        dev = PtyBoard()
        self.addCleanup(dev.close)
        link = self.alias(dev)
        hub = qh_link.PortHub(lambda *a: None)
        name, port = hub.open(dev.name, 115200)                       # what a transport does
        self.assertEqual(name, dev.name)
        self.addCleanup(port.close)
        self.assertIs(hub.probe(link, timeout=0.6), False)
        self.assertEqual(hub.open(link, 115200), (None, None), "nor opened a second time")
        time.sleep(0.2)
        self.assertEqual(dev.rx, [], "nothing was written into the live link")
        port.write(b"H\n")
        self.assertIn(b"h 1 uno 1a2b", port.read(1.0) + port.read(0.2), "the holder still gets its answers")
        hub.release(dev.name)
        self.assertEqual(hub.claimed, set())
        self.assertEqual(hub.probe(link, timeout=2), (1, "uno", "1a2b"), "free again, under either name")
        self.assertEqual(hub.claimed, set())

    def test_release_after_the_alias_is_gone(self):
        import qh_link
        dev = PtyBoard()
        self.addCleanup(dev.close)
        link = self.alias(dev)
        hub = qh_link.PortHub(lambda *a: None)
        name, port = hub.open(link, 115200)
        self.assertEqual(hub.claimed, {os.path.realpath(dev.name)})
        port.close()
        os.remove(link)                                               # unplugged: the by-id name is gone
        hub.release(name)
        self.assertEqual(hub.claimed, set(), "or the port would look busy for ever")

    def test_configured_board_is_never_probed_or_listed_as_found(self):
        """The setup names the tty, the port list shows its by-id name."""
        import qh_link
        dev = PtyBoard()
        self.addCleanup(dev.close)
        link = self.alias(dev)
        keep = qh_link.glob.glob, qh_link._have_pyserial
        qh_link.glob.glob = lambda pat: [link] if pat == "/dev/serial/by-id/*" else []
        qh_link._have_pyserial = lambda: False

        def undo():
            qh_link.glob.glob, qh_link._have_pyserial = keep
        self.addCleanup(undo)
        os.environ["QHOME_REAL_LINKS"] = "1"
        self.addCleanup(lambda: os.environ.pop("QHOME_REAL_LINKS", None))
        cfg = demo_config(False)
        cfg["boards"] = [cfg["boards"][0], {"id": "garage", "name": "Garage", "model": "uno",
                                            "link": {"type": "usb", "port": dev.name}}]
        cfg["components"] = [sw("lamp", "garage", 7)]
        rig = Rig(cfg, probe=True, disc_every=0.2)
        self.addCleanup(rig.close)
        e = rig.engine
        probed = []
        real_probe = e.ports.probe
        e.ports.probe = lambda name, *a, **k: probed.append(name) or real_probe(name, *a, **k)
        self.assertTrue(rig.wait(lambda: e.online.get("garage"), 10))
        self.assertEqual(e.ports.list(), [{"name": link, "busy": True}], "busy under its other name too")
        time.sleep(1.2)                                               # several rounds of the port search
        self.assertEqual((probed, e.discovered), ([], {}))
        self.assertTrue(e._disc_taken({"key": "usb:" + link, "link": "usb", "port": link}))
        e.post(("found", {"key": "usb:" + link, "link": "usb", "port": link, "model": "uno", "proto": 1,
                          "boot": "1a2b", "t": time.time()}))
        time.sleep(0.3)
        self.assertEqual(e.discovered, {}, "its own board is not a new board")
        e.transports["garage"].stop()                                 # the link drops: the port is free,
        self.assertTrue(rig.wait(lambda: not e.ports.claimed, 5))     # but it is still garage's port
        time.sleep(0.8)
        self.assertEqual((probed, e.discovered), ([], {}))


class Schema(unittest.TestCase):
    def test_schema_file_is_current(self):
        import importlib.util
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        spec = importlib.util.spec_from_file_location("gen_schema", os.path.join(root, "tools", "gen_schema.py"))
        gen = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gen)
        with open(os.path.join(root, "schema", "qhome-config.schema.json"), encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved, json.loads(json.dumps(gen.build())), "run: python tools/gen_schema.py")
        dev = saved["properties"]["device"]["properties"]
        self.assertEqual(dev["tz"]["default"], "Europe/Istanbul")
        self.assertEqual(len(dev["tz"]["anyOf"][0]["enum"]), 56)
        self.assertIn("tz_offset", dev)
        self.assertEqual(saved["properties"]["boards"]["items"]["properties"]["model"]["enum"], list(qh_boards.MODELS))
        text = json.dumps(saved)
        self.assertNotIn("jmisc", text.lower())
        mx = next(v for v in saved["properties"]["components"]["items"]["allOf"]
                  if v["if"]["properties"]["type"]["const"] == "led_matrix")["then"]["properties"]["props"]["properties"]
        self.assertEqual(mx["mode"], {"enum": list(font.MODES), "default": "text"})
        self.assertEqual(mx["source"], {"type": "string", "default": ""})


if __name__ == "__main__":
    unittest.main()
