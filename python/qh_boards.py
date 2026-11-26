"""Board models: which pins exist on each supported board, what each pin can do, and where
each pin sits on the real board (the `board` drawing data used by the Boards & pins tab).

Pin ids are the Arduino pin numbers used in sketches (A0 on an UNO is 14, on a Mega 54; on
ESP boards the GPIO number). String ids are on-board extras (LEDs, LED matrix).

Capabilities:
  din   digital input          dout  digital output       pwm  PWM output
  adc   analog input           dac   true analog output   cnt  pulse counter (interrupt)
  rgb   on-board RGB LED       matrix on-board LED matrix
Notes are short codes; the web UI translates them (i18n key "note.<code>").

Drawing data (`board`): unit = one header pitch (2.54 mm). Origin = top-left corner of the
board outline, x to the right, y down. Every board is drawn with its USB connector on the
LEFT. `python python/qh_boards.py` runs a self-check of all tables.
"""

PWM_MAX = 4095  # QLink and the master firmware always use 12-bit duty / DAC values


def _p(pid, label, caps, notes=(), alt=None):
    d = {"id": pid, "label": label, "caps": list(caps), "notes": list(notes)}
    if alt:
        d["alt"] = alt
    return d


def _pad(label, same=None):
    d = {"pad": label}
    if same is not None:
        d["same"] = same
    return d


def _hdr(name, side, x, y, pins, cols=None):
    d = {"name": name, "side": side, "x": x, "y": y, "pins": list(pins)}
    if cols:
        d["cols"] = cols
    return d


def _part(typ, x, y, w, h, label=None, pin=None, **extra):
    d = {"type": typ, "x": x, "y": y, "w": w, "h": h}
    if label:
        d["label"] = label
    if pin is not None:
        d["pin"] = pin
    d.update(extra)
    return d


_POWER = [_pad("NC"), _pad("IOREF"), _pad("RST"), _pad("3V3"), _pad("5V"), _pad("GND"), _pad("GND"), _pad("VIN")]
_ICSP = [_pad("CIPO"), _pad("5V"), _pad("SCK"), _pad("COPI"), _pad("RST"), _pad("GND")]


def _uno_board(scl, sda, icsp, parts, power=None):
    """UNO footprint, 2.7 x 2.1 in. `scl` / `sda` are pin ids or pads."""
    return {"w": 27, "h": 21, "headers": [
        _hdr("DIGITAL", "top", 7.4, 1, [scl, sda, _pad("AREF"), _pad("GND"), 13, 12, 11, 10, 9, 8]),
        _hdr("DIGITAL", "top", 18, 1, [7, 6, 5, 4, 3, 2, 1, 0]),
        _hdr("POWER", "bottom", 11, 20, power or _POWER),
        _hdr("ANALOG", "bottom", 20, 20, [14, 15, 16, 17, 18, 19]),
        _hdr("ICSP", "inner", 25, 9, icsp, cols=2),
    ], "parts": parts}


