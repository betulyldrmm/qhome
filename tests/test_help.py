"""Checks of the help content (assets/help.js) and of the files generated from it (docs/).

Standard library only; needs no running QHome. The page ids, anchors and hint keys below are the
ones assets/app.js links to: change them here and there together.

    python -m unittest tests/test_help.py
"""
import importlib.util
import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELP_JS = os.path.join(ROOT, "assets", "help.js")
PREFIX = "window.QHELP = "

# page id -> (roles, English title, Turkish title, anchors the UI or other docs link to)
PAGES = [
    ("start", ["master", "node"], "Getting started", "Başlarken", ["install", "first-device", "simulator"]),
    ("pins", ["master"], "Pins and devices", "Pinler ve cihazlar", ["inputs", "analog", "counter"]),
    ("wiring", ["master"], "Connecting boards", "Kartları bağlama", ["usb", "uart", "i2c", "wifi"]),
    ("boards", ["master"], "Board models", "Kart modelleri",
     ["unoq", "avr", "r4", "esp32", "esp32c3", "esp8266", "found"]),
    ("blocks", ["master"], "Blocks cookbook", "Blok tarifleri", ["time", "recipes"]),
    ("matrix", ["master"], "LED matrix", "LED matris", ["modes", "override"]),
    ("mqtt", ["master"], "MQTT and Home Assistant", "MQTT ve Home Assistant", ["ha", "topics"]),
    ("faq", ["master", "node"], "Troubleshooting", "Sorun giderme", ["password", "address", "timezone"]),
]
PLACEHOLDERS = {"url", "host", "node", "web_port", "mqtt_port", "link_port", "version"}
GEN_NAMES = {"boards", "links", "types", "icons", "anims"}
# Fields each block type must have, and the ones it may have.
SHAPES = {
    "h": ({"t", "id", "text"}, set()), "p": ({"t", "text"}, set()),
    "ul": ({"t", "items"}, set()), "ol": ({"t", "items"}, set()),
    "code": ({"t", "text"}, set()), "note": ({"t", "text"}, {"warn"}),
    "table": ({"t", "head", "rows"}, set()), "gen": ({"t", "name"}, set()),
}
# Where assets/app.js asks for a hint. prop.<key> and prop.<key>.<type> use the names of the
# device table (qh_engine.TYPES); they are repeated here so this test needs no other file.
FIXED_HINTS = {"pin.id", "board.id", "board.link", "link.port", "link.addr", "set.node", "set.pw", "set.tz",
               "set.role", "set.mqtt", "mqtt.prefix", "set.usb", "found"}
PROPS = {
    "binary_input": {"pull", "invert", "debounce", "device_class"},
    "analog_sensor": {"interval", "calib", "in_min", "in_max", "out_min", "out_max", "unit", "decimals",
                      "avg", "delta", "device_class"},
    "pulse_counter": {"interval", "mode", "multiplier", "unit", "decimals", "device_class"},
    "switch_output": {"invert", "restore", "ha_as"},
    "pwm_output": {"invert", "min_pct", "max_pct", "restore"},
    "dac_output": {"restore"}, "rgb_led": {"restore"},
    "led_matrix": {"brightness", "mode", "startup_text", "source", "bar_style", "bar_min", "bar_max",
                   "graph_secs", "anim", "speed", "icon", "clock_12h", "scroll_ms"},
    "virtual_switch": {"restore"},
}
ANCHOR_RE = re.compile(r"^[a-z][a-z0-9-]*$")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
HELP_LINK_RE = re.compile(r"^#([a-z][a-z0-9-]*)(?:/([a-z][a-z0-9-]*))?$")
PLACEHOLDER_RE = re.compile(r"\{\{(.*?)\}\}")


def no_duplicates(pairs):
    keys = [k for k, _ in pairs]
    dup = sorted({k for k in keys if keys.count(k) > 1})
    if dup:
        raise ValueError("duplicate keys: %s" % ", ".join(dup))
    return dict(pairs)


