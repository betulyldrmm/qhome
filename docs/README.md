# QHome documentation

## What is where

| You want | Look at |
|---|---|
| Help while using QHome | The **Help** tab of the web page, and the "?" buttons next to the settings. English and Turkish, following the language switch. |
| The same help without a running QHome | [help.en.md](help.en.md) (English), [help.tr.md](help.tr.md) (Türkçe). Generated; do not edit. |
| Overview, installing, the VS Code setup, environment variables, tests | [../README.md](../README.md) |
| The QLink protocol between the master and the other boards | [../README.md](../README.md#qlink-protocol) |
| The format of a setup file (`data/config.json`) | `schema/qhome-config.schema.json`, written by `tools/gen_schema.py` |
| Settings of the satellite firmware | The comments in `satellite/qhome_satellite/config.h` |
| The USB helper as a service | The comments in `tools/qhome-usb-helper.service` |

The help has eight pages:

| Page | Id | Covers |
|---|---|---|
| Getting started | `start` | Installing, where the address is shown, the tabs, a first device and script, the simulator |
| Pins and devices | `pins` | What each board offers, limits per board, inputs, analog sensors, counters, outputs |
| Connecting boards | `wiring` | USB, UART, I2C and Wi-Fi links, wiring and voltages, the USB helper |
| Board models | `boards` | Flashing the satellite firmware on each board, and how new boards are found |
| Blocks cookbook | `blocks` | How scripts run, the time blocks, five recipes |
| LED matrix | `matrix` | The nine modes, icons and animations, who decides what is shown, blocks and commands |
| MQTT and Home Assistant | `mqtt` | Setting up Home Assistant, topics, MQTT in scripts, security |
| Troubleshooting | `faq` | The address, the web password, the time, offline boards, save errors |

A UNO Q in the node role shows `start` and `faq` only.

## Editing the help

All help text is in one file, `assets/help.js`. The page (`assets/app.js`) only draws it.

1. Edit `assets/help.js`. Every text needs both languages.
2. Run `python tools/gen_docs.py` (VS Code task **QHome: regenerate the docs**). It rewrites `help.en.md` and `help.tr.md`.
3. Run `python -m unittest tests/test_help.py`. It checks the format, both languages, every link and hint, and that the two generated files are current.

Run step 2 again after changing a board table (`python/qh_boards.py`), the device types (`python/qh_engine.py`), the matrix icons or animations (`python/qh_font.py`) or their names in `assets/i18n.js`: the tables in the generated files come from there. `python tools/gen_docs.py --check` writes nothing and exits with 1 when a file is out of date.

### File format

`assets/help.js` is `//` comment lines, then `window.QHELP = `, then strict JSON, then `;`. Strict JSON means double quotes, no trailing commas, no comments inside. Python reads the same file, so keep it that way.

```json
{
  "version": 1,
  "pages": [
    {"id": "start", "roles": ["master", "node"],
     "title": {"en": "Getting started", "tr": "Başlarken"},
     "blocks": [
       {"t": "p", "text": {"en": "Open **{{url}}** in a browser.", "tr": "Tarayıcıda **{{url}}** adresini açın."}}
     ]}
  ],
  "hints": {
    "prop.pull": {"text": {"en": "...", "tr": "..."}, "more": "pins#inputs"}
  }
}
```

A text is either a plain string (the same in both languages: code, names) or an object with both `en` and `tr`.

`roles` lists where a page is shown: `master`, `node` or both.

### Blocks

| `t` | Fields | Shown as |
|---|---|---|
| `h` | `id`, `text` | Section heading. `id` is the anchor: lowercase letters, digits and `-`, unique in the page |
| `p` | `text` | Paragraph |
| `ul`, `ol` | `items` (list of texts) | Bulleted or numbered list, one level |
| `code` | `text` | Code block. Placeholders are filled in; inline markup is not applied |
| `note` | `text`, optional `"warn": true` | Information box, or a warning box |
| `table` | `head` (list of texts), `rows` (list of rows, each as long as `head`) | Table |
| `gen` | `name` | A table built from the running program: `boards`, `links`, `types`, `icons` or `anims` |

### Inline markup

Everywhere except in `code` blocks:

| Write | Get |
|---|---|
| `**Save & apply**` | bold: use it for names of buttons, tabs and settings, exactly as the page shows them |
| `` `QL_BAUD` `` | code: file names, commands, values to type, block texts |
| `[LED matrix](#matrix)` | a link to another help page |
| `[The time is wrong](#faq/timezone)` | a link to a heading of a page |

### Placeholders

The page replaces them with the values of the running installation; the generated files show sample values.

| Placeholder | In the page | In `docs/` |
|---|---|---|
| `{{url}}` | the address in the browser | `http://192.168.1.50:7000` |
| `{{host}}` | the master's address | `192.168.1.50` |
| `{{node}}` | the node name from Settings | `qhome` |
| `{{web_port}}` | the web port | `7000` |
| `{{mqtt_port}}` | the MQTT port in use | `1883` |
| `{{link_port}}` | the USB helper port | `7001` |
| `{{version}}` | the QHome version | the version in `python/qh_engine.py` |

### Hints

A hint is the short text behind a "?" button. `more` is optional and names the help page (`page` or `page#anchor`) that the "More in Help" link opens. The page asks for hints under these keys only; any other key is never shown:

| Key | Where |
|---|---|
| `prop.<setting>.<device type>`, else `prop.<setting>` | A setting of a device in **Boards & pins**, for example `prop.pull` or `prop.invert.switch_output`. The names are the ones in the `TYPES` table of `python/qh_engine.py` |
| `pin.id` | The Id field of a device |
| `board.id`, `board.link`, `link.port`, `link.addr` | The Add board / Edit board dialog |
| `set.node`, `set.pw`, `set.tz`, `set.role`, `set.mqtt`, `mqtt.prefix`, `set.usb` | Settings |
| `found` | The "New board found" note |

### Ids other files rely on

The page links to these headings; renaming one breaks a link in `assets/app.js` (and `tests/test_help.py` will say so):

- `boards#unoq`, `boards#avr`, `boards#r4`, `boards#esp32`, `boards#esp32c3`, `boards#esp8266`: "How to flash this board" in the board dialog.
- `boards#found`: the "New board found" note.
- `faq#password`, `faq#timezone`: hints in Settings.

### Wording

- Use the words the page uses. Names of tabs, buttons and settings come from `assets/i18n.js`; copy them from there in both languages.
- Say what to do and what happens. Leave out anything a reader does not need to act.
- Do not describe what QHome cannot do yet as if it could. Limits belong in the text: no I2C link on ESP boards, no detection of boards on UART or I2C wires.