def _unoq():
    pins = []
    doc_pwm = (3, 5, 6, 9, 10, 11)          # the six "~" pins from the official pinout
    core_pwm = (2, 7, 8, 12, 13)            # also wired to timers in the Zephyr core
    notes = {0: ["uart_rx"], 1: ["uart_tx"], 3: ["no5v"], 4: ["can_tx"], 5: ["can_rx"],
             10: ["spi_ss"], 11: ["spi_mosi"], 12: ["spi_miso"], 13: ["spi_sck"]}
    for d in range(14):
        caps = ["din", "dout", "cnt"]
        n = list(notes.get(d, []))
        if d in doc_pwm:
            caps.append("pwm")
        elif d in core_pwm:
            caps.append("pwm")
            n.append("pwm_core")
        pins.append(_p(d, "D%d" % d, caps, n))
    for a in range(6):
        caps = ["adc", "din", "dout", "cnt"] + (["dac"] if a < 2 else [])
        n = ["no5v"] if a < 2 else ["ain3v3"]
        pins.append(_p(14 + a, "A%d" % a, caps, n))
    pins.append(_p(20, "SDA", ["din", "dout", "cnt", "pwm"], ["i2c_sda", "pwm_core"]))
    pins.append(_p(21, "SCL", ["din", "dout", "cnt", "pwm"], ["i2c_scl", "pwm_core"]))
    for pid, lab in ((22, "CIPO"), (23, "COPI"), (24, "SCK")):
        pins.append(_p(pid, lab, ["din", "dout", "cnt"], ["jspi"]))
    pins.append(_p("LED1", "LED1", ["rgb"], ["led_linux"]))
    pins.append(_p("LED2", "LED2", ["rgb"], ["led_linux", "led_status"]))
    pins.append(_p("LED3", "LED3", ["rgb"], ["led_mcu"]))
    pins.append(_p("LED4", "LED4", ["rgb"], ["led_mcu"]))
    pins.append(_p("MATRIX", "Matrix", ["matrix"], ["matrix_13x8"]))
    board = _uno_board(21, 20, [22, _pad("3V3"), 24, 23, _pad("RST"), _pad("GND")], [
        _part("usb", -0.4, 4.2, 3.6, 3.4, "USB-C"),
        _part("btn", 2.2, 0.6, 1.6, 1.6, "PWR"),
        _part("module", 4.8, 6.4, 7.4, 7.4, "QRB2210"),
        _part("matrix", 13.6, 6.6, 9.6, 6.0, pin="MATRIX", cols=13, rows=8),
        _part("rgb", 4.8, 16.2, 1.3, 1.3, pin="LED1"),
        _part("rgb", 6.6, 16.2, 1.3, 1.3, pin="LED2"),
        _part("rgb", 8.4, 16.2, 1.3, 1.3, pin="LED3"),
        _part("rgb", 10.2, 16.2, 1.3, 1.3, pin="LED4"),
        _part("conn", 23.6, 14.4, 2.8, 1.9, "Qwiic"),
    ])
    return {
        "label": "Arduino UNO Q", "adc_max": 16383, "vref": 3.3, "logic": 3.3,
        "pins": pins, "links": ["local", "wifi"], "serial_pins": [0, 1], "uart_pins": [0, 1],
        "i2c_pins": [20, 21], "usb_shares_uart": False,
        "layout": [["digital", list(range(14)) + [20, 21]], ["analog", list(range(14, 20))],
                   ["onboard", ["LED1", "LED2", "LED3", "LED4", "MATRIX"]],
                   ["jspi", [22, 23, 24]]],
        "board": board,
    }


def _classic(label, ndig, nana, pwm, ints, i2c, adc_max=1023, vref=5.0, ain_only=(), dac=(),
             links=("usb", "uart", "i2c"), usb_shares_uart=True, led=13, board=None):
    pins = []
    for d in range(ndig):
        caps = ["din", "dout"]
        n = []
        if d in pwm:
            caps.append("pwm")
        if d in ints:
            caps.append("cnt")
        if d in (0, 1):
            n.append("uart_rx" if d == 0 else "uart_tx")
        if d == led:
            n.append("led_builtin")
        if d in i2c:
            n.append("i2c_sda" if d == i2c[0] else "i2c_scl")
        pins.append(_p(d, "D%d" % d, caps, n))
    for a in range(nana):
        pid = ndig + a
        if a in ain_only:
            caps, n = ["adc"], ["ain_only"]
        else:
            caps, n = ["adc", "din", "dout"], []
        if a in dac:
            caps.append("dac")
        if pid in i2c:
            n.append("i2c_sda" if pid == i2c[0] else "i2c_scl")
        pins.append(_p(pid, "A%d" % a, caps, n))
    return {
        "label": label, "adc_max": adc_max, "vref": vref, "logic": 5.0, "pins": pins,
        "links": list(links), "serial_pins": [0, 1], "uart_pins": [0, 1], "i2c_pins": list(i2c),
        "usb_shares_uart": usb_shares_uart,
        "layout": [["digital", list(range(ndig))], ["analog", list(range(ndig, ndig + nana))]],
        "board": board,
    }