def load_gen_docs():
    spec = importlib.util.spec_from_file_location("gen_docs", os.path.join(ROOT, "tools", "gen_docs.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class HelpContent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(HELP_JS, encoding="utf-8") as f:
            cls.src = f.read()
        lines = cls.src.split("\n")
        n = 0
        while n < len(lines) and lines[n].startswith("//"):
            n += 1
        cls.body = "\n".join(lines[n:]).strip()
        cls.data = json.loads(cls.body[len(PREFIX):-1], object_pairs_hook=no_duplicates)
        cls.pages = {pg["id"]: pg for pg in cls.data["pages"]}
        cls.anchors = {pid: {bl["id"] for bl in pg["blocks"] if bl.get("t") == "h"}
                       for pid, pg in cls.pages.items()}

    # ---- helpers
    def texts(self):
        """Every text value with a name that says where it is: (where, value, kind)."""
        for pg in self.data["pages"]:
            yield "%s title" % pg["id"], pg["title"], "plain"
            for i, bl in enumerate(pg["blocks"]):
                where = "%s block %d (%s)" % (pg["id"], i, bl.get("t"))
                kind = "code" if bl.get("t") == "code" else "rich"
                if "text" in bl:
                    yield where, bl["text"], kind
                for x in bl.get("items", []):
                    yield where, x, kind
                for x in bl.get("head", []):
                    yield where, x, kind
                for row in bl.get("rows", []):
                    for x in row:
                        yield where, x, kind
        for key, hint in self.data["hints"].items():
            yield "hint %s" % key, hint.get("text"), "rich"

    @staticmethod
    def variants(value):
        return [("en+tr", value)] if isinstance(value, str) else sorted(value.items())

    def link_ok(self, target):
        m = HELP_LINK_RE.match(target)
        return bool(m and m.group(1) in self.pages and (m.group(2) is None or m.group(2) in self.anchors[m.group(1)]))

    # ---- the file
    def test_file_is_comments_then_strict_json(self):
        self.assertTrue(self.body.startswith(PREFIX), "after the // lines the file starts with '%s'" % PREFIX)
        self.assertTrue(self.body.endswith(";"), "the file ends with ';'")
        self.assertEqual(set(self.data), {"version", "pages", "hints"})
        self.assertEqual(self.data["version"], 1)
        self.assertNotIn("\t", self.src)

    def test_pages_ids_roles_titles_anchors(self):
        self.assertEqual([pg["id"] for pg in self.data["pages"]], [p[0] for p in PAGES])
        for pid, roles, en, tr, anchors in PAGES:
            pg = self.pages[pid]
            self.assertEqual(set(pg), {"id", "roles", "title", "blocks"}, pid)
            self.assertEqual(pg["roles"], roles, pid)
            self.assertEqual(pg["title"], {"en": en, "tr": tr}, pid)
            for a in anchors:
                self.assertIn(a, self.anchors[pid], "%s needs the heading #%s" % (pid, a))
            self.assertTrue(pg["blocks"], pid)

    def test_block_shapes(self):
        for pid, pg in self.pages.items():
            seen = set()
            for i, bl in enumerate(pg["blocks"]):
                where = "%s block %d" % (pid, i)
                self.assertIsInstance(bl, dict, where)
                self.assertIn(bl.get("t"), SHAPES, where)
                need, may = SHAPES[bl["t"]]
                self.assertTrue(need <= set(bl) <= need | may, "%s (%s): fields %s" % (where, bl["t"], sorted(bl)))
                if bl["t"] == "h":
                    self.assertRegex(bl["id"], ANCHOR_RE, where)
                    self.assertNotIn(bl["id"], seen, "%s: anchor used twice" % where)
                    seen.add(bl["id"])
                elif bl["t"] in ("ul", "ol"):
                    self.assertIsInstance(bl["items"], list, where)
                    self.assertTrue(bl["items"], where)
                elif bl["t"] == "note":
                    self.assertIs(bl.get("warn", True), True, where)
                elif bl["t"] == "table":
                    self.assertTrue(bl["head"] and bl["rows"], where)
                    for row in bl["rows"]:
                        self.assertEqual(len(row), len(bl["head"]), "%s: a row is not as long as the head" % where)
                elif bl["t"] == "gen":
                    self.assertIn(bl["name"], GEN_NAMES, where)

    def test_texts_are_strings_or_both_languages(self):
        for where, value, _kind in self.texts():
            if isinstance(value, str):
                self.assertTrue(value.strip(), where)
                continue
            self.assertIsInstance(value, dict, where)
            self.assertEqual(set(value), {"en", "tr"}, where)
            for lang in ("en", "tr"):
                self.assertIsInstance(value[lang], str, where)
                self.assertTrue(value[lang].strip(), "%s: empty %s text" % (where, lang))
                self.assertEqual(value[lang], value[lang].strip(), "%s: %s text has spaces at an end" % (where, lang))

    def test_placeholders(self):
        for where, value, _kind in self.texts():
            for lang, s in self.variants(value):
                for name in PLACEHOLDER_RE.findall(s):
                    self.assertIn(name, PLACEHOLDERS, "%s (%s): unknown placeholder {{%s}}" % (where, lang, name))
                self.assertEqual(s.count("{{"), len(PLACEHOLDER_RE.findall(s)), "%s (%s): broken {{ }}" % (where, lang))

    def test_links_point_to_existing_pages_and_anchors(self):
        n = 0
        for where, value, kind in self.texts():
            if kind != "rich":
                continue
            for lang, s in self.variants(value):
                for _label, target in LINK_RE.findall(re.sub(r"`[^`]*`", "", s)):
                    n += 1
                    self.assertTrue(self.link_ok(target), "%s (%s): link to %s" % (where, lang, target))
        self.assertGreater(n, 10)

    def test_inline_markup_is_balanced_and_alike_in_both_languages(self):
        for where, value, kind in self.texts():
            if kind != "rich":
                continue
            for lang, s in self.variants(value):
                self.assertEqual(s.count("`") % 2, 0, "%s (%s): odd number of `" % (where, lang))
                self.assertEqual(re.sub(r"`[^`]*`", "", s).count("**") % 2, 0, "%s (%s): odd number of **" % (where, lang))
            if isinstance(value, dict):
                def marks(s):
                    bare = re.sub(r"`[^`]*`", "", s)
                    return (sorted(t for _l, t in LINK_RE.findall(bare)), sorted(PLACEHOLDER_RE.findall(s)),
                            s.count("`"), bare.count("**"))
                self.assertEqual(marks(value["en"]), marks(value["tr"]),
                                 "%s: links, placeholders, code and bold differ between en and tr" % where)

    def test_hints(self):
        hints = self.data["hints"]
        self.assertTrue(hints)
        for key, hint in hints.items():
            self.assertTrue({"text"} <= set(hint) <= {"text", "more"}, key)
            if key.startswith("prop."):
                parts = key.split(".")
                self.assertIn(len(parts), (2, 3), key)
                if len(parts) == 3:
                    self.assertIn(parts[2], PROPS, "%s: unknown device type" % key)
                    self.assertIn(parts[1], PROPS[parts[2]], "%s: that type has no such setting" % key)
                else:
                    self.assertTrue(any(parts[1] in p for p in PROPS.values()), "%s: unknown setting" % key)
            else:
                self.assertIn(key, FIXED_HINTS, "the page never asks for the hint '%s'" % key)
            if "more" in hint:
                page, _, anchor = hint["more"].partition("#")
                self.assertIn(page, self.pages, "%s: more" % key)
                if anchor:
                    self.assertIn(anchor, self.anchors[page], "%s: more" % key)
        for key in FIXED_HINTS:
            self.assertIn(key, hints, "no hint for '%s'" % key)

    def test_removed_and_unsupported_things_are_not_described(self):
        low = self.src.lower()
        self.assertNotIn("jmisc", low)
        self.assertNotIn("tz_offset", low)
        self.assertNotIn("after_restart", low)

    def test_every_new_board_and_mode_is_covered(self):
        text = json.dumps(self.data, ensure_ascii=False)
        for word in ("Nano R4", "ESP32 DevKit V1", "ESP32-C3 Super Mini", "ESP8266 NodeMCU",
                     "arduino:renesas_uno:nanor4", "esp32:esp32:esp32doit-devkit-v1",
                     "esp32:esp32:nologo_esp32c3_super_mini", "esp8266:esp8266:nodemcuv2",
                     "USB CDC On Boot", "QHOME_OPEN_BROWSER", "QHOME_USB_PROBE", "/mode/set", "=== QHome ==="):
            self.assertIn(word, text)
        modes = json.dumps(self.pages["matrix"], ensure_ascii=False)
        for mode in ("text", "clock", "value", "bar", "anim", "icon", "status", "ip", "off"):
            self.assertIn("`%s`" % mode, modes)


class GeneratedDocs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gen = load_gen_docs()

    def test_docs_are_what_gen_docs_writes_now(self):
        for lang in ("en", "tr"):
            path = os.path.join(ROOT, "docs", "help.%s.md" % lang)
            self.assertTrue(os.path.exists(path), "docs/help.%s.md is missing: run python tools/gen_docs.py" % lang)
            with open(path, encoding="utf-8", newline="") as f:
                have = f.read()
            self.assertEqual(have, self.gen.render(lang),
                             "docs/help.%s.md is out of date: run python tools/gen_docs.py" % lang)

    def test_generated_markdown(self):
        for lang in ("en", "tr"):
            md = self.gen.render(lang)
            self.assertEqual(md.split("\n")[0],
                             "<!-- Generated by tools/gen_docs.py from assets/help.js. Do not edit. -->")
            self.assertNotIn("{{", md)
            self.assertNotIn("\r", md)
            ids = re.findall(r'<a id="([^"]+)"></a>', md)
            self.assertEqual(len(ids), len(set(ids)), lang)
            for pid, _roles, en, tr, anchors in PAGES:
                self.assertIn("## %s" % (tr if lang == "tr" else en), md)
                for a in anchors:
                    self.assertIn("%s-%s" % (pid, a), ids)
            for target in re.findall(r"\]\(#([^)]+)\)", md):
                self.assertIn(target, ids, "%s: link to #%s" % (lang, target))
            for line in md.split("\n"):                 # every table row has as many cells as its head
                if line.startswith("|"):
                    self.assertTrue(line.endswith("|"), line)
            self.assertIn("192.168.1.50:7000", md)

    def test_check_mode_reports_a_current_tree(self):
        self.assertEqual(self.gen.main(["--check"]), 0)


if __name__ == "__main__":
    unittest.main()
