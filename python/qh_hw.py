"""Hardware layer.

LocalHW    the UNO Q's own STM32, reached through the Arduino Router Bridge (RPC)
SimHW      in-memory board for running on a PC (VS Code, tests)
QLinkHW    a remote board that speaks the QLink line protocol over any transport
QLinkDevice  the device side of QLink on top of a LocalHW/SimHW (simulated satellites
             and UNO Q "node" mode)

All of them expose the same small interface to the engine:
  configure(pin, mode, interval_ms, debounce_ms)  write_digital(pin, v)
  write_analog(pin, v12)  rgb(led, bits)  matrix(frame)  reset()  poll(now)
LocalHW and SimHW also take info(text): the start banner for the Serial Monitor.
"""
import math
import random
import re
import threading
import time

# Pin modes, identical in sketch/sketch.ino and satellite/qhome_satellite
M_OFF, M_DIN, M_DIN_PU, M_DIN_PD, M_DOUT, M_PWM, M_ADC, M_DAC, M_CNT = range(9)

RGB_BITS = {"off": 0, "red": 1, "green": 2, "yellow": 3, "blue": 4,
            "magenta": 5, "cyan": 6, "white": 7}
QLINK_PROTO = 1
HELLO_RE = re.compile(r"^h (\d+) ([a-z0-9_]+) ([0-9a-f]+)$")   # h <proto> <model> <boot id>

_LINUX_LEDS = {1: ("red:user", "green:user", "blue:user"),
               2: ("red:panic", "green:wlan", "blue:bt")}


class LocalHW:
    """The UNO Q microcontroller, through the Router Bridge."""
    simulated = False

    def __init__(self, on_event, on_boot, on_link_rx, log):
        from arduino.app_utils import Bridge  # only exists on the UNO Q
        self._b = Bridge
        self.log = log
        self.connected = False
        self.version = None
        self._led_warned = False
        # Bridge callbacks must not call back into the Bridge: they only queue.
        self._b.provide("q_ev", lambda pin, val: on_event(int(pin), int(val)))
        self._b.provide("q_boot", lambda ver: on_boot(int(ver)))
        self._b.provide("q_lrx", lambda lid, line: on_link_rx(int(lid), str(line)))

    def _call(self, name, *args):
        try:
            r = self._b.call(name, *args, timeout=3)
            self.connected = True
            return r
        except Exception as e:  # timeout / MCU not ready / sketch missing
            if self.connected:
                self.log("Lost contact with the microcontroller: %s" % e, "err")
            self.connected = False
            return None

    def probe(self):
        self.version = self._call("q_ver")
        return self.version is not None

    def configure(self, pin, mode, interval=1000, debounce=30):
        return self._call("q_cfg", int(pin), int(mode), int(interval), int(debounce))

    def write_digital(self, pin, v):
        return self._call("q_dw", int(pin), 1 if v else 0)

    def write_analog(self, pin, v12):
        return self._call("q_aw", int(pin), int(v12))

    def rgb(self, led, bits):
        if led in _LINUX_LEDS:
            return self._linux_led(led, bits)
        return self._call("q_rgb", int(led), int(bits))

    def _linux_led(self, led, bits):
        r, g, b = bool(bits & 1), bool(bits & 2), bool(bits & 4)
        try:
            from arduino.app_utils import Leds
            (Leds.set_led1_color if led == 1 else Leds.set_led2_color)(r, g, b)
            return bits
        except Exception:
            pass
        try:
            for name, on in zip(_LINUX_LEDS[led], (r, g, b)):
                with open("/sys/class/leds/%s/brightness" % name, "w") as f:
                    f.write("1" if on else "0")
            return bits
        except OSError as e:
            if not self._led_warned:
                self._led_warned = True
                self.log("LED%d is driven by Linux and could not be set: %s" % (led, e), "warn")
            return None

    def matrix(self, frame):
        return self._call("q_mx", frame)

    def reset(self):
        return self._call("q_reset")

    # wired links hosted by the microcontroller (UART on D0/D1, I2C on SDA/SCL or Qwiic)
    def link_open(self, lid, kind, a, b):
        return self._call("q_lopen", int(lid), int(kind), int(a), int(b))

    def link_tx(self, lid, data):
        return self._call("q_ltx", int(lid), data)

    def link_close(self, lid):
        return self._call("q_lclose", int(lid))

    def info(self, text):
        """Start banner for the microcontroller's Serial Monitor. Needs firmware v5; skipped otherwise."""
        try:
            new_enough = int(self.version or 0) >= 5
        except (TypeError, ValueError):
            new_enough = False
        if not self.connected or not new_enough:
            return None
        try:
            return self._b.call("q_info", str(text)[:190], timeout=3)
        except Exception:
            return None          # optional feature: never mark the microcontroller as lost because of it

    def poll(self, now=None):
        pass


