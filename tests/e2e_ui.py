"""End-to-end check through the real web UI (optional; needs Playwright and Chrome).

Starts nothing by itself: run QHome in simulation with the demo setup first, e.g.
    QHOME_MODE=sim QHOME_OPEN_BROWSER=0 QHOME_DATA=tests/fixtures/demo python python/main.py
then:  python tests/e2e_ui.py http://localhost:7000
The browser is /usr/bin/google-chrome when it exists, else Playwright's own Chromium; another
one is chosen with CHROME=/path/to/chrome.

It first walks through the views (system panel, board drawing, a found board, the matrix tile,
the time zone, the help). Then it builds three scripts with the block editor's own API, saves
them through the page, presses a simulated button and checks that the engine did what the
blocks say. The saved workspace is written to tests/fixtures/demo_workspace.json for the
offline tests (that file belongs to the engine tests: do not commit a change this run makes).
The run leaves a board "porch" and the zone Europe/Berlin in the setup of that simulator.
"""
import asyncio
import json
import os
import sys
import tempfile
import urllib.request

from playwright.async_api import async_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:7000"
HERE = os.path.dirname(os.path.abspath(__file__))
N = lambda v: {"shadow": {"type": "math_number", "fields": {"NUM": v}}}  # noqa: E731
T = lambda s: {"shadow": {"type": "text", "fields": {"TEXT": s}}}  # noqa: E731


def chain(*blocks):
    for a, b in zip(blocks, blocks[1:]):
        a["next"] = {"block": b}
    return blocks[0]


WORKSPACE = {"variables": [{"name": "count", "id": "v_count"}, {"name": "blink", "id": "v_blink"}],
             "blocks": {"languageVersion": 0, "blocks": [
    chain({"type": "ev_state", "x": 30, "y": 30, "fields": {"ENT": "button", "TO": "on"}},
          {"type": "do_toggle", "fields": {"ENT": "relay"}},
          {"type": "do_set", "fields": {"ENT": "fan"}, "inputs": {"VALUE": N(70)}},
          {"type": "do_show", "fields": {"ENT": "matrix"}, "inputs": {"TEXT": {"block": {
              "type": "text_join", "extraState": {"itemCount": 2}, "inputs": {
                  "ADD0": {"block": {"type": "text", "fields": {"TEXT": "T "}}},
                  "ADD1": {"block": {"type": "get_value", "fields": {"ENT": "temp"}}}}}}}},
          {"type": "math_change", "fields": {"VAR": {"id": "v_count"}}, "inputs": {"DELTA": N(1)}},
          {"type": "ctl_wait", "inputs": {"SECS": N(1)}},
          {"type": "do_rgb", "fields": {"ENT": "status_led", "COLOR": "green"}}),
    chain({"type": "ev_every", "x": 30, "y": 420, "fields": {"UNIT": "s"}, "inputs": {"N": N(1)}},
          {"type": "ctl_ifelse", "inputs": {
              "COND": {"block": {"type": "logic_compare", "fields": {"OP": "GT"}, "inputs": {
                  "A": {"block": {"type": "get_value", "fields": {"ENT": "ldr"}}}, "B": N(10)}}},
              "DO": {"block": {"type": "do_turn", "fields": {"ENT": "away", "TO": "on"}}},
              "ELSE": {"block": {"type": "do_turn", "fields": {"ENT": "away", "TO": "off"}}}}}),
    chain({"type": "ev_start", "x": 520, "y": 30},
          {"type": "ctl_repeat", "inputs": {"TIMES": N(3), "DO": {"block": chain(
              {"type": "math_change", "fields": {"VAR": {"id": "v_blink"}}, "inputs": {"DELTA": N(1)}},
              {"type": "ctl_wait", "inputs": {"SECS": N(0.2)}})}}}),
]}}


def get(path):
    with urllib.request.urlopen(BASE + path) as r:
        return json.load(r)


