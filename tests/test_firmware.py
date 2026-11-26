"""Compiles the real Arduino sketches against a PC stand-in for the Arduino core
(tests/host/mock) and talks to them: QLink over serial, I2C and Wi-Fi/MQTT, plus the whole
chain  block script -> engine -> USB helper -> serial -> satellite firmware.

Boards are chosen by -D flags only, as the Arduino cores do (FLAGS below): UNO R3, Nano, Mega,
UNO R4, Nano R4, ESP32 DevKit V1, ESP32-C3 Super Mini and ESP8266 NodeMCU.

Needs g++ (skipped without it). This checks the firmware's logic and protocol; it cannot
check electrical behaviour or the vendor cores, so still try a real board once.
"""
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # also runnable as tests.test_firmware

from common import HERE, ROOT, Rig, demo_config  # noqa: E402

from qh_mqtt import MqttHub  # noqa: E402

MOCK = os.path.join(HERE, "host", "mock")
SAT = os.path.join(ROOT, "satellite", "qhome_satellite")
GXX = shutil.which("g++")
BUILD = tempfile.mkdtemp(prefix="qhome-fw-")


# Compiler flags that make the mock look like each of the four boards added in 2.1.
FLAGS = {
    "nanor4": ["-DARDUINO_NANO_R4", "-DARDUINO_UNOR4_MINIMA", "-DMOCK_NANO"],
    "esp32": ["-DARDUINO_ARCH_ESP32", "-DCONFIG_IDF_TARGET_ESP32=1"],
    "esp32c3": ["-DARDUINO_ARCH_ESP32", "-DCONFIG_IDF_TARGET_ESP32C3=1", "-DARDUINO_USB_CDC_ON_BOOT=1"],
    "esp8266": ["-DARDUINO_ARCH_ESP8266"],
}


