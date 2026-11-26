# QHome 2.1

The ESPHome idea for the Arduino UNO Q, without code and without compiling.

Upload one general firmware once. After that everything happens in a web page: give every pin a job, snap Scratch-style blocks together to automate, and add more boards (other UNO Qs, UNO R4, Nano R4, ESP32, ESP32-C3, ESP8266, even an UNO R3, Nano or Mega) whose pins then behave as if they were on the master. A saved change is live immediately; no sketch is rebuilt or re-uploaded.

| | ESPHome | QHome |
|---|---|---|
| You describe the device in | YAML | a web page (pins) and blocks (logic) |
| A change needs | compile + upload | Save & apply |
| Logic runs on | each ESP | the master UNO Q (Linux side) |
| More boards | one firmware each | one generic satellite firmware, pins appear on the master |

## New in 2.1

- The web page opens by itself when the app starts: App Lab opens it on the UNO Q, the default browser on a PC.
- The address and port are printed on the Python console, in the Log tab and on the microcontroller's Serial Monitor.
- **Boards & pins** draws every board with its pins where they are on the real board, USB connector on the left. The old rows are still there as "List view".
- New boards: Arduino Nano R4, ESP32 DevKit V1, ESP32-C3 Super Mini, ESP8266 NodeMCU.
- The LED matrix has nine modes: text, clock, live value, bar or graph, animation, icon, board status, web address, off.
- The time zone is picked from a list (named zones follow daylight saving) instead of typed as an hour offset.
- The Dashboard starts with a System panel: board name, clock, uptime, CPU, memory, storage, temperature, address, versions.
- A **Help** tab with eight pages in English and Turkish, and "?" hints next to the settings. The same text is in `docs/`.
- Boards that are plugged in or join the broker while the master runs are announced as "New board found" and can be added with one click. Adding or renaming a board no longer interrupts the other boards.
- Removed: the UNO Q's bottom connector (JMISC). Devices that sat on it are dropped when an old setup is loaded, and the Log names them (a setup file loaded in Settings: the note on the page does). Block scripts that used them are kept but switched off, so the setup still saves: pick another device in their blocks, then right-click the script's first block and choose **Enable Block**.

## How it fits together

| Part | Runs on | Job |
|---|---|---|
| `sketch/sketch.ino` | UNO Q microcontroller (STM32) | Generic pin firmware; relays UART and I2C links to other boards; prints the address on the Serial Monitor |
| `python/qh_engine.py` | UNO Q Linux side (or a PC) | Boards, devices, live state, MQTT and Home Assistant, detection of new boards |
| `python/qh_script.py` | same | Runs the block scripts straight from the saved workspace |
| `python/qh_boards.py` | same | Pin tables and drawings of the ten board models |
| `python/qh_link.py`, `qh_hw.py` | same | Links to remote boards (USB, UART, I2C, Wi-Fi) and the QLink protocol |
| `python/qh_font.py` | same | Pictures for the LED matrix: text, clock, bars, icons, animations |
| `python/qh_sys.py`, `qh_tz.py` | same | System information and addresses; time zones |
| `python/qh_mqtt.py` | same | Built-in MQTT 3.1.1 broker and client, no dependencies |
| `python/qh_web.py` + `assets/` | same, port 7000 | Web UI and REST API; `assets/help.js` holds the Help pages |
| `satellite/qhome_satellite/` | UNO R3, Nano, Mega 2560, UNO R4 Minima / WiFi, Nano R4, ESP32, ESP32-C3, ESP8266 | Generic satellite firmware |
| `tools/qhome_usb_helper.py` | UNO Q Linux, outside App Lab | Lets the app reach boards plugged in over USB when the App Lab container cannot see them |

Python 3.9+, standard library only. The React UI is built once into `frontend/dist`; Blockly and the Barlow font remain bundled in `assets/`, so the board needs no internet.

## Build and run the React app

Build the frontend from the `frontend/` directory, then start the Python server from the project root. The server serves `frontend/dist` at `/`, keeps `/api/*` on the existing Python API, and serves Blockly and Help dependencies from `assets/` under `/static/*`.

