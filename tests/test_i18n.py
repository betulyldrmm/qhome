"""The two language packs of the web UI (assets/i18n.js) stay in step (standard library only).

Reads only assets/i18n.js: every key exists in English and Turkish, every key the page builds from
a value the server sends is there (matrix modes, animations, icons, pin notes, list groups, blocks),
and the keys of removed features are gone.
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
I18N = os.path.join(os.path.dirname(HERE), "assets", "i18n.js")

PAIR = re.compile(r'"((?:[^"\\]|\\.)+)":\s*"((?:[^"\\]|\\.)*)"')

# Values the server sends (python/qh_font.py, qh_boards.py, qh_script.py); the page looks up <prefix><value>.
MODES = ("text", "clock", "value", "bar", "anim", "icon", "status", "ip", "off")
ANIMS = ("heartbeat", "wave", "rain", "sparkle", "spinner", "bounce")
ICONS = ("smile", "sad", "heart", "check", "cross", "wifi", "house", "sun", "moon", "bell", "warn", "lock", "up", "down")
NEW_NOTES = ("strap", "boot_low", "boot_btn", "boot_out", "in_only", "no_pullup", "led_builtin_low", "adc_2v5",
             "a0_3v3", "uart2_rx", "uart2_tx", "dac8")
OLD_NOTES = ("uart_rx", "uart_tx", "no5v", "ain3v3", "can_tx", "can_rx", "spi_ss", "spi_mosi", "spi_miso", "spi_sck",
             "i2c_sda", "i2c_scl", "pwm_core", "jspi", "led_linux", "led_status", "led_mcu", "matrix_13x8", "ain_only",
             "led_builtin", "logic5", "logic33")
GROUPS = ("digital", "analog", "onboard", "jspi", "gpio")
NEW_BLOCKS = ("do_show_for", "do_mx_icon", "do_mx_anim", "do_mx_value", "do_mx_mode")
MATRIX_PROPS = ("brightness", "mode.led_matrix", "startup_text", "source", "bar_style", "bar_min", "bar_max",
                "graph_secs", "anim", "speed", "icon", "clock_12h", "scroll_ms")
REMOVED = ("group.jmisc", "note.jmisc", "note.port", "dash.clear")


def load():
    """-> {"en": {key: text}, "tr": {key: text}} and the duplicate keys of each block."""
    with open(I18N, encoding="utf-8") as f:
        lines = f.read().split("\n")
    start_en = next(i for i, l in enumerate(lines) if l.strip() == "en: {")
    start_tr = next(i for i, l in enumerate(lines) if l.strip() == "tr: {")
    end = next(i for i, l in enumerate(lines) if i > start_tr and l.strip() == "},")
    packs, dupes = {}, {}
    for lang, a, b in (("en", start_en, start_tr), ("tr", start_tr, end)):
        packs[lang], dupes[lang] = {}, []
        for key, text in PAIR.findall("\n".join(lines[a + 1:b])):
            if key in packs[lang]:
                dupes[lang].append(key)
            packs[lang][key] = text
    return packs, dupes


class I18nTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packs, cls.dupes = load()
        cls.en, cls.tr = cls.packs["en"], cls.packs["tr"]

    def test_parsed_something(self):
        self.assertGreater(len(self.en), 300)
        self.assertEqual(self.en["nav.help"], "Help")
        self.assertEqual(self.tr["nav.help"], "Yardım")

    def test_same_keys_in_both_languages(self):
        self.assertEqual(sorted(set(self.en) - set(self.tr)), [], "keys missing in tr")
        self.assertEqual(sorted(set(self.tr) - set(self.en)), [], "keys missing in en")

    def test_no_key_twice(self):
        self.assertEqual(self.dupes, {"en": [], "tr": []})

    def test_no_empty_text(self):
        for lang, pack in self.packs.items():
            self.assertEqual([k for k, v in pack.items() if not v.strip()], [], lang)

    def test_same_placeholders(self):
        """{0} {1} and %1 %2 are filled in by the page: both languages must use the same set."""
        for key, text in self.en.items():
            for pat in (r"\{\d\}", r"%\d"):
                self.assertEqual(sorted(set(re.findall(pat, text))), sorted(set(re.findall(pat, self.tr[key]))), key)

    def test_keys_derived_from_server_values(self):
        want = ["mx.auto", "mx.changed", "mxas.value", "mxas.bar", "opt.bar_style.level", "opt.bar_style.graph"]
        want += ["mx." + m for m in MODES] + ["anim." + a for a in ANIMS] + ["icon." + i for i in ICONS]
        want += ["note." + n for n in NEW_NOTES + OLD_NOTES] + ["group." + g for g in GROUPS]
        want += ["blk." + b for b in NEW_BLOCKS] + ["prop." + p for p in MATRIX_PROPS]
        for lang, pack in self.packs.items():
            self.assertEqual([k for k in want if k not in pack], [], lang)

    def test_spec_keys(self):
        want = ["nav.help", "sys.title", "boards.view.board", "boards.view.list", "fw.more", "wire.uart.pins", "wire.uart.33",
                "found.usb", "found.wifi", "found.unknown", "found.silent", "found.add", "found.ignore",
                "set.tz", "set.tz.region", "set.tz.city", "set.tz.fixed", "set.tz.browser", "set.tz.now", "set.tz.preview",
                "set.tz.nodb", "set.tz.fallback", "set.tz.skew",
                "help.search", "help.onpage", "help.more", "help.what", "help.empty"]
        for lang, pack in self.packs.items():
            self.assertEqual([k for k in want if k not in pack], [], lang)

    def test_removed_keys_are_gone(self):
        for lang, pack in self.packs.items():
            self.assertEqual([k for k in REMOVED if k in pack], [], lang)
        with open(I18N, encoding="utf-8") as f:
            self.assertNotIn("jmisc", f.read().lower())

    def test_block_texts_name_every_argument(self):
        args = {"do_show_for": 3, "do_mx_icon": 2, "do_mx_anim": 2, "do_mx_value": 3, "do_mx_mode": 2}
        for lang, pack in self.packs.items():
            for block, n in args.items():
                self.assertEqual(sorted(set(re.findall(r"%\d", pack["blk." + block]))), ["%%%d" % i for i in range(1, n + 1)],
                                 "%s blk.%s" % (lang, block))


if __name__ == "__main__":
    unittest.main()