def _gpio(label, rows, adc_max, links, serial_pins, i2c_pins, usb_shares_uart, uart_pins=None,
          board=None):
    """Boards with sparse GPIO numbering (ESP). rows: (gpio, label, "caps", [notes], alt)."""
    pins = [_p(g, lab, caps.split(), notes, alt) for g, lab, caps, notes, alt in rows]
    return {
        "label": label, "adc_max": adc_max, "vref": 3.3, "logic": 3.3, "pins": pins,
        "links": list(links), "serial_pins": list(serial_pins),
        "uart_pins": list(uart_pins or serial_pins), "i2c_pins": list(i2c_pins),
        "usb_shares_uart": usb_shares_uart,
        "layout": [["gpio", [r[0] for r in rows]]],
        "board": board,
    }


# ---------------------------------------------------------------- drawings
_SCL_PAD, _SDA_PAD = _pad("SCL", 19), _pad("SDA", 18)

_UNO_BOARD = _uno_board(_SCL_PAD, _SDA_PAD, _ICSP, [
    _part("usb", -2.5, 3.2, 6.3, 4.7, "USB-B"),
    _part("jack", -0.7, 13.6, 5.5, 3.6, "7-12 V"),
    _part("btn", 2.2, 0.6, 1.6, 1.6, "RESET"),
    _part("chip", 12.4, 13.4, 13.8, 3.4, "ATmega328P"),
])
_R4_POWER = [_pad("BOOT")] + _POWER[1:]
_R4M_BOARD = _uno_board(_SCL_PAD, _SDA_PAD, _ICSP, [
    _part("usb", -0.4, 4.2, 3.6, 3.4, "USB-C"),
    _part("jack", -0.7, 13.6, 5.5, 3.6, "6-24 V"),
    _part("btn", 2.2, 0.6, 1.6, 1.6, "RESET"),
    _part("chip", 13.0, 8.4, 4.6, 4.6, "RA4M1"),
], power=_R4_POWER)
_R4W_BOARD = _uno_board(_SCL_PAD, _SDA_PAD, _ICSP, [
    _part("usb", -0.4, 4.2, 3.6, 3.4, "USB-C"),
    _part("jack", -0.7, 13.6, 5.5, 3.6, "6-24 V"),
    _part("btn", 2.2, 0.6, 1.6, 1.6, "RESET"),
    _part("module", 4.2, 8.4, 4.4, 5.2, "ESP32-S3"),
    _part("chip", 9.4, 13.6, 3.6, 3.6, "RA4M1"),
    _part("matrix", 13.6, 6.6, 9.2, 6.2, cols=12, rows=8),
    _part("conn", 23.6, 14.4, 2.8, 1.9, "Qwiic"),
], power=_R4_POWER)

_MEGA_END = [_pad("5V"), _pad("5V")] + list(range(22, 54)) + [_pad("GND"), _pad("GND")]
_MEGA_BOARD = {"w": 40, "h": 21, "headers": [
    _hdr("DIGITAL", "top", 7.4, 1, [_pad("SCL", 21), _pad("SDA", 20), _pad("AREF"), _pad("GND"),
                                    13, 12, 11, 10, 9, 8]),
    _hdr("PWM", "top", 18, 1, [7, 6, 5, 4, 3, 2, 1, 0]),
    _hdr("COMMUNICATION", "top", 27, 1, [14, 15, 16, 17, 18, 19, 20, 21]),
    _hdr("POWER", "bottom", 11, 20, _POWER),
    _hdr("ANALOG", "bottom", 20, 20, list(range(54, 62))),
    _hdr("ANALOG", "bottom", 29, 20, list(range(62, 70))),
    _hdr("DIGITAL", "right", 37, 1.5, _MEGA_END, cols=2),
    _hdr("ICSP", "inner", 25.5, 9, _ICSP, cols=2),
], "parts": [
    _part("usb", -2.5, 3.2, 6.3, 4.7, "USB-B"),
    _part("jack", -0.7, 13.6, 5.5, 3.6, "7-12 V"),
    _part("btn", 2.2, 0.6, 1.6, 1.6, "RESET"),
    _part("chip", 17.4, 8.0, 5.6, 5.6, "ATmega2560"),
]}