class SimHW:
    """A pretend board: remembers pin modes, invents ADC readings and pulses."""
    simulated = True

    def __init__(self, on_event, adc_max=16383, log=None):
        self.on_event = on_event
        self.adc_max = adc_max
        self.log = log or (lambda *a: None)
        self.connected = True
        self.version = 5
        self.info_text = ""
        self.modes, self.cfg, self.din, self.out, self.cnt, self.last_rep = {}, {}, {}, {}, {}, {}
        self.matrix_frame = "0" * 104
        self.leds = {}
        self.t0 = time.time()
        self._lock = threading.Lock()

    def probe(self):
        return True

    def configure(self, pin, mode, interval=1000, debounce=30):
        with self._lock:
            self.modes[pin] = mode
            self.cfg[pin] = interval
            self.last_rep[pin] = 0
            if mode == M_CNT:
                self.cnt[pin] = 0
            if mode in (M_DIN, M_DIN_PU, M_DIN_PD):
                self.din[pin] = 1 if mode == M_DIN_PU else 0
                self.on_event(pin, self.din[pin])
        return mode

    def write_digital(self, pin, v):
        self.out[pin] = 1 if v else 0
        return self.out[pin]

    def write_analog(self, pin, v12):
        self.out[pin] = v12
        return v12

    def rgb(self, led, bits):
        self.leds[led] = bits
        return bits

    def matrix(self, frame):
        self.matrix_frame = frame
        return len(frame)

    def reset(self):
        with self._lock:
            self.modes.clear()
        return 1

    def link_open(self, *a):
        return 1

    def link_tx(self, *a):
        return 1

    def link_close(self, *a):
        return 1

    def info(self, text):
        self.info_text = text
        return len(text)

    def sim_input(self, pin, value):
        with self._lock:
            if self.modes.get(pin) in (M_DIN, M_DIN_PU, M_DIN_PD):
                self.din[pin] = 1 if value else 0
                self.on_event(pin, self.din[pin])
                return True
        return False

    def poll(self, now=None):
        now = now or time.time()
        with self._lock:
            for pin, mode in list(self.modes.items()):
                if mode not in (M_ADC, M_CNT):
                    continue
                if now - self.last_rep.get(pin, 0) < self.cfg.get(pin, 1000) / 1000.0:
                    continue
                self.last_rep[pin] = now
                if mode == M_ADC:
                    base = 0.5 + 0.35 * math.sin((now - self.t0) / 20.0 + pin)
                    raw = (base + random.uniform(-0.01, 0.01)) * self.adc_max
                    self.on_event(pin, int(max(0, min(self.adc_max, raw))))
                else:
                    self.cnt[pin] = self.cnt.get(pin, 0) + random.randint(3, 9)
                    self.on_event(pin, self.cnt[pin])


