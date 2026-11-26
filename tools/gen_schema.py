#!/usr/bin/env python3
"""Writes schema/qhome-config.schema.json from the board and device tables in python/.

VS Code uses that schema (see .vscode/settings.json) to autocomplete and check
data/config.json and any *.qhome.json file, much like ESPHome's YAML checks.
Run again after changing qh_boards.py or the TYPES table:  python tools/gen_schema.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "python"))

import qh_boards  # noqa: E402
import qh_engine  # noqa: E402
import qh_tz  # noqa: E402
from qh_hw import RGB_BITS  # noqa: E402

ID = {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,31}$"}


def prop_schema(p):
    if p["type"] == "bool":
        s = {"type": "boolean"}
    elif p["type"] == "number":
        s = {"type": "number"}
        for k, j in (("min", "minimum"), ("max", "maximum")):
            if k in p:
                s[j] = p[k]
    elif p["type"] == "select":
        s = {"enum": p["options"]}
    else:
        s = {"type": "string"}
    s["default"] = p["default"]
    return s


def component_variants():
    out = []
    for name, t in qh_engine.TYPES.items():
        out.append({
            "if": {"properties": {"type": {"const": name}}, "required": ["type"]},
            "then": {"properties": {"props": {
                "type": "object", "additionalProperties": False,
                "properties": {p["key"]: prop_schema(p) for p in t["props"]}}}}})
    return out


def link_schema():
    return {"type": "object", "required": ["type"], "properties": {
        "type": {"enum": list(qh_boards.LINK_TYPES), "description": "How the master reaches this board."},
        "port": {"type": "string", "description": "usb: serial port, \"auto\", \"helper:<name>\" or \"tcp://host:port\"."},
        "baud": {"enum": [9600, 19200, 38400, 57600, 115200]},
        "bus": {"enum": ["wire", "qwiic"], "description": "i2c: SDA/SCL header or the Qwiic connector of the master."},
        "address": {"type": "integer", "minimum": 8, "maximum": 119},
        "poll_ms": {"type": "integer", "minimum": 10, "maximum": 1000}}}


def build():
    pins = sorted({p["id"] for m in qh_boards.MODELS.values() for p in m["pins"] if isinstance(p["id"], str)})
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "QHome setup",
        "description": "Boards, devices and block scripts of a QHome installation (version %s)." % qh_engine.VERSION,
        "type": "object", "required": ["device", "boards", "components"],
        "properties": {
            "version": {"const": 2},
            "device": {"type": "object", "properties": {
                "name": {"type": "string"}, "node": {"type": "string", "pattern": "^[a-z0-9_-]{1,32}$",
                                                     "description": "MQTT topic prefix; in node mode also the board id on the master."},
                "tz": {"description": "Time zone: an IANA name such as Europe/Istanbul, or a fixed offset such as UTC+3 or UTC+5:30.",
                       "anyOf": [{"enum": qh_tz.fixed_names()},
                                 {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_+-]*(/[A-Za-z0-9_+-]+){1,2}$"}],
                       "default": qh_tz.DEFAULT},
                "tz_offset": {"type": "number", "minimum": -12, "maximum": 14,
                              "description": "Old setting (hours from UTC). Replaced by tz when the file is loaded."},
                "web_password": {"type": "string"},
                "role": {"enum": ["master", "node"]}, "master_host": {"type": "string"},
                "master_port": {"type": "integer"}, "master_user": {"type": "string"}, "master_pass": {"type": "string"}}},
            "mqtt": {"type": "object", "properties": {
                "mode": {"enum": ["internal", "external", "off"]}, "port": {"type": "integer"},
                "username": {"type": "string"}, "password": {"type": "string"}, "host": {"type": "string"},
                "ext_port": {"type": "integer"}, "discovery": {"type": "boolean"}, "prefix": {"type": "string"}}},
            "boards": {"type": "array", "items": {
                "type": "object", "required": ["id", "model", "link"], "properties": {
                    "id": ID, "name": {"type": "string"},
                    "model": {"enum": list(qh_boards.MODELS),
                              "description": ", ".join("%s = %s" % (k, v["label"]) for k, v in qh_boards.MODELS.items())},
                    "link": link_schema()}}},
            "components": {"type": "array", "items": {
                "type": "object", "required": ["id", "type"], "properties": {
                    "id": ID, "name": {"type": "string"},
                    "type": {"enum": list(qh_engine.TYPES)},
                    "board": {"type": ["string", "null"], "description": "Board id; null for virtual switches."},
                    "pin": {"description": "Arduino pin number (A0 is 14 on UNO boards, 54 on a Mega) or an on-board name.",
                            "anyOf": [{"type": "integer", "minimum": 0, "maximum": 69}, {"enum": pins}, {"type": "null"}]},
                    "props": {"type": "object"}},
                "allOf": component_variants()}},
            "scripts": {"type": "object", "properties": {
                "workspace": {"type": "object", "description": "Blockly workspace saved by the Blocks tab. Edit it there."}}},
        },
        "definitions": {"rgb_colors": {"enum": list(RGB_BITS)}},
    }
    return schema


def main():
    schema = build()
    path = os.path.join(ROOT, "schema", "qhome-config.schema.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2)
        f.write("\n")
    print("wrote", os.path.relpath(path, ROOT))


if __name__ == "__main__":
    main()