_NANO_TOP = [12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, _pad("GND"), _pad("RST"), 0, 1]
_NANO_BOARD = {"w": 17, "h": 7, "headers": [
    _hdr("TOP", "top", 1.5, 0.5, _NANO_TOP),
    _hdr("BOTTOM", "bottom", 1.5, 6.5, [13, _pad("3V3"), _pad("AREF"), 14, 15, 16, 17, 18, 19, 20, 21,
                                        _pad("5V"), _pad("RST"), _pad("GND"), _pad("VIN")]),
], "parts": [
    _part("usb", -0.8, 2.0, 3.4, 3.0, "Mini-USB"),
    _part("chip", 6.6, 2.2, 2.6, 2.6, "ATmega328"),
    _part("btn", 10.4, 2.8, 1.4, 1.4, "RESET"),
    _part("conn", 13.2, 2.2, 2.6, 2.6, "ICSP"),
]}
_NANOR4_BOARD = {"w": 17, "h": 7, "headers": [
    _hdr("TOP", "top", 1.5, 0.5, _NANO_TOP),
    _hdr("BOTTOM", "bottom", 1.5, 6.5, [13, _pad("3V3"), _pad("BOOT"), 14, 15, 16, 17, 18, 19, 20, 21,
                                        _pad("5V"), _pad("VBATT"), _pad("GND"), _pad("VIN")]),
], "parts": [
    _part("usb", -0.5, 2.0, 3.0, 3.0, "USB-C"),
    _part("chip", 6.4, 2.0, 3.0, 3.0, "RA4M1"),
    _part("btn", 10.4, 2.8, 1.4, 1.4, "RESET"),
    _part("led", 12.2, 3.0, 1.0, 1.0, "RGB"),
    _part("conn", 13.8, 2.3, 2.6, 2.4, "Qwiic"),
]}

