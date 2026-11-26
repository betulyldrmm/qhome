# Changelog

## 2.1.0

1. **Opens its own page.** On the UNO Q, `app.yaml` declares the `arduino:web_ui` brick so App Lab opens the page when the app starts (QHome still serves port 7000 itself). On a PC the browser opens once; `QHOME_OPEN_BROWSER=0` turns it off, `=1` forces it.
2. **Address on serial.** The address and port are printed on the Python console and on the microcontroller's Serial Monitor (repeated every 30 s and on any key press). Needs the new master sketch (v5).
3. **Board view.** Boards & pins draws each board with its headers where they really are (USB on the left). "List view" brings back the flat strips.
4. **JMISC removed.** UNO Q pins 25-49 are gone. Devices on those pins in an old setup are dropped with a note in the Log; scripts that used them are switched off, not deleted.
5. **Matrix modes.** Text, clock, live value, bar/graph, animation (6), icon (14), status, web address, off. Set in the device's settings, from the dashboard tile, from five new blocks, or over MQTT (`<node>/<id>/mode/set`).
6. **New boards.** Arduino Nano R4 (USB, UART, I2C), ESP32 DevKit V1, ESP32-C3 Super Mini and ESP8266 NodeMCU (USB, UART, Wi-Fi). Same satellite sketch; set the link in `config.h`.
7. **Time zone.** Region and city dropdowns with daylight saving, fixed UTC offsets as a fallback, and a "use this browser's zone" button. Old `tz_offset` values are converted.
8. **System panel.** The dashboard shows board name, time, uptime, CPU, memory, storage, temperature, address, versions and how many boards are online.
9. **Help.** A Help tab (English and Turkish, works offline) with search and "?" hints next to the harder fields. The same text is in `docs/help.en.md` and `docs/help.tr.md`.
10. **New boards are found.** Adding and configuring a board on a running master already worked and is unchanged. New: a board that joins over Wi-Fi or is plugged in over USB shows up as "New board found" with a prefilled Add dialog, and saving no longer restarts boards that did not change. `QHOME_USB_PROBE=0` turns USB probing off.

### After updating
- Run the app once from App Lab so the master sketch is re-uploaded (v5).
- Re-flash satellites only if you want the new boards or the ESP fixes; existing UNO/Nano/Mega/R4 satellites keep working.

### Not checked on real hardware
- App Lab opening the page through the `web_ui` brick, and the Serial Monitor text on a real UNO Q.
- Compiling the satellite for ESP32, ESP32-C3, ESP8266 and Nano R4 with their real cores (tested against a PC stand-in only).
- USB probing of real serial devices.
- If a web password is set, App Lab gets a 401 and will not open the page by itself.