```powershell
cd frontend
npm install
npm run typecheck
npm run build
cd ..
$env:QHOME_MODE = "sim"
python python/main.py
```

On Windows, use `npm.cmd` if PowerShell does not resolve `npm`. On UNO Q/Linux, use `npm` in `frontend/` to build, then run `python3 python/main.py` from the project root (or launch it through App Lab). The Python server falls back to the legacy `assets/index.html` if `frontend/dist/index.html` is absent. Keep the generated `frontend/dist/` directory with the deployment when using the React UI.

## Try it on a PC first (VS Code)

1. Open this folder in VS Code and install the recommended extensions when asked.
2. Press **F5** and pick **QHome: simulator (demo setup, 3 simulated boards)**. The browser opens on `http://localhost:7000`.

The simulator runs the real engine with a pretend UNO Q, a pretend UNO R3 "on USB" and a pretend Nano "on I2C". Analog inputs wander, and the dashboard has a "Hold to press" button for every simulated input. The demo also pretends that an ESP32 with the id `porch` was found on Wi-Fi, so **Boards & pins** shows the "New board found" note. Without VS Code: `QHOME_MODE=sim python python/main.py`; the browser opens by itself.

| VS Code piece | What it gives you |
|---|---|
| Run and Debug (F5) | Simulator with demo setup, simulator with an empty setup, PC-as-hub mode, tests; breakpoints work in all of them |
| Terminal > Run Task | Deploy to the UNO Q over SSH, restart the app, read its log, install the USB helper, compile and upload the satellite with arduino-cli, regenerate the setup schema and the docs |
| Setup file checks | `data/config.json` and any `*.qhome.json` get autocomplete and validation from `schema/qhome-config.schema.json` |
| Testing panel | The `unittest` suites in `tests/` |
| `.ino` IntelliSense | Works without the Arduino cores, through a small stand-in in `tests/host/mock` |

## Install on the UNO Q