_ESP32_BOARD = {"w": 20, "h": 11, "headers": [
    _hdr("LEFT", "top", 3, 0.5, [_pad("VIN"), _pad("GND"), 13, 12, 14, 27, 26, 25, 33, 32, 35, 34, 39, 36,
                                 _pad("EN")]),
    _hdr("RIGHT", "bottom", 3, 10.5, [_pad("3V3"), _pad("GND"), 15, 2, 4, 16, 17, 5, 18, 19, 21, 3, 1, 22, 23]),
], "parts": [
    _part("usb", -0.5, 4.0, 3.0, 3.0, "Micro-USB"),
    _part("btn", 0.8, 1.7, 1.4, 1.4, "EN"),
    _part("btn", 0.8, 7.9, 1.4, 1.4, "BOOT"),
    _part("led", 5.4, 2.4, 1.0, 1.0, "LED"),
    _part("module", 8.6, 1.8, 11.0, 7.4, "ESP32-WROOM-32"),
]}
_ESP32C3_BOARD = {"w": 9, "h": 7, "headers": [
    _hdr("TOP", "top", 1, 0.5, [_pad("5V"), _pad("GND"), _pad("3V3"), 4, 3, 2, 1, 0]),
    _hdr("BOTTOM", "bottom", 1, 6.5, [5, 6, 7, 8, 9, 10, 20, 21]),
], "parts": [
    _part("usb", -0.6, 2.0, 3.0, 3.0, "USB-C"),
    _part("btn", 3.0, 1.5, 1.2, 1.2, "RST"),
    _part("btn", 3.0, 4.3, 1.2, 1.2, "BOOT"),
    _part("chip", 4.8, 2.2, 2.6, 2.6, "ESP32-C3"),
    _part("led", 7.8, 1.6, 0.8, 0.8, "LED"),
]}
_ESP8266_BOARD = {"w": 19, "h": 10, "headers": [
    _hdr("LEFT", "top", 2, 0.5, [_pad("VIN"), _pad("GND"), _pad("RST"), _pad("EN"), _pad("3V3"), _pad("GND"),
                                 _pad("CLK"), _pad("SD0"), _pad("CMD"), _pad("SD1"), _pad("SD2"), _pad("SD3"),
                                 _pad("RSV"), _pad("RSV"), 17]),
    _hdr("RIGHT", "bottom", 2, 9.5, [_pad("3V3"), _pad("GND"), 1, 3, 15, 13, 12, 14, _pad("GND"), _pad("3V3"),
                                     2, 0, 4, 5, 16]),
], "parts": [
    _part("usb", -0.5, 3.5, 3.0, 3.0, "Micro-USB"),
    _part("btn", 0.8, 1.5, 1.4, 1.4, "RST"),
    _part("btn", 0.8, 7.1, 1.4, 1.4, "FLASH"),
    _part("led", 7.0, 2.2, 1.0, 1.0, "LED"),
    _part("module", 8.8, 1.9, 9.8, 6.2, "ESP-12E"),
]}

# ---------------------------------------------------------------- ESP pin tables
_IO = "din dout pwm cnt"
_ESP32_ROWS = [
    (1, "TX0", "din dout", ["uart_tx", "boot_out"], "GPIO1"),
    (3, "RX0", "din dout", ["uart_rx"], "GPIO3"),
    (2, "D2", _IO, ["strap", "led_builtin"], None),
    (4, "D4", _IO, [], None),
    (5, "D5", _IO, ["strap", "boot_out", "spi_ss"], None),
    (12, "D12", _IO, ["boot_low"], None),
    (13, "D13", _IO, [], None),
    (14, "D14", _IO, ["boot_out"], None),
    (15, "D15", _IO, ["strap", "boot_out"], None),
    (16, "RX2", _IO, ["uart2_rx"], "GPIO16"),
    (17, "TX2", _IO, ["uart2_tx"], "GPIO17"),
    (18, "D18", _IO, ["spi_sck"], None),
    (19, "D19", _IO, ["spi_miso"], None),
    (21, "D21", _IO, ["i2c_sda"], None),
    (22, "D22", _IO, ["i2c_scl"], None),
    (23, "D23", _IO, ["spi_mosi"], None),
    (25, "D25", _IO + " dac", ["dac8"], None),
    (26, "D26", _IO + " dac", ["dac8"], None),
    (27, "D27", _IO, [], None),
    (32, "D32", _IO + " adc", [], None),
    (33, "D33", _IO + " adc", [], None),
    (34, "D34", "din adc", ["in_only"], None),
    (35, "D35", "din adc", ["in_only"], None),
    (36, "VP", "din adc", ["in_only"], "GPIO36"),
    (39, "VN", "din adc", ["in_only"], "GPIO39"),
]
_ESP32C3_ROWS = [
    (0, "IO0", _IO + " adc", ["adc_2v5"], None),
    (1, "IO1", _IO + " adc", ["adc_2v5"], None),
    (2, "IO2", _IO + " adc", ["strap", "adc_2v5"], None),
    (3, "IO3", _IO + " adc", ["adc_2v5"], None),
    (4, "IO4", _IO + " adc", ["adc_2v5"], None),
    (5, "IO5", _IO, [], None),
    (6, "IO6", _IO, [], None),
    (7, "IO7", _IO, [], None),
    (8, "IO8", _IO, ["strap", "led_builtin_low", "i2c_sda"], None),
    (9, "IO9", _IO, ["boot_btn", "i2c_scl"], None),
    (10, "IO10", _IO, [], None),
    (20, "RX", _IO, ["uart_rx"], "GPIO20"),
    (21, "TX", _IO, ["uart_tx", "boot_out"], "GPIO21"),
]
_ESP8266_ROWS = [
    (16, "D0", "din dout", ["no_pullup"], "GPIO16"),
    (5, "D1", _IO, ["i2c_scl"], "GPIO5"),
    (4, "D2", _IO, ["i2c_sda"], "GPIO4"),
    (0, "D3", _IO, ["boot_btn"], "GPIO0"),
    (2, "D4", _IO, ["strap", "led_builtin_low", "boot_out"], "GPIO2"),
    (14, "D5", _IO, ["spi_sck"], "GPIO14"),
    (12, "D6", _IO, ["spi_miso"], "GPIO12"),
    (13, "D7", _IO, ["spi_mosi"], "GPIO13"),
    (15, "D8", _IO, ["boot_low", "spi_ss"], "GPIO15"),
    (3, "RX", "din dout", ["uart_rx"], "GPIO3"),
    (1, "TX", "din dout", ["uart_tx", "boot_out"], "GPIO1"),
    (17, "A0", "adc", ["ain_only", "a0_3v3"], "ADC0"),
]

