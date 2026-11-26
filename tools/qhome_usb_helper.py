#!/usr/bin/env python3
"""QHome USB helper: gives QHome access to Arduino boards plugged in over USB.

Why this exists: Arduino App Lab runs the Python part of an app inside a container that
cannot see /dev/ttyACM* or /dev/ttyUSB*. This small program runs on the UNO Q itself
(outside App Lab), opens every USB serial board it finds and forwards it to QHome's
link port over TCP. QHome then lists the board as "helper:<name>".

Run it once to try:      python3 qhome_usb_helper.py
Keep it running at boot: see qhome-usb-helper.service next to this file.

Not needed when QHome runs directly on a PC (python python/main.py): there it opens the
serial ports itself. Standard library only, Linux and macOS.
"""
import argparse
import glob
import os
import select
import socket
import termios
import threading
import time

PATTERNS = ("/dev/serial/by-id/*", "/dev/ttyACM*", "/dev/ttyUSB*", "/dev/cu.usbmodem*", "/dev/cu.usbserial*")


def find_devices():
    """Return {real device path: friendly name}; by-id names survive re-plugging."""
    found = {}
    for pat in PATTERNS:
        for path in sorted(glob.glob(pat)):
            real = os.path.realpath(path)
            found.setdefault(real, os.path.basename(path))
    return found


def open_serial(path, baud):
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    a = termios.tcgetattr(fd)
    a[0] = a[1] = a[3] = 0
    a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    a[4] = a[5] = getattr(termios, "B%d" % baud)
    a[6][termios.VMIN] = 0
    a[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, a)
    return fd


def pump(path, name, host, port, baud, active):
    fd = sock = None
    try:
        fd = open_serial(path, baud)
        sock = socket.create_connection((host, port), timeout=5)
        sock.sendall(("@usb %s\n" % name).encode())
        sock.setblocking(False)
        print("forwarding %s (%s)" % (name, path), flush=True)
        while True:
            r, _, _ = select.select([fd, sock], [], [], 1.0)
            if fd in r:
                data = os.read(fd, 512)
                if not data:
                    raise OSError("board unplugged")
                sock.sendall(data)
            if sock in r:
                data = sock.recv(512)
                if not data:
                    raise OSError("QHome closed the link")
                while data:
                    data = data[os.write(fd, data):]
    except (OSError, termios.error) as e:
        print("%s: %s" % (name, e), flush=True)
    finally:
        if fd is not None:
            os.close(fd)
        if sock is not None:
            sock.close()
        time.sleep(2)
        active.discard(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--host", default="127.0.0.1", help="where QHome runs (default: this UNO Q)")
    ap.add_argument("--port", type=int, default=7001, help="QHome link port (default 7001)")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--device", action="append", help="only forward this device (repeatable)")
    args = ap.parse_args()
    active = set()
    print("QHome USB helper: forwarding USB boards to %s:%d" % (args.host, args.port), flush=True)
    while True:
        devices = {os.path.realpath(d): os.path.basename(d) for d in args.device} if args.device else find_devices()
        for path, name in devices.items():
            if path not in active and os.path.exists(path):
                active.add(path)
                threading.Thread(target=pump, args=(path, name, args.host, args.port, args.baud, active),
                                 daemon=True).start()
        time.sleep(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