1. Copy this folder to `~/ArduinoApps/qhome` on the board (VS Code task **UNO Q: deploy the app**, or App Lab's import, or `scp`).
2. In App Lab open the app, go to **Sketch Libraries** and add **Arduino_RouterBridge**.
3. Press **Run**. The first start compiles the sketch and uploads it to the microcontroller.
4. App Lab opens the page in your browser as soon as QHome answers.

If no page opens, the address is shown in three places:

- The **Python console** of App Lab (and the **Log** tab) shows a framed block with `http://<address>:7000` after every start and whenever the address changes.
- The **Serial Monitor** of App Lab shows `=== QHome ===` and the address. It is printed every 30 seconds, so after you open the monitor it can take up to half a minute to appear; from then on press any key in the monitor to see it at once.
- An LED matrix set to **Web address** scrolls it.

`http://<board-name>.local:7000` works on most networks too. With a web password set, App Lab cannot open the page (it gets a password prompt instead); open the address by hand. App Lab only opens port 7000, so leave `QHOME_PORT` alone on the board.

## Environment variables

| Variable | Values | Meaning |
|---|---|---|
| `QHOME_MODE` | `auto` (default), `sim`, `pc` | `sim`: simulated UNO Q. `pc`: no local board, this computer is only the hub. `auto`: the UNO Q when the app runs on one, else the simulator |
| `QHOME_PORT` | `7000` | Web port |
| `QHOME_DATA` | folder | Where `config.json` and `state.json` live (default `data/`) |
| `QHOME_LINK_PORT` | `7001` | TCP port the USB helper connects to |
| `QHOME_OPEN_BROWSER` | `auto` (default), `1`, `0` | Open the page in the default browser at start. `auto` does it on a desktop PC, and not on the UNO Q (App Lab does it there), in a container, in CI, over SSH or on Linux without a display |
| `QHOME_USB_PROBE` | `1` (default), `0` | `0`: do not ask unassigned USB serial ports who is there (turns off the detection of new USB boards) |
| `QHOME_SIM_DISCOVER` | e.g. `esp32@wifi:porch,nano@usb:/dev/ttyACM9` | Simulator only: pretend these boards were found |
| `QHOME_REAL_LINKS` | set / unset | A simulated master still uses real USB and Wi-Fi boards (used by the tests) |

## Pins you can use

Every pin below can be configured from the **Boards & pins** tab. The board is drawn as it looks; free pins show coloured marks for what they can do, hatched pins carry a board link, and an amber corner marks a boot pin or an input-only pin. Click a pin and pick its job.

| Board | Digital in/out | PWM | Analog in | Analog out | Pulse counter | Extras |
|---|---|---|---|---|---|---|
| UNO Q | D0-D13, A0-A5, SDA, SCL, JSPI (3) | D3 D5 D6 D9 D10 D11, plus D2 D7 D8 D12 D13 SDA SCL (see note) | A0-A5, 14 bit | A0, A1 (DAC) | any header pin | LED1-LED4 (RGB), 13x8 LED matrix |
| UNO R3 | D0-D13, A0-A5 | D3 D5 D6 D9 D10 D11 | A0-A5, 10 bit | - | D2, D3 | |
| Nano | D0-D13, A0-A5 | same | A0-A7, 10 bit | - | D2, D3 | |
| Mega 2560 | D0-D53, A0-A15 | D2-D13, D44-D46 | A0-A15, 10 bit | - | D2 D3 D18-D21 | |
| UNO R4 Minima / WiFi | D0-D13, A0-A5 | D3 D5 D6 D9 D10 D11 | A0-A5, 14 bit | A0 (DAC) | D2, D3 | |
| Nano R4 | D0-D13, A0-A7 | D3 D5 D6 D9 D10 D11 | A0-A7, 14 bit | A0 (DAC) | D2, D3 | |
| ESP32 DevKit V1 | D2 D4 D5 D12-D19 D21-D23 D25-D27 D32 D33, RX0, TX0; input only: D34 D35 VP VN | every output pin except RX0 and TX0, 16 at once | D32-D35, VP, VN, 12 bit | D25, D26 (8 bit) | every PWM pin, 6 at once | |
| ESP32-C3 Super Mini | IO0-IO10, RX, TX | every pin, 6 at once | IO0-IO4, 12 bit, up to about 2.5 V | - | every pin, 6 at once | |
| ESP8266 NodeMCU | D0-D8, RX, TX | D1-D8 | A0, 10 bit, 0-3.3 V | - | D1-D8, 6 at once | |

Notes on the UNO Q:

- The extra PWM pins and the three JSPI pins (22-24) follow the pin table of the current Arduino Zephyr core; the six `~` pins and D0-D21 are the documented, safe set.
- LED1 and LED2 belong to the Linux side. LED2 normally shows system status.
- A0, A1 and D3 never tolerate more than 3.3 V. All outputs are 3.3 V.
- A pin that carries a link (D0/D1 for UART, SDA/SCL for I2C) is hatched and cannot be given a job.

Notes on the ESP boards:

- No pin tolerates 5 V.
- Pins the firmware refuses: the flash pins (GPIO6-11 on ESP32 and ESP8266, GPIO12-17 on the ESP32-C3), GPIO0 on the ESP32 DevKit and the USB pins GPIO18/19 on the ESP32-C3.
- Boot pins (ESP32: D2, D5, D12, D15; ESP32-C3: IO2, IO8, IO9; NodeMCU: D3, D4, D8) decide how the board starts. The page shows a note on each; do not hold them with a strong pull or a relay input.
- On the ESP32-C3 and the NodeMCU the printed names are not always the GPIO numbers; the page shows both.

Not covered yet: servo and tone outputs, I2C/SPI sensor drivers, CAN.

## Connecting other boards

Add a board in **Boards & pins > Add board**. The dialog shows the exact `config.h` lines for the satellite and the wiring. Flash `satellite/qhome_satellite` once with the Arduino IDE (or the VS Code task). The Help page "Board models" has the steps for each board: package, board name, FQBN, and the BOOT-button and "USB CDC On Boot" details of the ESP boards.

| Link | Works with | Wiring | Good to know |
|---|---|---|---|
| USB cable | UNO R3, Nano, Mega, UNO R4, Nano R4, ESP32, ESP32-C3, ESP8266 | Board into the UNO Q through a USB-C hub | No level shifting, also powers the board. On UNO R3, Nano, Mega, ESP32 DevKit and NodeMCU the two serial pins are taken by the USB link. |
| UART | all of the above | Master D1 (TX) to board RX, master D0 (RX) to board TX, GND to GND | One board per master. Board pins: D0/D1, on the ESP32 RX2/TX2 (GPIO16/17), on the ESP32-C3 GPIO20/21, on the NodeMCU RX/TX. 3.3 V boards connect directly; a 5 V board (UNO R3, Nano, Mega, UNO R4, Nano R4) needs a level shifter or divider on its TX line. The same link runs through RS-485 transceivers or HC-05 / HC-12 modules in transparent mode. |
| I2C | UNO R3, Nano, Mega, UNO R4, Nano R4 | SDA, SCL, GND on the master's header or Qwiic; pull-ups to 3.3 V | Several boards per bus, each with its own address (8-119). The satellite keeps its 5 V pull-ups off; still use a level shifter with 5 V boards and keep cables short. Not available on ESP boards. |
| Wi-Fi (MQTT) | UNO R4 WiFi, ESP32, ESP32-C3, ESP8266, other UNO Qs | none | Uses the master's built-in broker (or your own). Topics `qlink/<board>/down`, `up`, `status`. |

**New boards are announced.** While the master runs, a USB board with the satellite firmware is noticed a few seconds after it is plugged in, and a Wi-Fi board or UNO Q node as soon as it connects to the broker. **Boards & pins** then shows "New board found" with an **Add** button that fills in the model and the port or id; **Save & apply** brings it online without disturbing the other boards. Boards on UART or I2C wires are not detected; add them by hand.

**USB helper.** Inside App Lab the Python container may not see USB serial devices. Try without the helper first: if the board is listed under **Settings > USB boards**, nothing more is needed. If it is not, run `python3 ~/ArduinoApps/qhome/tools/qhome_usb_helper.py` on the UNO Q. To keep it running after a reboot use the VS Code task **UNO Q: install the USB helper service** or follow the comments in `tools/qhome-usb-helper.service`. On a PC the helper is not needed.

**Another UNO Q as a node.** Install QHome on it too, open **Settings > Role of this board > Node of another master**, and enter the master's address and a node name. On the master add an "Arduino UNO Q" board connected by Wi-Fi whose id is that node name. All of its pins, LEDs and its matrix then show up on the master.

**A PC as the hub.** `QHOME_MODE=pc python python/main.py` runs QHome without a local board. USB and Wi-Fi boards work; UART and I2C links need the UNO Q's microcontroller.

If a board drops off, its tiles grey out and scripts can react with "when board ... goes offline". When it returns the master sends its setup again.

## LED matrix

The matrix of the UNO Q (and of every UNO Q node) shows what **Show** says in its settings:

| Mode | Shows |
|---|---|
| Text | a text, centred or scrolling; `{id}` inserts the live value of a device |
| Clock | hours and minutes in the configured time zone |
| Live value | the value of one device, with its unit when it fits |
| Bar or graph | a level bar or a history graph of a device with a number value |
| Animation | heartbeat, wave, rain, sparkle, spinner, bouncing dot |
| Icon | one of fourteen icons (smile, heart, Wi-Fi, house, sun, bell, ...) |
| Board status | boards online / total, one dot per board, a dot for MQTT |
| Web address | scrolls `<address>:7000` |
| Off | dark |

The Dashboard tile, the blocks, `POST /api/cmd` and MQTT can show something else for a while, also for a set number of seconds; "As set up" (`auto`) returns to the setup. Such changes are forgotten at a restart.

## Blocks

The **Blocks** tab is a Scratch-style workspace (Blockly with the Scratch renderer).

| Category | Blocks |
|---|---|
| Events | when QHome starts; when a device turns on / off / changes; when a value goes above / below; every N seconds / minutes / hours; at HH:MM on chosen days; when a board goes online / offline; when an MQTT message arrives |
| Devices | turn on / off, toggle, set level, set RGB colour; for the matrix: show a text, show a text for N seconds, show an icon, play an animation, show a device's value as a number or a bar, switch the view (as set up, clock, board status, web address, off), clear |
| Sensing | is on, value of, board is online, current hour / minute / second / weekday, time is between |
| Control | wait, repeat, forever, if, if / else, wait until, repeat until, stop this script |
| Operators | arithmetic, compare, and / or / not, random, round, remainder, constrain, text, join |
| Variables | create, set, change; live values show on the dashboard |
| Network | publish to MQTT, the received MQTT message, write to the log |

Scratch rules apply: every "when" block is its own script, scripts run side by side, a script that is triggered again while running starts over, and a "forever" loop never blocks the others. Devices on any board can be mixed in one script, for example "when Door button (UNO Q) turns on, toggle Garage light (UNO R3)".

Scripts run on the master's Linux side. They stop while the master is off; satellites hold their last output state.

The time blocks, the matrix clock and the Dashboard use the time zone chosen in **Settings > Time zone**: a named zone such as Europe/Istanbul, which follows daylight saving by itself, or a fixed offset such as UTC+3. In the night the clocks go back a script "at HH:MM" runs once; one set to a time that is skipped in the night the clocks go forward runs as soon as the clock jumps. A setup from an older version with an hour offset is converted when it is loaded.

## MQTT and Home Assistant

The built-in broker listens on port 1883. In Home Assistant add the MQTT integration with the UNO Q's address; devices and one "online" sensor per board appear through auto-discovery.

| Topic | Direction | Payload |
|---|---|---|
| `<node>/<id>/state` | out, retained | `ON` or `OFF`, a number, a colour name or a text |
| `<node>/<id>/set` | in | `ON`, `OFF`, `TOGGLE`, a number, a colour name or a text |
| `<node>/<id>/level`, `<node>/<id>/level/set` | out / in | dimmer level, 0 to 100 |
| `<node>/<matrix id>/mode` | out, retained | the matrix mode drawn now: `text`, `clock`, `value`, `bar`, `anim`, `icon`, `status`, `ip` or `off` |
| `<node>/<matrix id>/mode/set` | in | `auto`, `clock`, `status`, `ip`, `off`, `icon:heart`, `anim:rain`, `value:<id>`, `bar:<id>`, `text:HELLO` |
| `<node>/status` | out, retained | `online` while QHome is connected |
| `<node>/board/<board>/state` | out, retained | `ON` while that board is online |

In Home Assistant a matrix is a text entity plus a select entity for its mode.

Set a broker user name and password and a web password in **Settings**. The web page uses plain HTTP with basic auth, so keep it on your own network. To put it behind Nginx:

```nginx
server {
    listen 80;
    location / {
        proxy_pass http://127.0.0.1:7000;
        proxy_set_header Host $host;
    }
}
```

## Help and docs

The **Help** tab of the web UI has eight pages: getting started, pins and devices, connecting boards, board models (with flashing steps), a blocks cookbook, the LED matrix, MQTT and Home Assistant, and troubleshooting. The "?" buttons next to settings open a short hint with a link into those pages.

The text lives in `assets/help.js`. `python tools/gen_docs.py` writes the same pages to `docs/help.en.md` and `docs/help.tr.md` for reading without a running QHome; `docs/README.md` says what is where and how to edit the help.

## Languages

English and Turkish, switched at the bottom left. All UI text lives in `assets/i18n.js`; copy the `en` block to add a language. The Help pages are in `assets/help.js`, with both languages side by side in every text. Blockly's own blocks use its bundled language packs (`assets/vendor/blockly/msg`); add the matching file for a new language. Log lines and save errors from the server are English only.

## Tests

`python -m unittest discover -s tests -p "test_*.py"`

| Suite | Covers |
|---|---|
| `test_qhome.py` | Setup validation and migration (version 1, hour offset to time zone, bottom-connector devices), pin tables and drawings of the ten boards, block scripts across three boards, matrix modes and commands, time zones, system information and the address banner, detection of new boards, QLink handshake and recovery, a UNO Q node over real MQTT sockets |
| `test_firmware.py` (needs g++) | Compiles the real satellite sketch against a PC stand-in for the Arduino core, once per board family (classic, Mega, R4, Nano R4, ESP32, ESP32-C3, ESP8266), and drives it over serial, I2C and Wi-Fi/MQTT; checks the pin rules of the ESP boards; runs the full chain block script > engine > USB helper > serial > firmware; lets the engine find a compiled ESP32 (Wi-Fi) and NodeMCU (USB) that are not in the setup, add them and use their pins; syntax-checks the master sketch and runs its Serial Monitor banner |
| `test_i18n.py` | English and Turkish UI texts have the same keys, and every name the server sends has a text |
| `test_help.py` | `assets/help.js` is well formed, complete in both languages, its links and hints point to existing places, and `docs/help.*.md` are current |
| `e2e_ui.py` (needs Playwright, run by hand) | Drives the page in a real browser: block editor, board drawing, found-board note, matrix modes, time zone, System panel, Help |

The stand-in checks protocol and logic, not electrical behaviour or the vendor cores. Version 2.0 of the satellite was also compiled with avr-gcc against the official AVR core; that has not been repeated for 2.1. The UNO R4, Nano R4, ESP32, ESP32-C3 and ESP8266 paths and the master sketch have not been compiled against their real cores here; check them on the first build. The ESP32 and ESP32-C3 code is written for the esp32 core 3.x and has a second PWM path for core 2.0.x (there the sketch attaches and frees the LEDC channels itself, because that core's `analogWrite()` never gives a channel back); the stand-in runs both:

```
arduino-cli compile --fqbn arduino:renesas_uno:nanor4 satellite/qhome_satellite
arduino-cli compile --fqbn esp32:esp32:esp32doit-devkit-v1 satellite/qhome_satellite
arduino-cli compile --fqbn esp32:esp32:nologo_esp32c3_super_mini satellite/qhome_satellite
arduino-cli compile --fqbn esp8266:esp8266:nodemcuv2 satellite/qhome_satellite
```

Nothing in 2.1 has been run on real hardware yet. In particular, that App Lab opens the page by itself is taken from the App Lab sources, not tried on a board.

## QLink protocol

Text lines, newline terminated, the same on every link.

| Direction | Line | Meaning |
|---|---|---|
| to board | `H` | hello; reply `h <proto> <model> <boot id>`. Models: `uno`, `nano`, `mega`, `r4m`, `r4w`, `nanor4`, `esp32`, `esp32c3`, `esp8266`, `unoq` |
| to board | `P` | ping; reply `p <boot id>` |
| to board | `C <pin> <mode> <interval ms> <debounce ms>` | set a pin's job; reply `c <pin> <mode or negative error>` |
| to board | `D <pin> <0/1>` | digital write |
| to board | `A <pin> <0-4095>` | PWM or DAC write, always 12 bit |
| to board | `L <led> <bits>`, `M <104 digits>` | RGB LED, matrix frame (UNO Q nodes) |
| to board | `R` | release all pins; reply `r 1` |
| from board | `E <pin> <value>` | input changed or periodic reading |
| from board | `B <boot id>` | the board just started |

Modes: 0 off, 1 input, 2 input pull-up, 3 input pull-down (plain input where the chip has none), 4 output, 5 PWM, 6 analog in, 7 DAC, 8 pulse counter. Errors: -1 the pin does not exist or carries the link, -2 the pin cannot do that, -3 no PWM channel or counter slot left. A changed boot id tells the master the board restarted, and it sends the setup again. The same hello is how new boards are detected: the master sends `H` to unassigned USB ports and to boards that announce themselves on `qlink/<id>/status`.

## Not in this version

- Over-the-air flashing of satellite firmware from the master.
- An I2C link on ESP boards (USB, UART and Wi-Fi work).
- Satellite firmware compiled against the real ESP32, ESP8266 and Nano R4 cores; it is tested against a PC stand-in only.
- Detection of boards on UART or I2C wires.
- eBPF packet handling from the project proposal.
- RS-485 multi-drop (several boards on one UART).
- Automatic conversion of version 1 IF/THEN automations; rebuild them as blocks. Version 1 devices are migrated.

## Licences of bundled parts

Blockly (Apache 2.0, `assets/vendor/blockly/LICENSE`), Barlow typeface (SIL OFL 1.1, `assets/fonts/LICENSE-Barlow-OFL.txt`).