class QLinkHW:
    """Master-side view of a remote board. A transport sets `send` and feeds lines in."""
    simulated = False

    def __init__(self, board_id, on_event, on_boot, log):
        self.board_id = board_id
        self.on_event, self.on_boot, self.log = on_event, on_boot, log
        self.send = None          # callable(line) installed by the transport
        self.link_up = False      # transport is open
        self.connected = False    # board answered the handshake
        self.version = None
        self.remote_model = None
        self.boot_id = None
        self.last_rx = self.last_hello = self.last_ping = 0.0

    def _tx(self, line):
        if self.send and self.link_up:
            try:
                self.send(line)
                return True
            except Exception as e:
                self.log("%s: send failed: %s" % (self.board_id, e), "warn")
        return None

    def set_link(self, up):
        if up == self.link_up:
            return
        self.link_up = up
        self.last_hello = 0.0
        if not up and self.connected:
            self.connected = False
            self.on_boot(None)

    def feed(self, line):
        parts = line.strip().split()
        if not parts:
            return
        self.last_rx = time.time()
        k = parts[0]
        try:
            if k == "E" and len(parts) >= 3:
                self.on_event(int(parts[1]), int(parts[2]))
            elif k == "h" and len(parts) >= 4:
                boot = parts[3]
                fresh = not self.connected or boot != self.boot_id
                self.version, self.remote_model, self.boot_id = int(parts[1]), parts[2], boot
                self.connected = True
                if fresh:
                    self.on_boot(boot)
            elif k == "p" and len(parts) >= 2:
                if self.connected and parts[1] != self.boot_id:
                    self.connected = False   # it restarted: handshake again
                    self.last_hello = 0.0
            elif k == "B":
                self.connected = False
                self.last_hello = 0.0
            elif k == "c" and len(parts) >= 3 and int(parts[2]) < 0:
                self.log("%s: pin %s rejected the requested mode (%s)"
                         % (self.board_id, parts[1], parts[2]), "err")
        except ValueError:
            pass  # noise on the wire (boot messages, partial lines)

    def poll(self, now=None):
        now = now or time.time()
        if not self.link_up:
            return
        if not self.connected:
            if now - self.last_hello >= 1.0:
                self.last_hello = now
                self._tx("H")
        else:
            if now - self.last_rx > 7.0:
                self.connected = False
                self.on_boot(None)
            elif now - self.last_ping >= 2.0:
                self.last_ping = now
                self._tx("P")

    def probe(self):
        return self.connected

    def configure(self, pin, mode, interval=1000, debounce=30):
        return mode if self._tx("C %d %d %d %d" % (pin, mode, interval, debounce)) else None

    def write_digital(self, pin, v):
        return self._tx("D %d %d" % (pin, 1 if v else 0))

    def write_analog(self, pin, v12):
        return self._tx("A %d %d" % (pin, v12))

    def rgb(self, led, bits):
        return self._tx("L %d %d" % (led, bits))

    def matrix(self, frame):
        return self._tx("M " + frame)

    def reset(self):
        return self._tx("R")


class QLinkDevice:
    """Device side of QLink, driving a LocalHW or SimHW.

    Used for simulated satellites and for a UNO Q running as a node of another master.
    The Arduino satellite sketch implements the same protocol in C++.
    """

    def __init__(self, hw, model, send):
        self.hw, self.model, self.send = hw, model, send
        self.boot_id = "%04x" % random.randint(0, 0xFFFF)

    def event(self, pin, val):
        self.send("E %d %d" % (pin, val))

    def rebooted(self):
        self.boot_id = "%04x" % random.randint(0, 0xFFFF)
        self.send("B " + self.boot_id)

    def feed(self, line):
        parts = line.strip().split()
        if not parts:
            return
        k, a = parts[0], parts[1:]
        try:
            if k == "H":
                self.send("h %d %s %s" % (QLINK_PROTO, self.model, self.boot_id))
            elif k == "P":
                self.send("p " + self.boot_id)
            elif k == "C":
                pin = int(a[0])
                r = self.hw.configure(pin, int(a[1]), int(a[2]), int(a[3]))
                self.send("c %d %d" % (pin, -1 if r is None else int(r)))
            elif k == "D":
                self.hw.write_digital(int(a[0]), int(a[1]))
            elif k == "A":
                self.hw.write_analog(int(a[0]), int(a[1]))
            elif k == "L":
                self.hw.rgb(int(a[0]), int(a[1]))
            elif k == "M":
                self.hw.matrix(a[0] if a else "")
            elif k == "R":
                self.hw.reset()
                self.send("r 1")
        except (ValueError, IndexError):
            pass


def create_local(on_event, on_boot, on_link_rx, log, mode="auto"):
    """Pick the local board: the real microcontroller, a simulation, or none (PC as hub)."""
    if mode == "pc":
        return None
    if mode != "sim":
        try:
            hw = LocalHW(on_event, on_boot, on_link_rx, log)
            log("Router Bridge found: running on an UNO Q")
            return hw
        except ImportError:
            pass
    log("No Router Bridge here: running the built-in simulation", "warn")
    return SimHW(on_event, log=log)
