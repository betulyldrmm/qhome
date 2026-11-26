"""Transports that carry QLink lines between the master and its remote boards.

  usb    serial port on the Linux side (direct device, the USB helper, or tcp://host:port)
  uart   Serial1 on the master's D0/D1, relayed by the microcontroller
  i2c    master's SDA/SCL or Qwiic, the microcontroller polls the satellite
  wifi   MQTT topics qlink/<board>/down|up|status
  sim    an in-memory satellite (PC simulation)

Every transport posts received lines and link up/down changes to the engine queue;
the engine thread is the only one that touches board state.
"""
import glob
import os
import select
import socket
import threading
import time

import qh_boards
import qh_hw

MCU_UART, MCU_I2C_WIRE, MCU_I2C_QWIIC = 1, 2, 3


# ----------------------------------------------------------------- byte ports
class _PosixPort:
    def __init__(self, path, baud):
        import termios
        self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        try:
            a = termios.tcgetattr(self.fd)
            a[0] = a[1] = a[3] = 0
            a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
            a[4] = a[5] = getattr(termios, "B%d" % baud)
            a[6][termios.VMIN] = 0
            a[6][termios.VTIME] = 0
            termios.tcsetattr(self.fd, termios.TCSANOW, a)
        except Exception:
            os.close(self.fd)
            raise

    def read(self, timeout):
        r, _, _ = select.select([self.fd], [], [], timeout)
        if not r:
            return b""
        data = os.read(self.fd, 512)
        if not data:
            raise OSError("serial device went away")
        return data

    def write(self, data):
        while data:
            _, w, _ = select.select([], [self.fd], [], 2)
            if not w:
                raise OSError("serial write timed out")
            data = data[os.write(self.fd, data):]

    def close(self):
        try:
            os.close(self.fd)
        except OSError:
            pass


class _PySerialPort:
    def __init__(self, path, baud):
        import serial
        self.s = serial.Serial(path, baud, timeout=0.2, write_timeout=2)

    def read(self, timeout):
        self.s.timeout = timeout
        return self.s.read(self.s.in_waiting or 1)

    def write(self, data):
        self.s.write(data)

    def close(self):
        try:
            self.s.close()
        except Exception:
            pass


class _SocketPort:
    def __init__(self, sock):
        self.sock = sock

    def read(self, timeout):
        self.sock.settimeout(timeout)
        try:
            data = self.sock.recv(512)
        except socket.timeout:
            return b""
        if not data:
            raise OSError("connection closed")
        return data

    def write(self, data):
        self.sock.settimeout(2)
        self.sock.sendall(data)

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def _have_pyserial():
    try:
        import serial  # noqa: F401
        return True
    except ImportError:
        return False


def port_key(name):
    """One key per serial device, whatever it is called: /dev/serial/by-id/usb-... and the
    /dev/ttyACM0 it points to are the same port (a setup can name either: the port list shows the
    by-id name without pyserial and the tty name with it). Helper and tcp:// names are their own
    key. Claims and the "is this a configured board's port?" checks all compare this key."""
    name = str(name or "")
    if not name or name.startswith(("helper:", "tcp://")):
        return name
    try:
        return os.path.realpath(name)
    except (OSError, ValueError):
        return name