_AVR_PWM = (3, 5, 6, 9, 10, 11)
_WIFI3 = ("usb", "uart", "wifi")
MODELS = {
    "unoq": _unoq(),
    "uno": _classic("Arduino UNO R3", 14, 6, _AVR_PWM, (2, 3), (18, 19), board=_UNO_BOARD),
    "nano": _classic("Arduino Nano", 14, 8, _AVR_PWM, (2, 3), (18, 19), ain_only=(6, 7),
                     board=_NANO_BOARD),
    "mega": _classic("Arduino Mega 2560", 54, 16, tuple(range(2, 14)) + (44, 45, 46),
                     (2, 3, 18, 19, 20, 21), (20, 21), board=_MEGA_BOARD),
    "r4m": _classic("Arduino UNO R4 Minima", 14, 6, _AVR_PWM, (2, 3), (18, 19), adc_max=16383,
                    dac=(0,), usb_shares_uart=False, board=_R4M_BOARD),
    "r4w": _classic("Arduino UNO R4 WiFi", 14, 6, _AVR_PWM, (2, 3), (18, 19), adc_max=16383,
                    dac=(0,), usb_shares_uart=False, links=("usb", "uart", "i2c", "wifi"),
                    board=_R4W_BOARD),
    "nanor4": _classic("Arduino Nano R4", 14, 8, _AVR_PWM, (2, 3), (18, 19), adc_max=16383,
                       dac=(0,), usb_shares_uart=False, led=None, board=_NANOR4_BOARD),
    "esp32": _gpio("ESP32 DevKit V1", _ESP32_ROWS, 4095, _WIFI3, (3, 1), (21, 22), True,
                   uart_pins=(16, 17), board=_ESP32_BOARD),
    "esp32c3": _gpio("ESP32-C3 Super Mini", _ESP32C3_ROWS, 4095, _WIFI3, (20, 21), (8, 9), False,
                     board=_ESP32C3_BOARD),
    "esp8266": _gpio("ESP8266 NodeMCU", _ESP8266_ROWS, 1023, _WIFI3, (3, 1), (4, 5), True,
                     board=_ESP8266_BOARD),
}
for _m in MODELS.values():
    _m["pin_by_id"] = {p["id"]: p for p in _m["pins"]}

LINK_TYPES = ("local", "usb", "uart", "i2c", "wifi")


def model(name):
    return MODELS.get(name)