def post(path, body):
    req = urllib.request.Request(BASE + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


async def nav(pg, view, wait=500):
    await pg.locator('#nav [data-view="%s"]' % view).click()
    await pg.wait_for_timeout(wait)


async def tour(pg, problems):
    """The views added in 2.1, through the page as a user would."""
    def check(name, ok, got=None):
        if not ok:
            problems.append("%s%s" % (name, "" if got is None else " (got %r)" % (got,)))

    # Dashboard: system panel with a running board clock
    check("the Dashboard has no System panel", await pg.locator("#syspanel").count() == 1)
    c1 = await pg.locator("#sys-time").inner_text()
    await pg.wait_for_timeout(1300)
    c2 = await pg.locator("#sys-time").inner_text()
    check("the System panel clock does not run", len(c1) == 8 and c1 != c2, (c1, c2))
    check("the System panel shows no address", await pg.locator("#sys-net a").count() >= 1)

    # matrix tile: the mode dropdown overrides without Save
    mode = pg.locator('.tile[data-id="matrix"] .mxctl select').first
    await mode.select_option("clock")
    await pg.wait_for_timeout(1200)
    st = get("/api/state")
    check("matrix tile: clock mode", st["states"]["matrix"]["v"] == "[clock]", st["states"]["matrix"]["v"])
    await pg.locator('.tile[data-id="matrix"] .mxctl select').first.select_option("auto")
    await pg.wait_for_timeout(600)

    # Boards: pins where they are on the board, no bottom connector, ten models
    await nav(pg, "boards")
    if await pg.locator('.viewsw [data-view="board"]').get_attribute("aria-pressed") != "true":
        await pg.locator('.viewsw [data-view="board"]').click()
        await pg.wait_for_timeout(300)
    b13 = await pg.locator('.bd .pin[data-pin="13"]').bounding_box()
    b8 = await pg.locator('.bd .pin[data-pin="8"]').bounding_box()
    check("UNO Q drawing: D13 is not left of D8", bool(b13 and b8) and b13["x"] < b8["x"], (b13, b8))
    check("the page still mentions JMISC", "jmisc" not in (await pg.content()).lower())
    await pg.locator("#bAddBoard").click()
    await pg.wait_for_timeout(300)
    n = await pg.locator("#bdModel option").count()
    check("the Add-board dialog should list ten models", n == 10, n)
    await pg.keyboard.press("Escape")

    # a pretend found board: banner, Add prefills, Save, banner gone
    if "porch" not in get("/api/state")["boards"]:
        post("/api/sim", {"discover": {"link": "wifi", "id": "porch", "model": "esp32"}})
        await pg.wait_for_timeout(1800)
        note = pg.locator('.note.found[data-key="wifi:porch"]')
        check("no banner for the found board", await note.count() == 1)
        if await note.count() == 1:
            await note.locator("button.primary").click()
            await pg.wait_for_timeout(300)
            got = (await pg.locator("#bdModel").input_value(), await pg.locator("#bdId").input_value())
            check("Add does not prefill model and id", got == ("esp32", "porch"), got)
            await pg.locator("#bdOk").click()
            await pg.wait_for_timeout(300)
            await pg.locator("#bSave").click()
            await pg.wait_for_timeout(2500)
            check("no tab for the added board", await pg.locator('.tabs [data-bid="porch"]').count() == 1)
            check("the found banner stays after Save", await pg.locator('.note.found[data-key="wifi:porch"]').count() == 0)
            check("the added board is not online", get("/api/state")["boards"].get("porch", {}).get("online") is True)

    # Settings: the two time zone dropdowns; saving Europe/Berlin changes time.tz
    await nav(pg, "settings")
    check("Settings: time zone dropdowns", await pg.locator("#tzRegion").count() == 1 and await pg.locator("#tzCity").count() == 1)
    # a setup file from before 2.1 loaded in the page: hour offset -> zone, bottom-connector device left out
    old = get("/api/config")
    old["device"].pop("tz", None)
    old["device"]["tz_offset"] = 5.5
    old["components"].append({"id": "oldpump", "type": "switch_output", "name": "Old pump", "board": "main", "pin": 30, "props": {}})
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(old, f)
    try:
        await pg.locator("input[type=file]").set_input_files(f.name)
        await pg.wait_for_timeout(400)
        got = await pg.evaluate("[DRAFT.device.tz, 'tz_offset' in DRAFT.device, DRAFT.components.some(c => c.id === 'oldpump')]")
        check("loading an old setup file", got == ["UTC+5:30", False, False], got)
        check("the note names the device that was left out", "oldpump" in await pg.locator("#toast").inner_text())
        await pg.locator("#bUndo").click()
        await pg.wait_for_timeout(300)
    finally:
        os.unlink(f.name)
    await pg.locator("#tzRegion").select_option("Europe")
    await pg.wait_for_timeout(200)
    await pg.locator("#tzCity").select_option("Europe/Berlin")
    await pg.wait_for_timeout(200)
    if await pg.locator("#bSave").is_enabled():
        await pg.locator("#bSave").click()
        await pg.wait_for_timeout(1500)
    tz = get("/api/state")["time"]["tz"]
    check("saving the time zone", tz == "Europe/Berlin", tz)

    # Help: the pages, and boards#esp32
    await nav(pg, "help")
    n = await pg.locator(".helplist button[data-page]").count()
    check("the Help view lists no pages", n >= 2, n)
    if n:
        await pg.evaluate('helpOpen("boards", "esp32")')
        await pg.wait_for_timeout(400)
        check("Help does not open boards#esp32", await pg.locator("#h-esp32").count() == 1
              and await pg.evaluate("location.hash") == "#help/boards/esp32")
    await nav(pg, "dash")


async def main():
    problems = []
    async with async_playwright() as p:
        exe = os.environ.get("CHROME", "/usr/bin/google-chrome")
        b = await p.chromium.launch(executable_path=exe if os.path.exists(exe) else None, args=["--no-sandbox"])
        pg = await (await b.new_context(viewport={"width": 1360, "height": 860})).new_page()
        pg.on("pageerror", lambda e: problems.append("page error: %s" % e))
        pg.on("console", lambda m: problems.append("console: " + m.text) if m.type == "error" else None)
        await pg.goto(BASE)
        await pg.wait_for_timeout(2000)
        await tour(pg, problems)
        await pg.locator('#nav [data-view="blocks"]').click()
        await pg.wait_for_timeout(1500)
        saved = await pg.evaluate("""ws => {
            const w = Blockly.getMainWorkspace();
            Blockly.serialization.workspaces.load(ws, w);     // fires change events -> draft updated
            return Blockly.serialization.workspaces.save(w);
        }""", WORKSPACE)
        await pg.wait_for_timeout(600)
        if len(sys.argv) > 2:
            await pg.screenshot(path=sys.argv[2])
        await pg.locator("#bSave").click()
        await pg.wait_for_timeout(800)
        err = await pg.locator("#errbox").inner_text() if await pg.locator("#errbox").is_visible() else ""
        if err:
            problems.append("save rejected: " + err)
        await b.close()
    with open(os.path.join(HERE, "fixtures", "demo_workspace.json"), "w") as f:
        json.dump(saved, f, indent=1)
    await asyncio.sleep(2.5)
    st = get("/api/state")
    if st["vars"].get("blink") != "3":
        problems.append("start script: blink should be 3, is %r" % st["vars"].get("blink"))
    if st["states"]["away"]["v"] is not True:
        problems.append("every-second script should have switched 'away' on")
    post("/api/sim", {"board": "main", "pin": 2, "value": 0})      # press (pull-up, inverted)
    await asyncio.sleep(0.5)
    st = get("/api/state")
    checks = [("relay", st["states"]["relay"]["v"] is True), ("fan", st["states"]["fan"]["v"] == {"on": True, "level": 70.0}),
              ("matrix", str(st["states"]["matrix"]["v"]).startswith("T ")), ("count", st["vars"].get("count") == "1"),
              ("led still off", st["states"]["status_led"]["v"] == "off")]
    post("/api/sim", {"board": "main", "pin": 2, "value": 1})
    await asyncio.sleep(1.3)
    st = get("/api/state")
    checks.append(("led green after wait", st["states"]["status_led"]["v"] == "green"))
    problems += ["after button press: %s is wrong" % name for name, ok in checks if not ok]
    print("\n".join(problems) if problems else "UI end-to-end: all checks passed")
    sys.exit(1 if problems else 0)

asyncio.run(main())