def build(name, flags=(), config=None, master=False, run=False, expect_error=None):
    """Compile a sketch against the mock. Satellite: returns the program. Master: syntax check
    only, or with run=True a program driven by tests/host/mock/master_main.cpp.
    expect_error: the build must fail and the compiler output must contain this text."""
    out = os.path.join(BUILD, name)
    if os.path.exists(out):
        return out
    d = os.path.join(BUILD, name + "-src")
    os.makedirs(d, exist_ok=True)
    src = os.path.join(ROOT, "sketch", "sketch.ino") if master else os.path.join(SAT, "qhome_satellite.ino")
    with open(src) as f, open(os.path.join(d, "sketch.cpp"), "w") as o:
        o.write("#include <Arduino.h>\n" + f.read())
    if not master:
        with open(os.path.join(SAT, "config.h")) as f:
            text = f.read()
        for key, val in (config or {}).items():
            lines = text.split("\n")
            text = "\n".join(("#define %s %s" % (key, val)) if ln.startswith("#define %s " % key) else ln for ln in lines)
        with open(os.path.join(d, "config.h"), "w") as o:
            o.write(text)
    inc = ["-I" + os.path.join(MOCK, "unoq")] if master else []
    cmd = [GXX, "-std=c++17", "-Wall", "-Werror", "-Wno-unused-function", *flags, *inc, "-I" + MOCK, "-I" + d,
           os.path.join(d, "sketch.cpp")]
    if master and not run:
        cmd += ["-fsyntax-only"]
    else:
        cmd += [os.path.join(MOCK, "master_main.cpp" if master else "main.cpp"), "-o", out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if expect_error is not None:
        if r.returncode == 0:
            raise AssertionError("%s: the build should have been refused (%s)" % (name, expect_error))
        if expect_error not in r.stderr:
            raise AssertionError("%s: expected %r in:\n%s" % (name, expect_error, r.stderr[:3000]))
        return None
    if r.returncode:
        raise AssertionError("compile failed:\n" + r.stderr[:3000])
    return out


class Board:
    """A compiled satellite running as a process; stdout = link, stderr = pin writes."""

    def __init__(self, exe, stdin=subprocess.PIPE, stdout=subprocess.PIPE):
        self.p = subprocess.Popen([exe], stdin=stdin, stdout=stdout, stderr=subprocess.PIPE)
        self.lines, self.writes = queue.Queue(), []
        if stdout == subprocess.PIPE:
            threading.Thread(target=self._read, args=(self.p.stdout, self.lines.put), daemon=True).start()
        threading.Thread(target=self._read, args=(self.p.stderr, self.writes.append), daemon=True).start()

    @staticmethod
    def _read(stream, sink):
        for raw in stream:
            sink(raw.decode("ascii", "replace").strip())

    def send(self, line):
        self.p.stdin.write((line + "\n").encode())
        self.p.stdin.flush()

    def expect(self, prefix, timeout=3.0):
        end = time.time() + timeout
        seen = []
        while time.time() < end:
            try:
                line = self.lines.get(timeout=0.05)
            except queue.Empty:
                continue
            seen.append(line)
            if line.startswith(prefix):
                return line
        raise AssertionError("expected a line starting with %r, got %r" % (prefix, seen))

    def wrote(self, text, timeout=2.0):
        end = time.time() + timeout
        while time.time() < end:
            if text in self.writes:
                return True
            time.sleep(0.02)
        return False

    def ask(self, line, prefix=None):
        """Send one command and return its reply ('C 4 2 0 0' is answered by a line 'c 4 ...')."""
        self.send(line)
        if prefix is None:
            k, pin = line.split()[:2]
            prefix = "%s %s " % (k.lower(), pin)
        return self.expect(prefix)

    def bad(self):
        """Pin calls that would crash the real chip (the mock reports them as 'XX ...')."""
        return [w for w in self.writes if w.startswith("XX")]

    def close(self):
        self.p.kill()
        self.p.wait()
        for stream in (self.p.stdin, self.p.stdout, self.p.stderr):
            if stream:
                try:
                    stream.close()
                except OSError:
                    pass


@unittest.skipUnless(GXX, "g++ not installed")
class Firmware(unittest.TestCase):
    def test_master_sketch_compiles(self):
        build("master", flags=["-DMOCK_UNOQ"], master=True)
        with open(os.path.join(ROOT, "sketch", "sketch.ino")) as f:
            text = f.read()
        self.assertIn("#define QH_VERSION 5", text)
        self.assertIn("#define NPIN 25", text)
        self.assertIn('Bridge.provide_safe("q_info", q_info);', text)
        self.assertNotIn("25..49", text, "the bottom connector is gone")

    def test_master_info_banner(self):
        """q_info stores the text; loop() prints it on the Serial Monitor: when it arrives, when a
        key is typed there, and again every INFO_EVERY_MS (a monitor opened later is not seen)."""
        b = Board(build("master-run", flags=["-DMOCK_UNOQ", "-DINFO_EVERY_MS=1500UL"], master=True, run=True))
        try:
            b.send("~v")
            self.assertEqual(b.expect("v "), "v 5")
            text = ["QHome 2.1.0 (Home)", "http://192.168.1.50:7000", "MQTT 192.168.1.50:1883"]
            b.send("~I " + "|".join(text))                   # no monitor attached: stored, not printed
            self.assertEqual(b.expect("i "), "i %d" % len("\n".join(text)))
            time.sleep(0.4)
            self.assertTrue(b.lines.empty(), "nothing is printed while no monitor is attached")
            b.send("~m 1")                                   # monitor opened later: banner at the next repeat
            self.assertEqual(b.expect("=== QHome ===", 4), "=== QHome ===")
            self.assertEqual([b.expect("", 2) for _ in range(4)], text + ["(press any key to show this again)"])
            b.send("~k x")                                   # a key press asks for it again
            self.assertEqual(b.expect("=== QHome ===", 1.2), "=== QHome ===")
            self.assertEqual(b.expect("QHome "), text[0])
            b.expect("(press")
            b.send("~I QHome 2.1.0 (Home)|http://10.0.0.7:7000")       # the address changed: printed at once
            self.assertEqual(b.expect("i "), "i 39")
            self.assertEqual(b.expect("http://", 1.2), "http://10.0.0.7:7000")
            b.send("~I " + "x" * 300)                        # over-long text is cut, not overflowed
            self.assertEqual(b.expect("i "), "i 199")
        finally:
            b.close()

    def test_master_info_costs_no_rpc_storm(self):
        """While no Serial Monitor has ever been attached every `if (Monitor)` is one blocking RPC
        to the router. The sketch may ask once per INFO_EVERY_MS, not on every loop() pass."""
        b = Board(build("master-run", flags=["-DMOCK_UNOQ", "-DINFO_EVERY_MS=1500UL"], master=True, run=True))
        try:
            b.send("~I QHome 2.1.0 (Home)|http://192.168.1.50:7000")       # text waiting, nobody attached
            b.expect("i ")
            b.send("~c")
            n0 = int(b.expect("r ").split()[1])
            self.assertLessEqual(n0, 2, "Monitor.begin() asks once")
            time.sleep(3.3)                                  # about 1500 loop() passes
            b.send("~c")
            n = int(b.expect("r ").split()[1]) - n0
            self.assertGreaterEqual(n, 1, "it still asks now and then, or a monitor opened later sees nothing")
            self.assertLessEqual(n, 4, "one RPC per INFO_EVERY_MS at most, got %d in 3.3 s" % n)
            self.assertTrue(b.lines.empty(), "nothing is printed while no monitor is attached")
            b.send("~m 1")                                   # opened later: the waiting text is printed
            self.assertEqual(b.expect("=== QHome ===", 4), "=== QHome ===")
            b.expect("(press")
            b.send("~c")
            n2 = int(b.expect("r ").split()[1])
            b.send("~I QHome 2.1.0 (Home)|http://10.0.0.7:7000")           # attached: at once, no RPC
            self.assertEqual(b.expect("http://", 1.0), "http://10.0.0.7:7000")
            b.expect("(press")
            b.send("~k x")
            b.expect("=== QHome ===", 1.2)
            b.expect("(press")
            b.send("~c")
            self.assertEqual(b.expect("r "), "r %d" % n2, "the answer is cached once a monitor was attached")
        finally:
            b.close()

    def test_master_info_waits_for_linux(self):
        b = Board(build("master-run", flags=["-DMOCK_UNOQ", "-DINFO_EVERY_MS=1500UL"], master=True, run=True))
        try:
            b.send("~m 1")
            self.assertEqual(b.expect("QHome", 4), "QHome: waiting for the Linux side...")
        finally:
            b.close()

    def test_uno_over_serial(self):
        b = Board(build("uno"))
        try:
            boot = b.expect("B ").split()[1]
            b.send("H")
            self.assertEqual(b.expect("h ").split(), ["h", "1", "uno", boot])
            b.send("P")
            self.assertEqual(b.expect("p ").split()[1], boot)
            b.send("C 4 2 1000 20")                 # input with pull-up
            self.assertEqual(b.expect("c 4"), "c 4 2")
            self.assertEqual(b.expect("E 4"), "E 4 1")
            b.send("~d 4 0")                        # contact closes
            self.assertEqual(b.expect("E 4"), "E 4 0")
            b.send("~a 14 512")
            b.send("C 14 6 50 0")                   # analog input, report every 50 ms
            self.assertEqual(b.expect("c 14"), "c 14 6")
            self.assertEqual(b.expect("E 14"), "E 14 512")
            b.send("C 3 5 0 0")                     # PWM: 12-bit in, 8-bit timer out
            self.assertEqual(b.expect("c 3"), "c 3 5")
            b.send("A 3 4095")
            self.assertTrue(b.wrote("AW 3 255"))
            b.send("C 2 8 100 0")                   # pulse counter on an interrupt pin
            self.assertEqual(b.expect("c 2"), "c 2 8")
            b.send("~i 2 5")
            self.assertEqual(b.expect("E 2 5"), "E 2 5")
            b.send("C 8 4 0 0")
            b.expect("c 8 4")
            b.send("D 8 1")
            self.assertTrue(b.wrote("DW 8 1"))
            for line, reply in (("C 7 7 0 0", "c 7 -2"),     # no DAC on an UNO R3
                                ("C 0 4 0 0", "c 0 -1"),     # D0 carries the serial link
                                ("C 4 5 0 0", "c 4 -2"),     # D4 has no PWM
                                ("C 5 8 0 0", "c 5 -2"),     # D5 has no interrupt
                                ("C 3 3 0 0", "c 3 1")):     # no pull-down on AVR: plain input
                b.send(line)
                self.assertEqual(b.expect(reply[:4]), reply)
            b.send("\x01\x02 zzz")                  # noise and an over-long line are ignored
            b.send("M " + "7" * 104)
            b.send("R")
            self.assertEqual(b.expect("r "), "r 1")
            b.send("D 8 1")                         # released pins no longer accept writes
            time.sleep(0.2)
            self.assertEqual(b.writes.count("DW 8 1"), 1)
        finally:
            b.close()

    def test_mega_pin_map(self):
        b = Board(build("mega", flags=["-D__AVR_ATmega2560__"]))
        try:
            b.send("H")
            self.assertEqual(b.expect("h ").split()[2], "mega")
            for line, reply in (("C 54 6 100 0", "c 54 6"), ("C 44 5 0 0", "c 44 5"), ("C 18 8 100 0", "c 18 8"),
                                ("C 53 4 0 0", "c 53 4"), ("C 69 6 100 0", "c 69 6"), ("C 70 4 0 0", "c 70 -1")):
                b.send(line)
                self.assertEqual(b.expect(reply.rsplit(" ", 1)[0]), reply)
        finally:
            b.close()

    def test_nanor4(self):
        b = Board(build("nanor4", flags=FLAGS["nanor4"]))
        try:
            boot = b.expect("B ").split()[1]
            self.assertEqual(b.ask("H", "h ").split(), ["h", "1", "nanor4", boot])   # not "r4m": macro order
            for line, reply in (("C 20 4 0 0", "c 20 4"),    # A6 is a full GPIO on the Nano R4
                                ("C 21 6 50 0", "c 21 6"),   # A7 as analog input
                                ("C 14 7 0 0", "c 14 7"),    # DAC on A0
                                ("C 15 7 0 0", "c 15 -2"),   # ... and only there
                                ("C 0 4 0 0", "c 0 4"),      # native USB: D0/D1 are free on a USB link
                                ("C 3 5 0 0", "c 3 5"),
                                ("C 4 5 0 0", "c 4 -2"),     # PWM only on the six ~ pins
                                ("C 2 8 100 0", "c 2 8"),
                                ("C 5 8 100 0", "c 5 -2"),   # counters on D2, D3
                                ("C 22 4 0 0", "c 22 -1")):  # the LEDs and Qwiic are not offered
                self.assertEqual(b.ask(line), reply)
            b.send("A 14 2048")                              # 12-bit DAC, as on the UNO R4
            self.assertTrue(b.wrote("AW 14 2048"))
            b.send("A 3 4095")
            self.assertTrue(b.wrote("AW 3 4095"))
        finally:
            b.close()

    def test_nanor4_uart_and_i2c_links(self):
        b = Board(build("nanor4-uart", flags=FLAGS["nanor4"], config={"QL_LINK": "QL_UART"}))
        try:
            b.expect("B ")
            self.assertEqual(b.ask("C 0 4 0 0"), "c 0 -1")   # Serial1 on D0/D1
            self.assertEqual(b.ask("C 1 4 0 0"), "c 1 -1")
            self.assertEqual(b.ask("C 18 4 0 0"), "c 18 4")
        finally:
            b.close()
        b = Board(build("nanor4-i2c", flags=FLAGS["nanor4"] + ["-DMOCK_I2C"], config={"QL_LINK": "QL_I2C"}))
        try:
            b.expect("B ")
            self.assertEqual(b.ask("H", "h ").split()[2], "nanor4")
            self.assertEqual(b.ask("C 18 4 0 0"), "c 18 -1")  # A4 = SDA
            self.assertEqual(b.ask("C 19 4 0 0"), "c 19 -1")  # A5 = SCL
            self.assertEqual(b.ask("C 0 4 0 0"), "c 0 4")
        finally:
            b.close()

    def test_esp32_pin_rules(self):
        b = Board(build("esp32", flags=FLAGS["esp32"]))
        try:
            boot = b.expect("B ").split()[1]
            self.assertEqual(b.ask("H", "h ").split(), ["h", "1", "esp32", boot])
            self.assertEqual(b.ask("P", "p ").split()[1], boot)
            for line, reply in (("C 6 4 0 0", "c 6 -1"),     # flash pin: never touched
                                ("C 11 1 0 0", "c 11 -1"),
                                ("C 0 2 0 0", "c 0 -1"),     # BOOT button, not on the header
                                ("C 20 4 0 0", "c 20 -1"),   # does not exist
                                ("C 37 6 50 0", "c 37 -1"),
                                ("C 40 4 0 0", "c 40 -1"),
                                ("C 34 4 0 0", "c 34 -2"),   # input only
                                ("C 39 5 0 0", "c 39 -2"),
                                ("C 35 8 100 0", "c 35 -2"),
                                ("C 36 7 0 0", "c 36 -2"),
                                ("C 34 2 0 0", "c 34 1"),    # no pull-up there: plain input
                                ("C 35 3 0 0", "c 35 1"),    # no pull-down either
                                ("C 13 3 0 0", "c 13 3"),    # the ESP32 has real pull-downs
                                ("C 13 2 0 0", "c 13 2"),
                                ("C 25 7 0 0", "c 25 7"),    # DAC on 25 and 26
                                ("C 27 7 0 0", "c 27 -2"),
                                ("C 4 6 100 0", "c 4 -2"),   # ADC2 pin: no analog while Wi-Fi is on
                                ("C 3 1 0 0", "c 3 -1"),     # RX0/TX0 carry the USB link
                                ("C 1 4 0 0", "c 1 -1"),
                                ("C 16 4 0 0", "c 16 4"),    # RX2/TX2 are free on a USB link
                                ("C 14 8 100 0", "c 14 8")):
                self.assertEqual(b.ask(line), reply)
            self.assertTrue(b.wrote("PM 34 0") and b.wrote("PM 35 0"))
            self.assertTrue(b.wrote("PM 13 9"), "INPUT_PULLDOWN of the ESP32 core")
            b.send("A 25 4095")                              # 12 bit in, 8-bit DAC out
            self.assertTrue(b.wrote("DA 25 255"))
            b.send("C 25 0 0 0")                             # release switches the DAC off first
            self.assertEqual(b.expect("c 25"), "c 25 0")
            self.assertTrue(b.wrote("DD 25"))
            b.send("~i 14 3")                                # the interrupt number is the GPIO number
            self.assertEqual(b.expect("E 14 3"), "E 14 3")
            b.send("~a 34 1650")                             # calibrated millivolts -> 4095 = 3.3 V
            self.assertEqual(b.ask("C 34 6 50 0"), "c 34 6")
            self.assertEqual(b.expect("E 34"), "E 34 2047")
            b.send("~a 34 3400")                             # never above full scale
            self.assertEqual(b.expect("E 34 4"), "E 34 4095")
            b.send("C 2 5 0 0")
            b.expect("c 2 5")
            b.send("A 2 4095")                               # PWM stays 8 bit on ESP
            self.assertTrue(b.wrote("AW 2 255"))
            b.send("R")
            self.assertEqual(b.expect("r "), "r 1")
            pwm = [2, 4, 5, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 23, 25, 26, 27]
            for p in pwm[:16]:                               # 16 LEDC channels
                self.assertEqual(b.ask("C %d 5 0 0" % p), "c %d 5" % p)
            self.assertEqual(b.ask("C 27 5 0 0"), "c 27 -3")
            self.assertEqual(b.ask("C 2 5 0 0"), "c 2 5")    # setting up a PWM pin again is not a 17th
            self.assertEqual(b.ask("C 2 4 0 0"), "c 2 4")    # freeing one makes room
            self.assertEqual(b.ask("C 27 5 0 0"), "c 27 5")
            self.assertEqual(b.bad(), [], "a pin that crashes the chip was touched")
        finally:
            b.close()

    def test_esp32_core2_pwm(self):
        """esp32 core 2.x: analogWrite() keeps a pin's LEDC channel until reset and, up to 2.0.8,
        does not connect a pin again after pinMode(). The firmware owns the channels there, so a
        pin still dims after it was set up again and after any number of other pins had PWM."""
        for name, free, npwm in (("esp32", [2, 4, 5, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 23, 25, 26, 27, 32, 33], 16),
                                 ("esp32c3", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 21], 6)):
            b = Board(build(name + "-core2", flags=FLAGS[name] + ["-DESP_ARDUINO_VERSION_MAJOR=2"]))
            try:
                b.expect("B ")
                self.assertEqual(b.ask("H", "h ").split()[2], name)
                p = free[0]
                self.assertEqual(b.ask("C %d 5 0 0" % p), "c %d 5" % p)
                b.send("A %d 4095" % p)
                self.assertTrue(b.wrote("AW %d 255" % p), "%s: 8-bit duty reaches the pin" % name)
                self.assertEqual(b.ask("C %d 5 0 0" % p), "c %d 5" % p)        # every Save & apply does this
                b.send("A %d 2048" % p)
                self.assertTrue(b.wrote("AW %d 128" % p), "%s: the pin still dims after it was set up again" % name)
                self.assertEqual(b.ask("C %d 4 0 0" % p), "c %d 4" % p)        # now a plain output
                self.assertTrue(b.wrote("LD %d" % p), "the channel is taken off the pin")
                n = len(b.writes)
                b.send("D %d 1" % p)
                self.assertTrue(b.wrote("DW %d 1" % p))
                b.send("A %d 999" % p)                                         # not a PWM pin any more
                b.send("R")
                b.expect("r 1")
                # "LD" was already seen at the second set-up, so the switch-off write (duty 0) may still
                # be on its way when n is taken: only a non-zero duty would be a fault here
                self.assertFalse([w for w in b.writes[n:] if w.startswith("AW") and not w.endswith(" 0")])
                for p in free:                               # a dimmer moved from pin to pin: more pins
                    self.assertEqual(b.ask("C %d 5 0 0" % p), "c %d 5" % p)    # than the chip has channels
                    b.send("A %d 1600" % p)
                    self.assertTrue(b.wrote("AW %d 100" % p), "%s: pin %d has no PWM" % (name, p))
                    self.assertEqual(b.ask("C %d 0 0 0" % p), "c %d 0" % p)
                for p in free[:npwm]:                        # all channels at once
                    self.assertEqual(b.ask("C %d 5 0 0" % p), "c %d 5" % p)
                self.assertEqual(b.ask("C %d 5 0 0" % free[npwm]), "c %d -3" % free[npwm])
                self.assertEqual(b.ask("C %d 5 0 0" % free[0]), "c %d 5" % free[0], "setting one up again is not one more")
                b.send("R")                                  # release all: the channels really are free again
                b.expect("r 1")
                last = free[-1]
                self.assertEqual(b.ask("C %d 5 0 0" % last), "c %d 5" % last)
                b.send("A %d 4095" % last)
                self.assertTrue(b.wrote("AW %d 255" % last), "%s: PWM after the pool was used once" % name)
                self.assertEqual(b.bad(), [], "%s: analogWrite() or a dead LEDC channel was used" % name)
            finally:
                b.close()

    def test_esp32_uart_link(self):
        b = Board(build("esp32-uart", flags=FLAGS["esp32"], config={"QL_LINK": "QL_UART"}))
        try:
            b.expect("B ")
            self.assertTrue(b.wrote("SB 16 17"), "Serial2 started on RX2/TX2")
            self.assertEqual(b.ask("H", "h ").split()[2], "esp32")
            self.assertEqual(b.ask("C 16 1 0 0"), "c 16 -1")
            self.assertEqual(b.ask("C 17 4 0 0"), "c 17 -1")
            self.assertEqual(b.ask("C 3 1 0 0"), "c 3 1")    # RX0/TX0 are ordinary pins now
            self.assertEqual(b.ask("C 1 4 0 0"), "c 1 4")
        finally:
            b.close()

    def test_esp32c3_pin_rules(self):
        b = Board(build("esp32c3", flags=FLAGS["esp32c3"]))
        try:
            boot = b.expect("B ").split()[1]
            self.assertEqual(b.ask("H", "h ").split(), ["h", "1", "esp32c3", boot])
            for line, reply in (("C 18 1 0 0", "c 18 -1"),   # USB D-
                                ("C 19 4 0 0", "c 19 -1"),   # USB D+
                                ("C 11 4 0 0", "c 11 -1"),   # supply
                                ("C 12 4 0 0", "c 12 -1"),   # flash
                                ("C 17 1 0 0", "c 17 -1"),
                                ("C 22 4 0 0", "c 22 -1"),
                                ("C 5 6 100 0", "c 5 -2"),   # analog only on 0-4
                                ("C 5 7 0 0", "c 5 -2"),     # no DAC on the C3
                                ("C 20 1 0 0", "c 20 1"),    # native USB: RX/TX are free on a USB link
                                ("C 21 4 0 0", "c 21 4"),
                                ("C 9 2 0 0", "c 9 2"),
                                ("C 10 3 0 0", "c 10 3"),
                                ("C 8 8 100 0", "c 8 8")):
                self.assertEqual(b.ask(line), reply)
            b.send("~a 4 3300")
            self.assertEqual(b.ask("C 4 6 50 0"), "c 4 6")
            self.assertEqual(b.expect("E 4"), "E 4 4095")
            b.send("R")
            b.expect("r 1")
            for p in (0, 1, 2, 3, 5, 6):                     # 6 LEDC channels
                self.assertEqual(b.ask("C %d 5 0 0" % p), "c %d 5" % p)
            self.assertEqual(b.ask("C 7 5 0 0"), "c 7 -3")
            b.send("R")                                      # release all: the channels are free again
            b.expect("r 1")
            self.assertEqual(b.ask("C 7 5 0 0"), "c 7 5")
            self.assertEqual(b.bad(), [])
        finally:
            b.close()

    def test_esp32c3_uart_link(self):
        b = Board(build("esp32c3-uart", flags=FLAGS["esp32c3"], config={"QL_LINK": "QL_UART"}))
        try:
            b.expect("B ")
            self.assertTrue(b.wrote("SB 20 21"), "Serial0 started on GPIO20/21")
            self.assertEqual(b.ask("C 20 1 0 0"), "c 20 -1")
            self.assertEqual(b.ask("C 21 4 0 0"), "c 21 -1")
            self.assertEqual(b.ask("C 5 4 0 0"), "c 5 4")
        finally:
            b.close()
        # without "USB CDC On Boot", Serial is the UART on GPIO20/21: fine for UART, refused for USB
        plain = FLAGS["esp32c3"][:2]
        b = Board(build("esp32c3-uart-nocdc", flags=plain, config={"QL_LINK": "QL_UART"}))
        try:
            b.expect("B ")
            self.assertEqual(b.ask("C 20 1 0 0"), "c 20 -1")
        finally:
            b.close()
        build("esp32c3-usb-nocdc", flags=plain, expect_error="USB CDC On Boot must be Enabled")

    def test_esp8266_pin_rules(self):
        b = Board(build("esp8266", flags=FLAGS["esp8266"]))
        try:
            boot = b.expect("B ").split()[1]
            self.assertEqual(b.ask("H", "h ").split(), ["h", "1", "esp8266", boot])
            self.assertTrue(b.wrote("AR 255"), "8-bit PWM range on every core version")
            for line, reply in (("C 16 8 1000 0", "c 16 -2"),  # D0: no interrupt
                                ("C 16 5 0 0", "c 16 -2"),     # ... and no PWM
                                ("C 16 2 0 0", "c 16 1"),      # ... and no pull-up: plain input
                                ("C 16 4 0 0", "c 16 4"),      # but it can drive
                                ("C 4 3 0 0", "c 4 1"),        # no pull-down on the ESP8266
                                ("C 4 2 0 0", "c 4 2"),
                                ("C 17 4 0 0", "c 17 -2"),     # A0 is analog only
                                ("C 17 1 0 0", "c 17 -2"),
                                ("C 17 2 0 0", "c 17 -2"),
                                ("C 5 6 50 0", "c 5 -2"),      # one analog input: A0
                                ("C 5 7 0 0", "c 5 -2"),       # no DAC
                                ("C 9 4 0 0", "c 9 -1"),       # flash pin
                                ("C 6 1 0 0", "c 6 -1"),
                                ("C 18 4 0 0", "c 18 -1"),
                                ("C 1 4 0 0", "c 1 -1"),       # TX/RX carry the USB link
                                ("C 3 1 0 0", "c 3 -1"),
                                ("C 14 8 100 0", "c 14 8"),
                                ("C 12 5 0 0", "c 12 5")):
                self.assertEqual(b.ask(line), reply)
            b.send("A 12 4095")
            self.assertTrue(b.wrote("AW 12 255"))
            b.send("~a 17 1024")                             # the core can return 1024
            self.assertEqual(b.ask("C 17 6 50 0"), "c 17 6")
            self.assertEqual(b.expect("E 17"), "E 17 1023")
            b.send("~a 17 512")
            self.assertEqual(b.expect("E 17 5"), "E 17 512")
            self.assertEqual(b.ask("C 17 0 0 0"), "c 17 0")
            b.send("R")
            self.assertEqual(b.expect("r "), "r 1")
            self.assertEqual(b.bad(), [], "pinMode on A0 or a flash pin")
        finally:
            b.close()

    def test_esp8266_uart_link(self):
        b = Board(build("esp8266-uart", flags=FLAGS["esp8266"], config={"QL_LINK": "QL_UART"}))
        try:
            b.expect("B ")
            self.assertEqual(b.ask("C 1 4 0 0"), "c 1 -1")
            self.assertEqual(b.ask("C 3 1 0 0"), "c 3 -1")
        finally:
            b.close()

    def test_links_a_board_cannot_do(self):
        for name in ("esp32", "esp32c3", "esp8266"):
            build(name + "-i2c", flags=FLAGS[name], config={"QL_LINK": "QL_I2C"},
                  expect_error="I2C link is not supported on ESP boards")
        build("nanor4-wifi", flags=FLAGS["nanor4"], config={"QL_LINK": "QL_WIFI"},
              expect_error="This board has no Wi-Fi")
        build("uno-wifi", config={"QL_LINK": "QL_WIFI"}, expect_error="This board has no Wi-Fi")

    def test_i2c_slave(self):
        b = Board(build("uno-i2c", flags=["-DMOCK_I2C"], config={"QL_LINK": "QL_I2C"}))
        try:
            b.expect("B ")
            b.send("H")
            self.assertEqual(b.expect("h ").split()[2], "uno")
            b.send("C 0 4 0 0")                     # D0/D1 are free on I2C ...
            self.assertEqual(b.expect("c 0"), "c 0 4")
            b.send("C 18 4 0 0")                    # ... SDA is not
            self.assertEqual(b.expect("c 18"), "c 18 -1")
            b.send("C 14 6 20 0")                   # a burst of events must survive the 32-byte polling
            for _ in range(20):
                b.expect("E 14 ")
        finally:
            b.close()

    def _mqtt_rig(self, port, bid):
        got = queue.Queue()
        hub = MqttHub(lambda *a: None, lambda t, p: got.put((t, p)), lambda: None)
        hub.configure({"mode": "internal", "port": port}, "test", "test/status")
        hub.subscribe("qlink/%s/up" % bid)
        hub.subscribe("qlink/%s/status" % bid)

        def expect(leaf, prefix, timeout=6):
            topic = "qlink/%s/%s" % (bid, leaf)
            end = time.time() + timeout
            seen = []
            while time.time() < end:
                try:
                    t, p = got.get(timeout=0.05)
                except queue.Empty:
                    continue
                seen.append((t, p))
                if t == topic and p.startswith(prefix):
                    return p
            raise AssertionError("expected %s %r, got %r" % (topic, prefix, seen))
        return hub, expect

    def test_r4_wifi_over_mqtt(self):
        port = 18941
        hub, expect = self._mqtt_rig(port, "kitchen")
        b = Board(build("r4w", flags=["-DARDUINO_UNOR4_WIFI"], config={
            "QL_LINK": "QL_WIFI", "QL_MASTER_HOST": '"127.0.0.1"', "QL_MASTER_PORT": str(port), "QL_BOARD_ID": '"kitchen"'}))
        try:
            expect("status", "online")
            boot = expect("up", "B ").split()[1]
            hub.publish("qlink/kitchen/down", "H")
            self.assertEqual(expect("up", "h ").split(), ["h", "1", "r4w", boot])
            hub.publish("qlink/kitchen/down", "C 14 7 0 0")      # the R4 has a DAC on A0
            self.assertEqual(expect("up", "c 14"), "c 14 7")
            hub.publish("qlink/kitchen/down", "A 14 2048")
            self.assertTrue(b.wrote("AW 14 2048"))
            hub.publish("qlink/kitchen/down", "C 5 2 0 10")
            self.assertEqual(expect("up", "E 5"), "E 5 1")
            b.close()                                            # power cut: the broker publishes the last will
            expect("status", "offline")
        finally:
            b.close()

    def _esp_wifi(self, name, port, bid, pin, extra=()):
        """An ESP board on Wi-Fi: what the engine's discovery relies on (retained 'online', 'B',
        an unsolicited 'H' answered with the model), pins, last will, and joining Wi-Fi once."""
        hub, expect = self._mqtt_rig(port, bid)
        down = "qlink/%s/down" % bid
        b = Board(build(name + "-wifi", flags=FLAGS[name] + list(extra), config={
            "QL_LINK": "QL_WIFI", "QL_MASTER_HOST": '"127.0.0.1"', "QL_MASTER_PORT": str(port), "QL_BOARD_ID": '"%s"' % bid}))
        try:
            expect("status", "online")
            boot = expect("up", "B ").split()[1]
            hub.publish(down, "H")
            self.assertEqual(expect("up", "h ").split(), ["h", "1", name, boot])
            self.assertTrue(b.wrote("ND 1"), "TCP no-delay after connecting")
            hub.publish(down, "C %d 2 0 10" % pin)
            self.assertEqual(expect("up", "c %d" % pin), "c %d 2" % pin)
            self.assertEqual(expect("up", "E %d" % pin), "E %d 1" % pin)
            hub.publish(down, "C 1 4 0 0")                       # on Wi-Fi the TX pin is an ordinary pin
            self.assertEqual(expect("up", "c 1 "), "c 1 4")
            hub.publish(down, "D 1 1")
            self.assertTrue(b.wrote("DW 1 1"))
            self.assertEqual(b.writes.count("WB"), 1, "WiFi.begin() once: on ESP every call restarts the join")
            return hub, expect, b
        except BaseException:
            b.close()
            raise

    def test_esp32_wifi_over_mqtt(self):
        hub, expect, b = self._esp_wifi("esp32", 18942, "porch", 13)
        try:
            b.close()                                            # power cut: the broker publishes the last will
            expect("status", "offline")
        finally:
            b.close()

    def test_esp32c3_wifi_over_mqtt(self):
        hub, expect, b = self._esp_wifi("esp32c3", 18943, "shed", 9)
        try:
            b.close()
            expect("status", "offline")
        finally:
            b.close()

    def test_esp8266_wifi_rejoins(self):
        """Wi-Fi lost: the board must not call WiFi.begin() in a loop (on ESP that restarts the join
        every time), only after QL_WIFI_REJOIN_MS, and then start a fresh MQTT session."""
        hub, expect, b = self._esp_wifi("esp8266", 18944, "attic", 4, extra=["-DQL_WIFI_REJOIN_MS=2500UL"])
        try:
            b.send("~w 0")                                       # the access point goes away
            expect("status", "offline")                          # the board dropped its dead session
            time.sleep(1.5)
            self.assertEqual(b.writes.count("WB"), 1, "no new begin() while the core is still retrying")
            boot = expect("up", "B ", 10).split()[1]             # rejoined after the waiting time
            self.assertEqual(b.writes.count("WB"), 2)
            hub.publish("qlink/attic/status", "")                # (forget the retained state of this test)
            hub.publish("qlink/attic/down", "P")
            self.assertEqual(expect("up", "p ").split()[1], boot)
        finally:
            b.close()

    def test_whole_chain_usb_helper_to_firmware(self):
        """Door button on the simulated UNO Q -> block script -> relay on a (compiled) UNO R3
        reached through the USB helper, exactly as on an UNO Q running App Lab."""
        port = 18951
        cfg = demo_config()
        cfg["boards"] = cfg["boards"][:2]                        # main + 'garage' (UNO on USB)
        cfg["components"] = [c for c in cfg["components"] if c.get("board") != "lab"]
        cfg["scripts"]["workspace"]["blocks"]["blocks"] = cfg["scripts"]["workspace"]["blocks"]["blocks"][:1]
        os.environ["QHOME_REAL_LINKS"] = "1"
        master_fd, slave_fd = os.openpty()
        board = Board(build("uno"), stdin=master_fd, stdout=master_fd)
        helper = subprocess.Popen([sys.executable, os.path.join(ROOT, "tools", "qhome_usb_helper.py"), "--port", str(port),
                                   "--device", os.ttyname(slave_fd)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        rig = Rig(cfg, link_port=port)
        try:
            self.assertTrue(rig.wait(lambda: rig.engine.online.get("garage"), 10), "satellite found through the helper")
            self.assertEqual(rig.engine.hws["garage"].remote_model, "uno")
            self.assertTrue(board.wrote("PM 7 1", 3), "relay pin configured as an output")
            self.assertTrue(rig.wait(lambda: rig.state("pir") is False), "PIR reading arrived from the firmware")
            os.write(slave_fd, b"~d 4 1\n")                      # motion on the satellite's D4
            self.assertTrue(rig.wait(lambda: rig.state("pir") is True))
            rig.wait(lambda: rig.state("button") is False)
            rig.engine.sim_input("main", 2, 0)                   # press the button on the master
            self.assertTrue(board.wrote("DW 7 1", 3), "the script switched the relay on the other board")
            board.close()                                        # unplug
            self.assertTrue(rig.wait(lambda: not rig.engine.online.get("garage"), 12), "unplugging is noticed")
        finally:
            os.environ.pop("QHOME_REAL_LINKS", None)
            helper.kill()
            helper.wait()
            board.close()
            rig.close()
            os.close(master_fd)
            os.close(slave_fd)

    # ---- 2.1, both halves together: the engine's detection of new boards against the real firmware
    @staticmethod
    def _new_board_devices(bid, relay_pin, adc_pin):
        return [{"id": "pump", "type": "switch_output", "name": "Pump", "board": bid, "pin": relay_pin, "props": {}},
                {"id": "volts", "type": "analog_sensor", "name": "Volts", "board": bid, "pin": adc_pin,
                 "props": {"interval": 100, "avg": 1}}]

    def test_engine_finds_a_compiled_esp32_on_wifi_and_adds_it(self):
        """An ESP32 that joins the broker without being in the setup is listed as found with the
        model its firmware reports; added with that model it works at once (item 10 + item 6)."""
        port = 18945
        cfg = demo_config(with_scripts=False)
        cfg["boards"] = cfg["boards"][:1]
        cfg["components"] = [c for c in cfg["components"] if c.get("board") == "main"]
        cfg["mqtt"].update(mode="internal", port=port)
        holder, early = {}, []                                   # the broker calls back while the Rig is being built

        def deliver(*item):
            if "rig" not in holder:
                return early.append(item)
            e = holder["rig"].engine
            e.mqtt_message(*item) if item else e.mqtt_connected()
        os.environ["QHOME_REAL_LINKS"] = "1"
        rig = holder["rig"] = Rig(cfg, mqtt=MqttHub(lambda *a: None, deliver, deliver))
        for item in early:
            deliver(*item)
        e = rig.engine
        board = Board(build("esp32-wifi-found", flags=FLAGS["esp32"], config={
            "QL_LINK": "QL_WIFI", "QL_MASTER_HOST": '"127.0.0.1"', "QL_MASTER_PORT": str(port), "QL_BOARD_ID": '"porch"'}))
        try:
            self.assertTrue(rig.wait(lambda: (e.discovered.get("wifi:porch") or {}).get("model") == "esp32", 10),
                            "found, with the model key the firmware reports: %r" % (e.discovered,))
            d = e.snapshot()["discovered"][0]
            self.assertEqual((d["link"], d["id"], d["proto"]), ("wifi", "porch", 1))
            cfg = e.cfg.copy()
            cfg["boards"] = cfg["boards"] + [{"id": d["id"], "name": d["id"], "model": d["model"], "link": {"type": "wifi"}}]
            cfg["components"] = cfg["components"] + self._new_board_devices("porch", 4, 34)
            self.assertEqual(e.submit_config(cfg), [])
            self.assertTrue(rig.wait(lambda: e.online.get("porch"), 8), "online after Save")
            self.assertEqual(e.hws["porch"].remote_model, "esp32")
            self.assertEqual(e.discovered, {})
            self.assertTrue(board.wrote("PM 4 1", 3), "relay pin configured as an output")
            board.send("~a 34 1650")                             # 1.65 V on D34
            self.assertTrue(rig.wait(lambda: rig.state("volts") is not None and abs(rig.state("volts") - 1.65) < 0.02, 5),
                            "the master reads the calibrated ESP32 ADC in volts: %r" % (rig.state("volts"),))
            e.submit_command("pump", "on")
            self.assertTrue(board.wrote("DW 4 1", 3))
            self.assertEqual(board.bad(), [])
        finally:
            os.environ.pop("QHOME_REAL_LINKS", None)
            board.close()
            rig.close()

    def test_engine_finds_a_compiled_esp8266_on_usb_and_adds_it(self):
        """A NodeMCU plugged in behind the USB helper: asked who it is, listed as found, added
        with the port and model from the list, and its relay and A0 work."""
        port = 18952
        cfg = demo_config(with_scripts=False)
        cfg["boards"] = cfg["boards"][:1]
        cfg["components"] = [c for c in cfg["components"] if c.get("board") == "main"]
        os.environ["QHOME_REAL_LINKS"] = "1"
        master_fd, slave_fd = os.openpty()
        board = Board(build("esp8266", flags=FLAGS["esp8266"]), stdin=master_fd, stdout=master_fd)
        helper = subprocess.Popen([sys.executable, os.path.join(ROOT, "tools", "qhome_usb_helper.py"), "--port", str(port),
                                   "--device", os.ttyname(slave_fd)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        rig = Rig(cfg, link_port=port, probe=True)
        e = rig.engine
        try:
            def found():
                return [d for d in e.snapshot()["discovered"] if d["link"] == "usb" and d["port"].startswith("helper:")]
            self.assertTrue(rig.wait(lambda: found() and found()[0]["model"] == "esp8266", 12),
                            "found through the helper: %r" % (e.discovered,))
            d = found()[0]
            cfg = e.cfg.copy()
            cfg["boards"] = cfg["boards"] + [{"id": "shed", "name": "NodeMCU", "model": d["model"],
                                              "link": {"type": "usb", "port": d["port"]}}]
            cfg["components"] = cfg["components"] + self._new_board_devices("shed", 5, 17)
            self.assertEqual(e.submit_config(cfg), [])
            self.assertTrue(rig.wait(lambda: e.online.get("shed"), 10), "online after Save")
            self.assertEqual(e.hws["shed"].remote_model, "esp8266")
            self.assertEqual(found(), [])
            self.assertTrue(board.wrote("PM 5 1", 3), "D1 (GPIO5) configured as an output")
            os.write(slave_fd, b"~a 17 512\n")                   # half scale on A0
            self.assertTrue(rig.wait(lambda: rig.state("volts") is not None and abs(rig.state("volts") - 1.65) < 0.02, 5),
                            "A0 arrives in volts: %r" % (rig.state("volts"),))
            e.submit_command("pump", "on")
            self.assertTrue(board.wrote("DW 5 1", 3))
            self.assertEqual(board.bad(), [], "no call that would crash the real chip")
        finally:
            os.environ.pop("QHOME_REAL_LINKS", None)
            helper.kill()
            helper.wait()
            board.close()
            rig.close()
            os.close(master_fd)
            os.close(slave_fd)


if __name__ == "__main__":
    unittest.main()