class PortHub:
    """Finds serial ports: local devices plus the ones forwarded by the USB helper."""

    def __init__(self, log):
        self.log = log
        self.claimed = set()   # port_key of every port in use (by a transport or a probe)
        self._claims = {}      # name it was opened by -> that key (a by-id name is gone after unplugging)
        self.helper = {}  # name -> connected socket
        self.lock = threading.Lock()
        self.server = None
        self.port = None

    def listen(self, port):
        """Accept the USB helper (tools/qhome_usb_helper.py) on a TCP port."""
        try:
            self.server = socket.create_server(("0.0.0.0", port))
        except OSError as e:
            self.log("USB helper port %d is not available: %s" % (port, e), "warn")
            return
        self.port = port
        threading.Thread(target=self._accept, daemon=True, name="usb-helper").start()

    def _accept(self):
        while True:
            try:
                conn, _ = self.server.accept()
                conn.settimeout(5)
                head = b""
                while not head.endswith(b"\n") and len(head) < 200:
                    ch = conn.recv(1)
                    if not ch:
                        break
                    head += ch
                words = head.decode("ascii", "replace").split()
                if len(words) >= 2 and words[0] == "@usb":
                    name = "helper:" + words[1]
                    with self.lock:
                        old = self.helper.pop(name, None)
                        self.helper[name] = conn
                    if old:
                        old.close()
                    self.log("USB helper attached %s" % words[1])
                else:
                    conn.close()
            except OSError:
                time.sleep(1)

    def list(self):
        out = []
        with self.lock:
            for name in sorted(self.helper):
                out.append({"name": name, "busy": name in self.claimed})
        seen = set()
        if _have_pyserial():
            from serial.tools import list_ports
            cands = [p.device for p in list_ports.comports()]
        else:
            cands = []
            for pat in ("/dev/serial/by-id/*", "/dev/ttyACM*", "/dev/ttyUSB*",
                        "/dev/cu.usbmodem*", "/dev/cu.usbserial*", "/dev/cu.wchusbserial*"):
                cands += sorted(glob.glob(pat))
        for c in cands:
            real = port_key(c)
            if real in seen:
                continue
            seen.add(real)
            out.append({"name": c, "busy": real in self.claimed})
        return out

    def open(self, want, baud):
        """Open the wanted port ("auto" = first free one). Returns (name, port) or (None, None)."""
        names = [p["name"] for p in self.list() if not p["busy"]] if want in ("", "auto", None) \
            else [want]
        for name in names:
            key = port_key(name)
            with self.lock:
                if key in self.claimed:            # in use, possibly under another name of the device
                    continue
                self.claimed.add(key)
                self._claims[name] = key
            try:
                return name, self._open(name, baud)
            except Exception as e:
                self.release(name)
                if want not in ("", "auto", None):
                    raise OSError("%s: %s" % (name, e))
        return None, None

    def _open(self, name, baud):
        if name.startswith("helper:"):
            with self.lock:
                sock = self.helper.pop(name, None)
            if sock is None:
                raise OSError("helper device not attached")
            return _SocketPort(sock)
        if name.startswith("tcp://"):
            host, _, port = name[6:].rpartition(":")
            return _SocketPort(socket.create_connection((host, int(port)), timeout=5))
        if _have_pyserial():
            return _PySerialPort(name, baud)
        if os.name != "posix":
            raise OSError("install pyserial to use serial ports on this system (pip install pyserial)")
        return _PosixPort(name, baud)

    def release(self, name):
        with self.lock:
            self.claimed.discard(self._claims.pop(name, None) or port_key(name))

    def probe(self, name, baud=115200, timeout=3.5):
        """Ask whoever is on a free port for its QLink hello.

        Returns (proto, model, boot) when a QHome satellite answered, None when the port is
        silent or speaks something else, False when the port could not be opened at all
        (a transport holds it, it went away, no access) or a helper connection broke
        meanwhile. The port is claimed for the time of the probe, by its port_key, so a transport
        and a probe can never use the same device at once, whichever of its names each one uses.
        """
        try:
            got, port = self.open(name, baud)
        except OSError:
            return False
        if port is None:
            return False
        result, alive = None, True
        try:
            buf, end, next_h = b"", time.time() + timeout, 0.0
            while result is None:
                now = time.time()
                if now >= end:
                    break
                if now >= next_h:                  # classic boards restart when the port opens
                    next_h = now + 0.5
                    port.write(b"H\n")
                buf += port.read(max(0.01, min(0.1, end - now)))
                while b"\n" in buf and result is None:
                    line, buf = buf.split(b"\n", 1)
                    m = qh_hw.HELLO_RE.match(line.decode("ascii", "replace").strip())
                    if m:
                        result = (int(m.group(1)), m.group(2), m.group(3))
                if len(buf) > 400:                 # boot text without line ends
                    buf = b""
        except Exception:
            alive = False
        finally:
            if alive and name.startswith("helper:") and isinstance(port, _SocketPort):
                with self.lock:                    # hand the helper's connection back: closing it
                    self.helper.setdefault(name, port.sock)   # would make the helper dial again
                    alive = self.helper[name] is port.sock
            if not (alive and name.startswith("helper:")):
                port.close()
            self.release(name)
        if result is None and not alive and name.startswith("helper:"):
            return False                           # the helper's connection broke: it will come back
        return result


# ----------------------------------------------------------------- transports
class Transport:
    kind = ""

    def __init__(self, engine, board, hw):
        self.engine, self.board, self.hw = engine, board, hw
        self.bid = board["id"]
        self.link = board.get("link") or {}
        self.text = "starting"
        hw.send = self.send

    def start(self):
        pass

    def stop(self):
        pass

    def send(self, line):
        pass

    def poll(self, now):
        pass

    def _rx(self, line):
        self.engine.post(("link", self.bid, line))

    def _state(self, up, text):
        self.text = text
        self.engine.post(("link_state", self.bid, up))


class SerialTransport(Transport):
    kind = "usb"

    def start(self):
        self.run = True
        self.port = None
        self.open_name = None            # name of the port it holds open (None while it has none)
        self.wlock = threading.Lock()
        threading.Thread(target=self._loop, daemon=True, name="usb-" + self.bid).start()

    def stop(self):
        self.run = False
        if self.port:
            self.port.close()

    def send(self, line):
        port = self.port
        if port is None:
            raise OSError("port closed")
        with self.wlock:
            port.write(line.encode("ascii", "replace") + b"\n")

    def _loop(self):
        hub = self.engine.ports
        want = self.link.get("port") or "auto"
        baud = int(self.link.get("baud") or 115200)
        while self.run:
            name = None
            try:
                name, port = hub.open(want, baud)
                if port is None:
                    self.text = "waiting for a USB board" if want == "auto" else "waiting for " + want
                    time.sleep(2)
                    continue
                self.open_name = name
                self.port = port
                self._state(True, name)
                buf = b""
                while self.run:
                    buf += port.read(0.25)
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        self._rx(line.decode("ascii", "replace"))
                    if len(buf) > 400:
                        buf = b""
            except Exception as e:
                if self.run:
                    self._state(False, str(e) or e.__class__.__name__)
            finally:
                if self.port:
                    self.port.close()
                    self.port = None
                self.open_name = None
                if name:
                    hub.release(name)
            if self.run:
                time.sleep(2)