def reserved_pins(board, boards):
    """Pins a board cannot hand out because its link (or a link it hosts) uses them.

    Returns {pin_id: reason_code}.
    """
    m = MODELS.get(board.get("model"))
    if not m:
        return {}
    out = {}
    lt = (board.get("link") or {}).get("type")
    if lt == "uart":
        for p in m["uart_pins"]:
            out[p] = "link_serial"
    elif lt == "usb" and m.get("usb_shares_uart"):
        for p in m["serial_pins"]:
            out[p] = "link_serial"
    if lt == "i2c":
        for p in m["i2c_pins"]:
            out[p] = "link_i2c"
    if lt == "local":  # the master also hosts the wired links of the other boards
        for other in boards:
            ol = other.get("link") or {}
            if ol.get("type") == "uart":
                for p in m["uart_pins"]:
                    out[p] = "host_uart"
            if ol.get("type") == "i2c" and ol.get("bus", "wire") == "wire":
                for p in m["i2c_pins"]:
                    out[p] = "host_i2c"
    return out


def board_pin_ids(m):
    """Every clickable pin id of a model's drawing, in drawing order (used by tests)."""
    b = m["board"]
    ids = [e for hd in b["headers"] for e in hd["pins"] if not isinstance(e, dict)]
    return ids + [pt["pin"] for pt in b["parts"] if "pin" in pt]


def public_models():
    """Model table for the web UI (without the lookup helper dicts)."""
    return {k: {kk: vv for kk, vv in v.items() if kk != "pin_by_id"} for k, v in MODELS.items()}


# ---------------------------------------------------------------- self-check
if __name__ == "__main__":
    import json
    for name, m in MODELS.items():
        ids = [p["id"] for p in m["pins"]]
        assert len(ids) == len(set(ids)), name
        laid = [p for _, pins in m["layout"] for p in pins]
        assert sorted(map(str, laid)) == sorted(map(str, ids)), (name, "layout")
        drawn = board_pin_ids(m)
        assert len(drawn) == len(set(drawn)), (name, "drawn twice")
        assert sorted(map(str, drawn)) == sorted(map(str, ids)), (name, "drawing", set(map(str, ids)) ^ set(map(str, drawn)))
        b = m["board"]
        for hd in b["headers"]:
            n, cols = len(hd["pins"]), hd.get("cols") or len(hd["pins"])
            assert n % cols == 0, (name, hd["name"])
            x1, y1 = hd["x"] + cols - 1, hd["y"] + n // cols - 1
            assert 0 < hd["x"] and x1 < b["w"] and 0 < hd["y"] and y1 < b["h"], (name, hd["name"], x1, y1)
            assert hd["side"] in ("top", "bottom", "left", "right", "inner")
            for e in hd["pins"]:
                if isinstance(e, dict) and "same" in e:
                    assert e["same"] in m["pin_by_id"], (name, e)
        for pt in b["parts"]:
            assert -3 <= pt["x"] and pt["x"] + pt["w"] <= b["w"] + 0.01 and 0 <= pt["y"] and pt["y"] + pt["h"] <= b["h"], (name, pt)
        for k in ("serial_pins", "uart_pins", "i2c_pins"):
            assert all(p in m["pin_by_id"] for p in m[k]), (name, k)
        print("%-8s %-22s %2d pins  %s  board %sx%s  %d bytes" % (
            name, m["label"], len(ids), ",".join(m["links"]), b["w"], b["h"],
            len(json.dumps(m["board"]))))
    assert reserved_pins({"model": "esp32", "link": {"type": "uart"}}, []) == {16: "link_serial", 17: "link_serial"}
    assert reserved_pins({"model": "esp32", "link": {"type": "usb"}}, []) == {3: "link_serial", 1: "link_serial"}
    assert reserved_pins({"model": "esp32c3", "link": {"type": "usb"}}, []) == {}
    assert reserved_pins({"model": "esp32", "link": {"type": "wifi"}}, []) == {}
    print("ok, total /api/meta models size: %d bytes" % len(json.dumps(public_models())))