class McuTransport(Transport):
    """UART or I2C link hosted by the master's own microcontroller."""

    def __init__(self, engine, board, hw, lid):
        super().__init__(engine, board, hw)
        self.lid = lid
        self.kind = self.link.get("type")
        self.opened = False
        self.next_try = 0

    def stop(self):
        local = self.engine.local
        if local and self.opened:
            local.link_close(self.lid)
        self.opened = False

    def reopen(self):
        self.opened = False
        self.next_try = 0

    def poll(self, now):
        local = self.engine.local
        if self.opened or now < self.next_try:
            return
        self.next_try = now + 3
        if local is None:
            self.text = "needs the UNO Q microcontroller"
            return
        if not local.connected:
            self.text = "waiting for the microcontroller"
            return
        if self.kind == "uart":
            r = local.link_open(self.lid, MCU_UART, int(self.link.get("baud") or 115200), 0)
            text = "UART on D0/D1"
        else:
            qwiic = self.link.get("bus") == "qwiic"
            addr = int(self.link.get("address") or 16)
            r = local.link_open(self.lid, MCU_I2C_QWIIC if qwiic else MCU_I2C_WIRE, addr,
                                int(self.link.get("poll_ms") or 40))
            text = "I2C 0x%02X on %s" % (addr, "Qwiic" if qwiic else "SDA/SCL")
        if r is not None and int(r) >= 0:
            self.opened = True
            self._state(True, text)
        else:
            self.text = "the microcontroller refused the link (update its sketch)"

    def send(self, line):
        local = self.engine.local
        if local is None or not self.opened:
            raise OSError("link closed")
        local.link_tx(self.lid, line + "\n")


# The MQTT subscriptions that carry QLink, for configured boards and for boards that are not in the
# setup yet (discovery) alike. There is deliberately no subscription per board next to them: with
# two filters matching one topic a broker may send every message once per filter (MQTT 3.1.1,
# 3.3.5; EMQX does), and each QLink line would then be handled twice.
QLINK_FILTERS = ("qlink/+/status", "qlink/+/up")


class MqttTransport(Transport):
    """QLink over MQTT. The link counts as open whenever MQTT is on; the QLink handshake
    (and the board's retained online/offline status) decides whether the board is there.
    Messages arrive through QLINK_FILTERS; Engine._handle_mqtt routes them here by board id."""
    kind = "wifi"

    def start(self):
        self.base = "qlink/%s/" % self.bid
        self.up = False

    def poll(self, now):
        mq = self.engine.mqtt
        if mq is None or mq.mode == "off":
            self.text = "turn MQTT on in Settings"
            return
        if not self.up:
            for filt in QLINK_FILTERS:              # normally there already (Engine._setup_mqtt)
                mq.subscribe(filt)
            self.up = True
            self._state(True, "waiting for the board on MQTT")

    def on_mqtt(self, topic, payload):
        if topic == self.base + "status":
            if payload.strip() == "online":
                self.text = "MQTT"
            else:
                self.up = False                      # reopened on the next poll
                self._state(False, "board is offline")
        elif topic == self.base + "up":
            self.text = "MQTT"
            for line in payload.split("\n"):
                if line.strip():
                    self._rx(line)

    def send(self, line):
        self.engine.mqtt.publish(self.base + "down", line)


class SimTransport(Transport):
    """A satellite that only exists in memory, so the whole system runs on a PC."""
    kind = "sim"

    def start(self):
        m = qh_boards.model(self.board.get("model")) or {}
        self.sim = qh_hw.SimHW(lambda pin, val: self.dev.event(pin, val),
                               adc_max=m.get("adc_max", 1023))
        self.dev = qh_hw.QLinkDevice(self.sim, self.board.get("model", "uno"), self._rx)
        self._state(True, "simulated")

    def send(self, line):
        self.dev.feed(line)

    def poll(self, now):
        self.sim.poll(now)


def create(engine, board, hw, lid):
    lt = (board.get("link") or {}).get("type")
    simulate = engine.local is not None and engine.local.simulated
    if simulate and os.environ.get("QHOME_REAL_LINKS") and lt in ("usb", "wifi"):
        simulate = False       # simulated master, real USB / Wi-Fi boards (used by the tests)
    if simulate:
        return SimTransport(engine, board, hw)
    if lt == "usb":
        return SerialTransport(engine, board, hw)
    if lt in ("uart", "i2c"):
        return McuTransport(engine, board, hw, lid)
    if lt == "wifi":
        return MqttTransport(engine, board, hw)
    return Transport(engine, board, hw)
