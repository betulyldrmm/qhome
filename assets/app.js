// QHome web UI. No build step: plain ES2020, served as-is by python/qh_web.py.
"use strict";

// ------------------------------------------------------------------ helpers
const $ = sel => document.querySelector(sel);
function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "class") e.className = v;
    else if (k === "value") e.value = v;
    else if (k === "checked") e.checked = v;
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat()) {
    if (c == null || c === false) continue;
    e.append(c.nodeType ? c : document.createTextNode(c));
  }
  return e;
}
const clone = o => JSON.parse(JSON.stringify(o));
async function api(path, body) {
  const r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  return r.json();
}
function toast(text) {
  const e = $("#toast");
  e.textContent = text;
  e.classList.add("show");
  clearTimeout(e._t);
  e._t = setTimeout(() => e.classList.remove("show"), Math.max(2400, 50 * String(text).length));   // long messages stay longer
}
function lsGet(key, fallback) {
  try { const v = localStorage.getItem(key); return v == null ? fallback : v; } catch (e) { return fallback; }
}
function lsSet(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* storage blocked */ } }
const RGB_CSS = { off: "#2B3331", red: "#F04438", green: "#22C55E", yellow: "#FACC15", blue: "#3B82F6", magenta: "#D946EF", cyan: "#22D3EE", white: "#FFFFFF" };
const ID_PREFIX = { binary_input: "input", analog_sensor: "sensor", pulse_counter: "counter", switch_output: "relay", pwm_output: "dimmer",
                    dac_output: "analog_out", rgb_led: "led", led_matrix: "matrix", virtual_switch: "flag" };
const ID_RE = /^[a-z][a-z0-9_]{0,31}$/;

// ------------------------------------------------------------------ state
let META = null, CFG = null, DRAFT = null, ST = null;
let VIEW = "dash", SELB = null, SEL = null, LOGSEQ = 0, LOGS = [], BLOCKS_READY = false, PORTS = [];
let SKEW = 0;                    // board clock minus this device's clock, in ms (refreshed on every poll)
let PDOWN = false;               // a pointer is held down (a slider being dragged must not be redrawn)
const HIST = {};
const HELP = { page: null, anchor: null, q: "" };
const dirty = () => JSON.stringify(CFG) !== JSON.stringify(DRAFT);
const isNode = () => META.role === "node";
const comps = () => DRAFT.components;
const compById = id => comps().find(c => c.id === id);
const boardById = (id, cfg = DRAFT) => cfg.boards.find(b => b.id === id);
const modelOf = b => (b ? META.models[b.model] : null);
const pinOf = (b, pid) => (modelOf(b) ? modelOf(b).pins.find(p => p.id === pid) : null);
const pinName = p => p.label + (p.alt ? " (" + p.alt + ")" : "");
const compAt = (bid, pid) => comps().find(c => c.board === bid && c.pin === pid);
const stOf = id => (ST && ST.states && ST.states[id]) || {};
const frameOf = id => (ST && ST.matrix && ST.matrix[id]) || "";
const typeLabel = type => t("type." + type);
function propsOf(c) {
  const o = {};
  for (const p of META.types[c.type].props) o[p.key] = p.default;
  return Object.assign(o, c.props || {});
}
// Twin of reserved_pins() in python/qh_boards.py: the pins a board's link takes away.
function reservedPins(b) {
  const m = modelOf(b), out = {}, lt = (b.link || {}).type;
  if (!m) return out;
  const uart = m.uart_pins || m.serial_pins || [], serial = m.serial_pins || [], i2c = m.i2c_pins || [];
  if (lt === "uart") uart.forEach(p => (out[p] = "link_serial"));
  if (lt === "usb" && m.usb_shares_uart) serial.forEach(p => (out[p] = "link_serial"));
  if (lt === "i2c") i2c.forEach(p => (out[p] = "link_i2c"));
  if (lt === "local") for (const o of DRAFT.boards) {
    const ol = o.link || {};
    if (o === b) continue;
    if (ol.type === "uart") uart.forEach(p => (out[p] = "host_uart"));
    if (ol.type === "i2c" && (ol.bus || "wire") === "wire") i2c.forEach(p => (out[p] = "host_i2c"));
  }
  return out;
}
function changed() { updateTop(); updateBadge(); }
function updateTop() {
  const d = dirty();
  $("#bSave").disabled = !d;
  $("#bUndo").hidden = !d;
  $("#dirtyTxt").textContent = d ? t("unsaved") : "";
}
function typingIn(root) {         // the user is inside a text box or dropdown of this element
  const a = document.activeElement;
  if (!a || !root || !root.contains(a) || !a.matches("input,select,textarea")) return false;
  return a.type === "range" ? PDOWN : a.type !== "checkbox";
}

// ------------------------------------------------------------------ navigation
function views() {
  return isNode() ? [["dash", "nav.dash"], ["settings", "nav.settings"], ["log", "nav.log"], ["help", "nav.help"]]
    : [["dash", "nav.dash"], ["boards", "nav.boards"], ["blocks", "nav.blocks"], ["settings", "nav.settings"], ["log", "nav.log"], ["help", "nav.help"]];
}
function renderNav() {
  const n = $("#nav");
  n.replaceChildren(...views().map(([k, label]) =>
    h("button", { "aria-current": VIEW === k ? "page" : null, "data-view": k, onclick: () => go(k) }, t(label),
      k === "boards" ? h("span", { class: "badge", id: "navBadge", hidden: true }) : null)));
  updateBadge();
}
function helpHref(page, anchor) { return "#help" + (page ? "/" + page + (anchor ? "/" + anchor : "") : ""); }
function setHash() {              // keeps the address in step with the view, without creating history entries
  const want = VIEW === "dash" ? "" : VIEW === "help" ? helpHref(HELP.page, HELP.anchor) : "#" + VIEW;
  if (location.hash === want) return;
  try { history.replaceState(null, "", location.pathname + location.search + want); } catch (e) { /* file: or sandboxed */ }
}
function readHash() {
  const parts = decodeURIComponent(location.hash.replace(/^#/, "")).split("/");
  if (!views().some(v => v[0] === parts[0])) return false;
  VIEW = parts[0];
  if (VIEW === "help") { HELP.page = parts[1] || HELP.page; HELP.anchor = parts[2] || null; }
  return true;
}
function go(view) {
  VIEW = view;
  HINT_OPEN = null;
  for (const k of Object.keys(TILE_MX)) delete TILE_MX[k];
  if (view !== "help") HELP.anchor = null;
  renderNav(); render();
}
function render() {
  const main = $("#main"), bv = $("#blocksView");
  const blocks = VIEW === "blocks";
  main.hidden = blocks;
  bv.hidden = !blocks;
  delete main.dataset.dash;
  if (blocks) showBlocks();
  else {
    main.replaceChildren();
    ({ dash: isNode() ? viewNode : viewDash, boards: viewBoards, settings: viewSettings, log: viewLog, help: viewHelp })[VIEW](main);
  }
  updateTop();
  setHash();
}

// ------------------------------------------------------------------ board clock (independent of this device's time zone)
function fixedName(min) {         // 180 -> "UTC+3", 330 -> "UTC+5:30", 0 -> "UTC" (as qh_tz.fixed_name)
  if (!min) return "UTC";
  const a = Math.abs(min), mm = a % 60;
  return "UTC" + (min < 0 ? "-" : "+") + Math.floor(a / 60) + (mm ? ":" + String(mm).padStart(2, "0") : "");
}
function fixedMinutes(name) {     // "UTC+5:30" -> 330; null when it is not a fixed-offset name
  const m = /^UTC(?:([+-])(\d{1,2})(?::(00|15|30|45))?)?$/.exec(name || "");
  if (!m) return null;
  const v = (+(m[2] || 0) * 60 + +(m[3] || 0)) * (m[1] === "-" ? -1 : 1);
  return v < -720 || v > 840 ? null : v;
}
function boardDate(offsetMin) {   // a Date whose UTC fields read as the board's local date and time
  if (!ST || !ST.time || typeof ST.time.offset !== "number") return null;
  return new Date(Date.now() + SKEW + (offsetMin == null ? ST.time.offset : offsetMin) * 60000);
}
const hms = d => d.toISOString().slice(11, 19);
function longDate(d) {
  try { return d.toLocaleDateString(LANG, { timeZone: "UTC", weekday: "short", day: "numeric", month: "short", year: "numeric" }); }
  catch (e) { return d.toISOString().slice(0, 10); }
}
function tzPreview(tz) {          // what the clock would read in a zone that is not saved yet
  const fm = fixedMinutes(tz);
  if (fm != null) { const d = boardDate(fm); return d ? hms(d) + ", " + tz : tz; }
  try {
    return new Intl.DateTimeFormat(LANG, { timeZone: tz, hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23", timeZoneName: "shortOffset" })
      .format(Date.now() + SKEW).replace("GMT", "UTC");
  } catch (e) { return tz; }
}
function setText(el, text) { if (el && el.textContent !== text) el.textContent = text; }
function clockTick() {            // the one-second timer: every element that shows the board clock
  const d = boardDate(), tm = (ST && ST.time) || {};
  setText($("#sys-time"), d ? hms(d) : "-");
  setText($("#sys-time-s"), d ? longDate(d) + "\n" + [tm.label, String(tm.tz || "").replace(/_/g, " ")].filter(Boolean).join(" · ") : "");
  const now = $("#tznow");
  if (now) {
    setText(now, d ? t("set.tz.now", hms(d), tm.label || tm.tz || "") : "");
    const prev = $("#tzprev"), draft = (DRAFT.device || {}).tz;
    if (prev) { prev.hidden = !draft || draft === tm.tz; setText(prev, prev.hidden ? "" : t("set.tz.preview", tzPreview(draft))); }
    const warn = $("#tzwarn");
    if (warn) {
      const list = [];
      if (d && Math.abs(SKEW) > 120000) list.push(t("set.tz.skew", Math.round(Math.abs(SKEW) / 60000)));
      if (tm.exact === false) list.push(t("set.tz.nodb"));
      const sig = list.join("|");
      if (warn.dataset.sig !== sig) { warn.dataset.sig = sig; warn.replaceChildren(...list.map(x => h("div", { class: "note" }, x))); }
    }
  }
}

// ------------------------------------------------------------------ dashboard: system panel
function fmtNum(n, digits) {
  try { return n.toLocaleString(LANG, { maximumFractionDigits: digits, minimumFractionDigits: 0 }); } catch (e) { return n.toFixed(digits); }
}
function fmtBytes(n) {
  if (typeof n !== "number") return "-";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return fmtNum(n, n >= 100 || i < 2 ? 0 : 1) + " " + units[i];
}
function fmtDur(s) {              // 3 d 4 h, 5 h 12 min, 12 min, 48 s
  if (typeof s !== "number" || isNaN(s)) return "-";
  s = Math.max(0, Math.floor(s));
  const u = k => " " + t("sys.u." + k), d = Math.floor(s / 86400), hh = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
  if (d) return d + u("d") + " " + hh + u("h");
  if (hh) return hh + u("h") + " " + m + u("min");
  if (m) return m + u("min");
  return s + u("s");
}
function boardText() {
  const s = META.sys || {};
  if (s.board_model) return s.board_model;
  if (META.has_local && !META.sim) return t("sys.board.unoq");
  if (META.sim) return t("sys.board.sim");
  return t("sys.board.pc") + (s.hostname ? " (" + s.hostname + ")" : "");
}
function sysBox(key, id, bar) {
  return h("div", { class: "sysbox" }, h("div", { class: "k" }, t(key)), h("div", { class: "v", id: "sys-" + id }, "-"),
    bar ? h("div", { class: "bar" }, h("i", { id: "sys-" + id + "-bar" })) : null, h("div", { class: "s", id: "sys-" + id + "-s" }));
}
function sysPanel() {
  const boxes = [sysBox("sys.board", "board"), sysBox("sys.time", "time"), sysBox("sys.uptime", "up"), sysBox("sys.cpu", "cpu", true),
    sysBox("sys.mem", "mem", true), sysBox("sys.disk", "disk", true), sysBox("sys.temp", "temp"), sysBox("sys.net", "net"), sysBox("sys.soft", "soft")];
  if (!isNode()) boxes.push(sysBox("sys.status", "stat"));
  return h("section", { class: "panel sys", id: "syspanel", "aria-label": t("sys.title") }, h("h3", {}, t("sys.title")), h("div", { class: "sysgrid" }, boxes));
}
// Fills the panel in place. Called on every poll; never redraws the page (a text box keeps its focus).
function sysPatch() {
  if (!$("#syspanel")) return;
  const s = (ST && ST.sys) || {}, ms = META.sys || {};
  const set = (id, text) => setText($("#sys-" + id), text);
  const pct = (id, o) => {
    const ok = o && typeof o.pct === "number";
    set(id, ok ? fmtNum(o.pct, 0) + " %" : "-");
    set(id + "-s", ok && typeof o.total === "number" ? t("sys.of", fmtBytes(o.used), fmtBytes(o.total)) : "");
    bar(id, ok ? o.pct : null);
  };
  const bar = (id, v) => {
    const b = $("#sys-" + id + "-bar");
    if (!b) return;
    b.style.width = v == null ? "0" : Math.max(0, Math.min(100, v)) + "%";
    b.className = v > 90 ? "err" : v > 75 ? "warn" : "";
  };
  set("board", (CFG.device || {}).name || "-");
  set("board-s", boardText());
  set("up", ST && typeof ST.uptime === "number" ? fmtDur(ST.uptime) : "-");
  set("up-s", typeof s.os_uptime === "number" ? t("sys.uptime.os", fmtDur(s.os_uptime)) : "");
  set("cpu", typeof s.cpu === "number" ? fmtNum(s.cpu, 1) + " %" : "-");
  set("cpu-s", [Array.isArray(s.load) && typeof s.load[0] === "number" ? t("sys.cpu.load", fmtNum(s.load[0], 2)) : null,
    ms.cpus ? t("sys.cpu.cores", ms.cpus) : null].filter(Boolean).join(" · "));
  bar("cpu", typeof s.cpu === "number" ? s.cpu : null);
  pct("mem", s.mem);
  pct("disk", s.disk);
  set("temp", typeof s.temp === "number" ? fmtNum(s.temp, 1) + " °C" : "-");
  const net = $("#sys-net"), port = s.port || META.web_port || location.port;
  const urls = (s.ips || []).length ? s.ips.map(ip => "http://" + ip + (port ? ":" + port : "")) : [location.origin];
  if (net && net.dataset.sig !== urls.join(" ")) {
    net.dataset.sig = urls.join(" ");
    net.replaceChildren(...urls.map(u => h("a", { href: u }, u.replace(/^https?:\/\//, ""))));
  }
  set("net-s", port ? t("sys.net.port", port) : "");
  set("soft", "QHome " + META.version);
  const local = isNode() ? null : CFG.boards.find(b => (b.link || {}).type === "local");
  const fw = local && ST && ST.boards && ST.boards[local.id] ? ST.boards[local.id].fw : null;
  set("soft-s", [ms.python ? "Python " + ms.python : null, [ms.os, ms.arch].filter(Boolean).join(" ") || null, fw != null ? t("sys.fw", fw) : null].filter(Boolean).join("\n"));
  if (!isNode()) {
    const on = ST && ST.boards ? CFG.boards.filter(b => (ST.boards[b.id] || {}).online).length : null;
    set("stat", on == null ? "-" : on + " / " + CFG.boards.length);
    set("stat-s", ST ? [t("sys.boards"), "MQTT: " + ((ST.mqtt || {}).text || "-"), t("sys.scripts", ST.running || 0)].join("\n") : "");
  }
  clockTick();
}

// ------------------------------------------------------------------ dashboard
function command(id, action, value) { api("/api/cmd", { id, action, value }); }
function sparkline(id) {
  const a = HIST[id] || [];
  if (a.length < 2) return h("div", { class: "small muted" }, t("dash.waiting"));
  const mn = Math.min(...a), mx = Math.max(...a), r = (mx - mn) || 1;
  const pts = a.map((v, i) => (i / (a.length - 1) * 100).toFixed(1) + "," + (28 - (v - mn) / r * 26 + 1).toFixed(1)).join(" ");
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("viewBox", "0 0 100 30");
  s.setAttribute("preserveAspectRatio", "none");
  s.classList.add("spark");
  s.innerHTML = `<polyline points="${pts}" fill="none" stroke="#B0650A" stroke-width="1.5" vector-effect="non-scaling-stroke"/>`;
  return s;
}
function matrixView(frame, cls) {
  const g = h("div", { class: cls || "mxview" });
  for (let i = 0; i < 104; i++) {
    const b = +((frame || "")[i] || 0);
    g.append(h("i", { style: b ? `background:rgba(125,211,252,${0.3 + b * 0.1})` : null }));
  }
  return g;
}
function toggle(on, onclick) { return h("button", { class: "sw", role: "switch", "aria-checked": on ? "true" : "false", onclick }); }

// Matrix tile. What the user picks here is an override (no Save needed); the choice is kept in
// TILE_MX while a second control is open, because tiles are redrawn whenever their state changes.
const TILE_MX = {}, TILE_ARG = {};
const MX_NOW = ["auto", "clock", "status", "ip", "off"];
function mxInfo(id) { return (ST && ST.mx && ST.mx[id]) || { mode: "text", auto: true, left: 0 }; }
function mxKinds(mode) {          // device types a matrix can show; a bar needs a number
  const def = META.types.led_matrix.props.find(p => p.key === "source") || {};
  const kinds = def.kinds || [], numeric = (META.entity_fields || {}).get_value || kinds;
  return mode === "bar" ? kinds.filter(k => numeric.includes(k)) : kinds;
}
function mxChip(id) {
  const mi = mxInfo(id);
  return mi.auto ? null : h("span", { class: "chip mxchip" }, t("mx.changed") + (mi.left > 0 ? " · " + mi.left + " " + t("sys.u.s") : ""));
}
function mxTile(el, c) {
  const mi = mxInfo(c.id), mm = META.matrix || {};
  const modes = mm.modes && mm.modes.length ? mm.modes : ["text", "off"];
  let pend = TILE_MX[c.id];
  if (pend && pend.t && (Date.now() - pend.t > 2500 || (pend.m === "auto" ? mi.auto : !mi.auto && mi.mode === pend.m))) { delete TILE_MX[c.id]; pend = null; }
  const pick = pend ? pend.m : mi.auto ? "auto" : mi.mode;
  const send = (action, value) => { command(c.id, action, value); TILE_MX[c.id] = { m: pick, t: Date.now() }; };
  const modeSel = h("select", { "aria-label": t("prop.mode.led_matrix"), onchange: e => {
    const m = e.target.value;
    TILE_MX[c.id] = { m, t: MX_NOW.includes(m) ? Date.now() : 0 };
    if (MX_NOW.includes(m)) command(c.id, "mode", m);
    redrawTile(c.id);
  } }, ["auto", ...modes].map(m => h("option", { value: m, selected: m === pick ? true : null }, t("mx." + m))));
  const sv = String(stOf(c.id).v || ""), shown = (/^\[(?:icon|anim|bar):([^\]]+)\]$/.exec(sv) || [])[1];
  const second = (list, label, action) => {
    const cur = TILE_ARG[c.id + "." + action] || (!mi.auto && mi.mode === action ? shown : "");
    return h("select", { "aria-label": t("mx." + action), onchange: e => { if (!e.target.value) return; TILE_ARG[c.id + "." + action] = e.target.value; send(action, e.target.value); } },
      h("option", { value: "" }, list.length ? t("mx.pick") : t("mx.nodev")), list.map(v => h("option", { value: v, selected: v === cur ? true : null }, label(v))));
  };
  const ctl = h("div", { class: "mxctl" }, modeSel);
  if (pick === "text") {
    const inp = h("input", { type: "text", placeholder: t("dash.text.ph"), "aria-label": t("dash.text.ph"), value: TILE_ARG[c.id + ".text"] || "",
      oninput: e => { TILE_ARG[c.id + ".text"] = e.target.value; }, onkeydown: e => { if (e.key === "Enter") send("text", inp.value); } });
    ctl.append(h("div", { class: "inline" }, inp, h("button", { class: "btn sm", onclick: () => send("text", inp.value) }, t("dash.show"))));
  } else if (pick === "icon") ctl.append(second(Object.keys(mm.icons || {}), v => t("icon." + v), "icon"));
  else if (pick === "anim") ctl.append(second(mm.anims || [], v => t("anim." + v), "anim"));
  else if (pick === "value" || pick === "bar") {
    const kinds = mxKinds(pick), devs = CFG.components.filter(x => kinds.includes(x.type));
    ctl.append(second(devs.map(x => x.id), v => (devs.find(x => x.id === v) || {}).name || v, pick));
  }
  el.append(h("div", { class: "mxrow" }, matrixView(frameOf(c.id)), mxChip(c.id)), ctl);
}
function tileSig(c) {             // everything a tile's picture depends on
  const s = stOf(c.id), a = HIST[c.id];
  return JSON.stringify([s.v, s.txt, ST && ST.boards && ST.boards[c.board], a ? a._t : 0,
    c.type === "led_matrix" ? [frameOf(c.id), mxInfo(c.id), TILE_MX[c.id]] : 0]);
}
function tile(c) {
  const s = stOf(c.id), v = s.v, ty = META.types[c.type], p = propsOf(c);
  const b = boardById(c.board, CFG), pin = pinOf(b, c.pin);
  const bs = (ST && ST.boards && ST.boards[c.board]) || {};
  const off = ty.cap && !bs.online;
  const el = h("div", { class: "tile" + (off ? " offline" : ""), "data-id": c.id, "data-sig": tileSig(c) },
    h("div", { class: "tt" }, h("span", { class: "tag f-" + (ty.cap || "virt") }, ty.tag), h("span", { class: "tname" }, c.name),
      h("span", { class: "where" }, pin ? pin.label : "")));
  if (c.type === "binary_input") {
    el.append(h("div", { class: "line" }, h("span", { class: "lamp" + (v ? " on" : "") }), h("span", { class: "big" }, v == null ? "--" : (v ? t("on") : t("off")))));
    if (/simulated/.test(bs.text || "")) {
      const press = val => api("/api/sim", { board: c.board, pin: c.pin, value: val });
      // released on the document: the tile itself is redrawn while the button is held
      const down = () => { press(p.invert ? 0 : 1); document.addEventListener("pointerup", () => press(p.invert ? 1 : 0), { once: true }); };
      el.append(h("button", { class: "btn sm", onpointerdown: down }, t("dash.hold")));
    }
  } else if (c.type === "switch_output" || c.type === "virtual_switch") {
    el.append(h("div", { class: "line" }, toggle(v, () => command(c.id, "toggle")), h("span", { class: "big" }, v ? t("on") : t("off"))));
  } else if (c.type === "pwm_output") {
    const on = v && v.on, lv = v ? Math.round(v.level) : 0;
    el.append(h("div", { class: "line" }, toggle(on, () => command(c.id, "toggle")), h("span", { class: "big" }, on ? lv + "%" : t("off"))),
      h("input", { type: "range", min: 0, max: 100, value: lv, "aria-label": c.name, onchange: e => command(c.id, "set", +e.target.value) }));
  } else if (c.type === "dac_output") {
    const vref = (modelOf(b) || {}).vref || 3.3;
    el.append(h("div", { class: "big" }, (v || 0).toFixed(2), h("span", { class: "unit" }, " V")),
      h("input", { type: "range", min: 0, max: vref, step: 0.01, value: v || 0, "aria-label": c.name, onchange: e => command(c.id, "set", +e.target.value) }));
  } else if (c.type === "analog_sensor" || c.type === "pulse_counter") {
    el.append(h("div", { class: "big" }, s.txt || "--", h("span", { class: "unit" }, " " + (p.unit || ""))), sparkline(c.id));
  } else if (c.type === "rgb_led") {
    el.append(h("div", { class: "swatches" }, META.colors.map(k => h("button", { class: "swatch", title: t("color." + k), "aria-label": t("color." + k),
      "aria-pressed": v === k ? "true" : "false", style: "background:" + RGB_CSS[k], onclick: () => command(c.id, "set", k) }))));
  } else if (c.type === "led_matrix") mxTile(el, c);
  return el;
}
const FOCUSABLE = "button,input,select,textarea,a[href]";
function redrawTile(id) {         // replaces one tile and keeps the keyboard focus on the same control
  const old = document.querySelector('#main .tile[data-id="' + id + '"]'), c = CFG.components.find(x => x.id === id);
  if (!old || !c) return;
  const idx = [...old.querySelectorAll(FOCUSABLE)].indexOf(document.activeElement), nw = tile(c);
  old.replaceWith(nw);
  const f = idx >= 0 ? nw.querySelectorAll(FOCUSABLE)[idx] : null;
  if (f) f.focus({ preventScroll: true });
}
function dashSig() {              // what the dashboard's frame depends on; tiles and the system panel are patched in place
  return JSON.stringify([dirty(), CFG.boards.map(b => !!(ST && ST.boards && (ST.boards[b.id] || {}).online)), ST ? ST.node : 0,
    ST ? Object.keys(ST.vars || {}).length > 0 : 0]);
}
function varChips() { return Object.entries((ST && ST.vars) || {}).map(([k, v]) => h("span", { class: "var" }, k + " = " + v)); }
function refreshDash() {
  const main = $("#main");
  if (main.dataset.dash !== dashSig()) { if (!typingIn(main)) render(); return; }
  for (const el of main.querySelectorAll(".tile[data-id]")) {
    const c = CFG.components.find(x => x.id === el.dataset.id);
    if (!c || el.dataset.sig === tileSig(c)) continue;
    if (typingIn(el)) {           // leave the control alone; a matrix still gets its live picture
      if (c.type === "led_matrix") {
        const row = el.querySelector(".mxrow");
        if (row) row.replaceChildren(matrixView(frameOf(c.id)), mxChip(c.id) || "");
      }
      continue;
    }
    redrawTile(c.id);
  }
  const vb = $("#varbox");
  if (vb) vb.replaceChildren(...varChips());
}
function viewDash(m) {
  m.dataset.dash = dashSig();
  m.append(sysPanel());
  sysPatch();
  if (!CFG.components.length) {
    m.append(h("div", { class: "panel empty" }, h("p", {}, t("dash.empty")), h("button", { class: "btn primary", onclick: () => go("boards") }, t("dash.empty.btn"))));
    return;
  }
  if (dirty()) m.append(h("div", { class: "note", style: "margin:0 0 16px" }, t("dash.unsaved")));
  const groups = CFG.boards.map(b => [b, CFG.components.filter(c => c.board === b.id && META.types[c.type].cap)]);
  for (const [b, list] of groups) {
    if (!list.length) continue;
    const on = ST && ST.boards && ST.boards[b.id] && ST.boards[b.id].online;
    m.append(h("div", { class: "group-title" }, h("span", { class: "dot " + (on ? "ok" : "err") }), h("h3", {}, b.name || b.id),
      h("span", { class: "small muted" }, modelOf(b) ? modelOf(b).label : "")), h("div", { class: "tiles" }, list.map(tile)));
  }
  const virt = CFG.components.filter(c => !META.types[c.type].cap);
  if (virt.length) m.append(h("div", { class: "group-title" }, h("h3", {}, t("dash.virtual"))), h("div", { class: "tiles" }, virt.map(tile)));
  const vars = varChips();
  if (vars.length) m.append(h("div", { class: "group-title" }, h("h3", {}, t("dash.vars"))), h("div", { class: "vars", id: "varbox" }, vars));
}
function viewNode(m) {
  const n = (ST && ST.node) || {};
  m.dataset.dash = dashSig();
  m.append(sysPanel());
  sysPatch();
  m.append(h("div", { class: "panel", style: "max-width:640px" }, h("h2", {}, t("node.title")),
    h("p", { style: "margin:10px 0 14px" }, t("node.body", CFG.device.master_host || "?", CFG.device.node)),
    h("div", { class: "stat" }, h("span", { class: "dot " + (n.online ? "ok" : "warn") }), n.online ? t("node.connected") : t("node.waiting")),
    h("div", { class: "stat", style: "margin-top:6px" }, h("span", { class: "dot " + (n.mcu ? "ok" : "err") }), t("node.mcu"))));
}

// ------------------------------------------------------------------ boards & pins
function newId(prefix, taken) { let n = 1; while (taken(prefix + n)) n++; return prefix + n; }
function addComp(type, bid, pid) {
  const id = newId(ID_PREFIX[type] || "dev", x => !!compById(x));
  const c = { id, type, name: typeLabel(type) + " " + id.replace(/^\D+/, ""), board: bid, pin: pid, props: {} };
  const m = modelOf(boardById(bid));
  if (type === "analog_sensor" && m && m.vref !== 3.3) c.props.in_max = m.vref;
  const pn = pinOf(boardById(bid), pid);     // no internal resistor on this pin: do not pretend there is a pull-up
  if (type === "binary_input" && pn && pn.notes.some(n => n === "in_only" || n === "no_pullup")) c.props.pull = "none";
  comps().push(c);
  SEL = { comp: id };
  changed(); render();
}
function scriptsText() { return JSON.stringify((DRAFT.scripts || {}).workspace || {}); }
const SCRIPT_REFS = ["ENT", "SRC"];          // block fields that hold a device id
function removeComp(id) {
  const used = SCRIPT_REFS.some(f => scriptsText().includes('"' + f + '":"' + id + '"'))
    || comps().some(c => c.type === "led_matrix" && c.id !== id && (c.props || {}).source === id);
  if (used && !confirm(t("pin.inuse", id))) return;
  DRAFT.components = comps().filter(c => c.id !== id);
  SEL = null;
  changed(); render();
}
function renameComp(c, nv) {
  const old = c.id;
  c.id = nv;
  let s = scriptsText();
  for (const f of SCRIPT_REFS) s = s.split('"' + f + '":"' + old + '"').join('"' + f + '":"' + nv + '"');
  DRAFT.scripts = DRAFT.scripts || {};
  DRAFT.scripts.workspace = JSON.parse(s);
  for (const m of comps()) if (m.type === "led_matrix" && m.props && m.props.source === old) m.props.source = nv;
  SEL = { comp: nv };
}
// A setup that lost the devices `ids` (old files: the UNO Q bottom connector) must not name them any
// more, or every later save is refused. Twin of qh_engine._unhook / qh_script.disable_scripts: scripts
// that use them are switched off like "Disable Block" on their first block (kept, to be repaired in
// the Blocks tab), a matrix that showed one goes back to its text. Returns the number of scripts.
function blockUses(block, ids) {
  for (let b = block; b; b = (b.next || {}).block) {
    if (SCRIPT_REFS.some(f => ids.includes((b.fields || {})[f]))) return true;
    for (const slot of Object.values(b.inputs || {})) if (slot && blockUses(slot.block || slot.shadow, ids)) return true;
  }
  return false;
}
function unhookComps(cfg, ids) {
  ids = ids.filter(id => typeof id === "string" && !cfg.components.some(c => c && c.id === id));
  if (!ids.length) return 0;
  let off = 0;
  const tops = (((cfg.scripts || {}).workspace || {}).blocks || {}).blocks;
  for (const top of Array.isArray(tops) ? tops : []) {
    const on = top && /^ev_/.test(top.type || "") && top.enabled !== false && !(top.disabledReasons || []).length;
    if (on && blockUses(top, ids)) { top.disabledReasons = ["MANUALLY_DISABLED"]; off++; }
  }
  for (const c of cfg.components) {
    if (!c || c.type !== "led_matrix" || !c.props || !ids.includes(c.props.source)) continue;
    c.props.source = "";
    if (c.props.mode === "value" || c.props.mode === "bar") c.props.mode = "text";
  }
  return off;
}
// One pin as the user sees it: its device, whether the link owns it, and the button contract shared by
// the board drawing and the list view (class pin/used/reserved, data-pin, aria-pressed, title, click).
const WARN_NOTES = ["strap", "boot_low", "boot_btn", "in_only"];
function pinInfo(b, pid, reserved) {
  const p = pinOf(b, pid);
  if (!p) return null;
  const c = compAt(b.id, pid), res = reserved[pid];
  const sel = !!(SEL && ((SEL.comp && c && SEL.comp === c.id) || (!SEL.comp && SEL.pin === pid && SEL.board === b.id)));
  const warn = (p.notes || []).some(n => WARN_NOTES.includes(n));
  return { p, c, res, sel, cls: "pin" + (c ? " used" : "") + (res ? " reserved" : "") + (warn ? " warn" : ""),
    attrs: { "aria-pressed": sel ? "true" : "false", "data-pin": String(pid),
      title: pinName(p) + (res ? " · " + t("res." + res) : c ? " · " + c.name : " · " + p.caps.map(k => t("cap." + k)).join(", ")),
      onclick: () => { SEL = c ? { comp: c.id } : { board: b.id, pin: pid }; render(); } } };
}
function fillSock(sock, c, mxClass) {         // the live part of a used pad: matrix picture or LED colour
  if (c.type === "led_matrix") sock.replaceChildren(matrixView(frameOf(c.id), mxClass || "mxmini"));
  else if (c.type === "rgb_led") sock.style.background = RGB_CSS[stOf(c.id).v] || "";
}
function sockEl(c, mxClass, bare) {
  const sock = h("span", { class: "sock" + (c ? " f-" + META.types[c.type].cap : "") }, c && !bare ? META.types[c.type].tag : "");
  if (c) fillSock(sock, c, mxClass);
  return sock;
}
const valText = c => (c.type === "led_matrix" || c.type === "rgb_led" ? "" : stOf(c.id).txt || "");
function pinCell(b, pid, reserved) {          // list view
  const pi = pinInfo(b, pid, reserved);
  if (!pi) return null;
  const { p, c, res } = pi;
  return h("button", Object.assign({ class: pi.cls }, pi.attrs), h("span", { class: "pl" }, p.label), sockEl(c),
    c || res ? null : h("span", { class: "caps" }, p.caps.map(k => h("i", { class: "f-" + k }))),
    h("span", { class: "nm" }, c ? c.name : res ? t("res." + res) : ""), c ? h("span", { class: "val" }, valText(c)) : null);
}
// The board drawing. Unit = one header pitch; data and rules: model.board (python/qh_boards.py).
const PAD = 0.43, FLAG_GAP = 0.25;            // half a pad, and the gap between the board edge and a name
const QUIET_HEADERS = ["TOP", "BOTTOM", "LEFT", "RIGHT"];      // names that are not printed on the board
function headerEls(pcb, b, hd, reserved, bd) {
  const pins = hd.pins || [], cols = hd.cols || pins.length || 1, rows = Math.ceil(pins.length / cols), side = hd.side;
  const box = (cls, x, y, w, hh, kids) => h("div", { class: cls, style: `--x:${x};--y:${y};--pw:${w};--ph:${hh}` }, kids || []);
  pcb.append(box("hstrip", hd.x - 0.5, hd.y - 0.5, cols, rows));
  if (hd.name && !QUIET_HEADERS.includes(hd.name) && side !== "left" && side !== "right") {
    const y = side === "bottom" ? hd.y - 0.5 - 1.85 : side === "top" ? hd.y + rows - 0.5 + 1.35 : hd.y - 0.5 - 0.55;
    pcb.append(box("hname", hd.x - 0.5, y, cols, 0.5, [hd.name]));
  }
  pins.forEach((e, i) => {
    const col = i % cols, row = Math.floor(i / cols), x = hd.x + col, y = hd.y + row;
    const roomRight = bd.w - x - PAD;
    // lab: where the silk label is printed (board side). flag: where the device name goes (outer side).
    let lab = "", flag = "fo-n", fo = 0;
    const outer = side === "right" ? cols - 1 : 0, mate = pins[row * cols + outer];
    // a row of two identical pads (5V 5V, GND GND at the ends of the Mega's block) is labelled once, on the outer side
    const twinPad = (side === "right" || side === "left") && col !== outer && e && typeof e === "object" && mate && typeof mate === "object" && mate.pad === e.pad;
    if (side === "top") {
      if (row === rows - 1) lab = "l-b";
      if (row === 0) { flag = "fo-t"; fo = y; }
    } else if (side === "bottom") {
      if (row === 0) lab = "l-a";
      if (row === rows - 1) { flag = "fo-b"; fo = bd.h - y; }
    } else if (side === "right") {
      lab = twinPad ? "" : col === 0 ? "l-l" : col === cols - 1 ? (roomRight >= 1.4 ? "l-r" : "l-rv") : "";
      if (col === cols - 1) { flag = "fo-r"; fo = bd.w - x; }
    } else if (side === "left") {
      lab = twinPad ? "" : col === cols - 1 ? "l-r" : col === 0 ? "l-l" : "";
      if (col === 0) { flag = "fo-l"; fo = x; }
    } else if (rows === 1) lab = "l-b";
    else lab = col === 0 ? "l-l" : col === cols - 1 ? (roomRight >= 1.4 ? "l-r" : "l-rv") : "";
    const style = `--x:${x};--y:${y};--fo:${Math.max(0, fo - PAD) + FLAG_GAP}`;
    if (e && typeof e === "object") {         // inert pad: power, ground, reset, or a copy of another pin
      const txt = String(e.pad == null ? "" : e.pad);
      const kind = /^GND$/i.test(txt) ? " gnd" : /^(3V3|5V|VIN|VBATT|VBAT|VCC|VBUS)$/i.test(txt) ? " pwr" : "";
      const twin = e.same != null ? pinInfo(b, e.same, reserved) : null;
      pcb.append(h("span", { class: "bpad " + lab + kind + (twin ? " same" + (twin.sel ? " sel" : "") + (twin.c ? " used" : "") : ""), style,
        title: twin ? t("boards.pad.same", txt, twin.p.label) : t("boards.pad", txt) },
        h("span", { class: "sock" + (twin && twin.c ? " f-" + META.types[twin.c.type].cap : "") }), h("span", { class: "pl" }, txt)));
      return;
    }
    const pi = pinInfo(b, e, reserved);
    if (!pi) return;
    pcb.append(h("button", Object.assign({ class: pi.cls + " bpin " + lab + " " + flag, style }, pi.attrs),
      sockEl(pi.c), h("span", { class: "pl" }, pi.p.label),
      pi.c || pi.res ? null : h("span", { class: "caps" }, pi.p.caps.map(k => h("i", { class: "f-" + k }))),
      pi.c || pi.res ? h("span", { class: "fl" }, h("span", { class: "nm" }, pi.c ? pi.c.name : t("res." + pi.res)),
        pi.c ? h("span", { class: "val" }, valText(pi.c)) : null) : null));
  });
}
function partEl(b, part, reserved, bd) {
  const w = part.w || 1, hh = part.h || 1, grid = `;--cols:${part.cols || 13};--rows:${part.rows || 8}`;
  const style = `--x:${part.x};--y:${part.y};--pw:${w};--ph:${hh}` + (part.type === "matrix" ? grid : "");
  const pi = part.pin != null ? pinInfo(b, part.pin, reserved) : null;
  if (pi) {                                   // an on-board device that can be configured: behaves like a pin
    const sock = sockEl(pi.c, "mxpart", true);
    if (part.type === "matrix" && !pi.c) sock.append(matrixView("", "mxpart"));
    return h("button", Object.assign({ class: pi.cls + " bpart t-" + part.type, style }, pi.attrs), sock,
      h("span", { class: "pcap" }, h("span", { class: "pl" }, pi.p.label), pi.c ? h("span", { class: "nm" }, pi.c.name) : null,
        pi.c ? h("span", { class: "val" }, valText(pi.c)) : null));
  }
  const label = part.label || "";
  if (part.type === "matrix") {
    const n = (part.cols || 13) * (part.rows || 8);
    return h("div", { class: "part t-matrix", style, "aria-hidden": "true" }, h("div", { class: "mxpart" }, Array.from({ length: n }, () => h("i", {}))));
  }
  const outside = part.type === "btn" || part.type === "led";      // too small to hold their own label
  const cls = "part t-" + part.type + (part.type === "module" && w / hh > 1.3 ? " ant" : "")
    + (outside ? (part.y + hh / 2 >= bd.h / 2 ? " lab-a" : " lab-b") : "");
  return h("div", { class: cls, style, title: label || null }, label ? h("span", { class: "plab" }, label) : null);
}
function boardView(b, model, reserved) {
  const bd = model.board, hs = bd.headers || [], sides = new Set(hs.map(x => x.side));
  // room around the outline: USB plugs on the left, device names beyond every edge that has a header
  const ml = sides.has("left") ? 5 : 3.2, mr = sides.has("right") ? 5 : 1, mt = sides.has("top") ? 4.8 : 1, mb = sides.has("bottom") ? 4.8 : 1;
  const pcb = h("div", { class: "bd", style: `--w:${bd.w};--h:${bd.h}` });
  for (const part of bd.parts || []) pcb.append(partEl(b, part, reserved, bd));
  for (const hd of hs) headerEls(pcb, b, hd, reserved, bd);
  return h("div", { class: "boardwrap" }, h("div", { class: "board m-" + b.model, role: "group", "aria-label": model.label,
    style: `--tw:${ml + bd.w + mr};--th:${mt + bd.h + mb};--ml:${ml};--mt:${mt}` }, pcb));
}
function listView(b, model, reserved) {
  const pcb = h("div", { class: "pcb" });
  for (const [group, pins] of model.layout || [])
    pcb.append(h("div", { class: "strip-title" }, t("group." + group)), h("div", { class: "strip" }, pins.map(pid => pinCell(b, pid, reserved))));
  return pcb;
}
function linkSummary(b) {
  const l = b.link || {};
  if (l.type === "i2c") return t("link.i2c") + " 0x" + (l.address || 16).toString(16).toUpperCase() + " · " + t("link.bus." + (l.bus || "wire"));
  if (l.type === "uart") return t("link.uart") + " · " + (l.baud || 115200);
  if (l.type === "usb") return t("link.usb") + (l.port && l.port !== "auto" ? " · " + l.port : "");
  return t("link." + l.type);
}
// Boards that answer but are not in the setup (ST.discovered): one note each, with Add and Ignore.
function foundIgnored() {
  try { const a = JSON.parse(lsGet("qhome.found.ignored", "[]")); return Array.isArray(a) ? a : []; } catch (e) { return []; }
}
function foundInDraft(d) {
  return DRAFT.boards.some(b => (d.link === "wifi" ? b.id === d.id : (b.link || {}).type === "usb" && b.link.port === d.port));
}
function foundAll() { return ST && !isNode() && Array.isArray(ST.discovered) ? ST.discovered.filter(d => d && d.key && !foundInDraft(d)) : []; }
function foundList() { const ign = foundIgnored(); return foundAll().filter(d => !ign.includes(d.key)); }
function updateBadge() {
  const el = $("#navBadge");
  if (!el || !META || !DRAFT) return;
  const n = foundList().length;
  el.textContent = String(n);
  el.hidden = !n;
}
function foundNote(d) {
  const m = d.model == null ? null : META.models[d.model], where = d.link === "wifi" ? d.id : d.port;
  let text, add = null;
  if (d.model == null) text = t("found.silent", where);
  else if (!m) text = t("found.unknown", d.model);
  else {
    text = d.link === "wifi" ? t("found.wifi", m.label, d.id) : t("found.usb", m.label, d.port);
    const preset = d.link === "wifi" ? { id: d.id, name: d.id, model: d.model, link: { type: "wifi" } }
      : { model: d.model, name: m.label, link: { type: "usb", port: d.port } };
    add = h("button", { class: "btn sm primary", onclick: () => boardDialog(null, preset) }, t("found.add"));
  }
  return h("div", { class: "note info found", "data-key": d.key }, h("span", { class: "ftxt" }, text, helpHint("found")), add,
    h("button", { class: "btn sm", onclick: () => { lsSet("qhome.found.ignored", JSON.stringify([...new Set([...foundIgnored(), d.key])])); fillFound(); updateBadge(); } }, t("found.ignore")));
}
function fillFound() {            // rebuilt in place by the live update: a redraw would close the inspector
  const box = $("#foundbox");
  if (!box) return;
  const list = foundList(), hidden = foundAll().length - list.length;
  const sig = JSON.stringify([list.map(d => [d.key, d.model]), hidden]);
  if (box.dataset.sig === sig) return;
  box.dataset.sig = sig;
  box.replaceChildren(...list.map(foundNote), hidden ? h("button", { class: "btn sm ghost", onclick: () => { lsSet("qhome.found.ignored", "[]"); fillFound(); updateBadge(); } },
    t("found.ignored", hidden)) : "");
}
function viewBoards(m) {
  if (!boardById(SELB)) SELB = DRAFT.boards.length ? DRAFT.boards[0].id : null;
  m.append(h("div", { id: "foundbox" }));
  fillFound();
  const tabs = h("div", { class: "tabs", role: "tablist" }, DRAFT.boards.map(b => {
    const on = ST && ST.boards && ST.boards[b.id] && ST.boards[b.id].online;
    return h("button", { role: "tab", "data-bid": b.id, "aria-selected": b.id === SELB ? "true" : "false", onclick: () => { SELB = b.id; SEL = null; render(); } },
      h("span", { class: "dot " + (on ? "ok" : "err") }), b.name || b.id);
  }), h("button", { role: "tab", "aria-selected": "false", id: "bAddBoard", onclick: () => boardDialog(null) }, "+ " + t("boards.add")));
  m.append(tabs);
  const b = boardById(SELB);
  if (!b) {
    m.append(h("div", { class: "panel empty" }, h("p", {}, t("boards.none")), h("button", { class: "btn primary", onclick: () => boardDialog(null) }, t("boards.add"))));
    return;
  }
  const model = modelOf(b), st = (ST && ST.boards && ST.boards[b.id]) || {}, reserved = reservedPins(b);
  const left = h("div", {});
  left.append(h("div", { class: "boardmeta" }, h("h2", {}, b.name || b.id), h("span", { class: "chip" }, model.label),
    h("span", { class: "chip" }, linkSummary(b)),
    h("span", { class: "chip", id: "bstat" }, h("span", { class: "dot " + (st.online ? "ok" : "err") }), st.online ? t("online") : (st.text || t("offline"))),
    h("span", { class: "grow" }), h("button", { class: "btn sm", onclick: () => boardDialog(b) }, t("boards.edit")),
    h("button", { class: "btn sm danger", onclick: () => removeBoard(b) }, t("boards.remove"))));
  if (st.model && st.model !== b.model && META.models[st.model])
    left.append(h("div", { class: "note" }, t("boards.mismatch", META.models[st.model].label)));
  const drawn = !!model.board && lsGet("qhome.boardview", "board") !== "list";
  const caps = [...new Set(model.pins.flatMap(p => p.caps))];
  const swatch = k => h("span", { class: "tag f-" + k, style: "min-width:14px;height:8px;padding:0" });
  left.append(h("div", { class: "viewbar" },
    h("div", { class: "legend" }, h("span", {}, t("boards.legend")), caps.map(k => h("span", {}, swatch(k), t("cap." + k))),
      model.pins.some(p => (p.notes || []).some(n => WARN_NOTES.includes(n))) ? h("span", {}, h("span", { class: "warnmark" }), t("boards.legend.boot")) : null),
    model.board ? h("div", { class: "seg viewsw", role: "group", "aria-label": t("boards.view") }, [["board", drawn], ["list", !drawn]].map(([k, on]) =>
      h("button", { "aria-pressed": on ? "true" : "false", "data-view": k, onclick: () => { lsSet("qhome.boardview", k); render(); } }, t("boards.view." + k)))) : null));
  left.append(drawn ? boardView(b, model, reserved) : listView(b, model, reserved));
  const virt = comps().filter(c => !META.types[c.type].cap);
  left.append(h("div", { class: "virtrow" }, h("span", { class: "small muted" }, t("boards.virtual")),
    virt.map(c => h("button", { class: "vchip", "aria-pressed": SEL && SEL.comp === c.id ? "true" : "false", onclick: () => { SEL = { comp: c.id }; render(); } },
      h("span", { class: "tag" }, META.types[c.type].tag), c.name)),
    h("button", { class: "btn sm ghost", onclick: () => addComp("virtual_switch", null, null) }, "+ " + t("boards.virtual.add"))));
  m.append(h("div", { class: "boardgrid" }, left, h("div", { class: "panel inspector" }, inspector(b, reserved))));
}
function pinNotes(b, p) {
  const model = modelOf(b);
  const items = (p.notes || []).map(n => t("note." + n));
  items.push(t(model.logic === 5 ? "note.logic5" : "note.logic33"));
  return h("ul", { class: "pinnotes" }, items.map(x => h("li", {}, x)));
}
// A field label, with the round "?" when the help has a hint for one of the keys.
function lab(text, ...hintKeys) {
  const hint = helpHint(...hintKeys);
  return hint ? h("div", { class: "lbl" }, h("label", {}, text), hint) : h("label", {}, text);
}
function optLabel(def, o, type) { // names of dropdown choices; matrix choices use the words of the dashboard
  const special = type === "led_matrix" ? { mode: "mx.", anim: "anim.", icon: "icon." }[def.key] : null;
  return special ? tOr(special + o, o) : tOr("opt." + def.key + "." + o, o || t("none"));
}
function field(def, obj, type, rerender, self) {
  const v = obj[def.key] ?? def.default;
  const label = tOr("prop." + def.key + "." + type, t("prop." + def.key));
  const hints = ["prop." + def.key + "." + type, "prop." + def.key];
  if (def.type === "bool") {
    const box = h("label", { class: "check" }, h("input", { type: "checkbox", checked: !!v, onchange: e => { obj[def.key] = e.target.checked; changed(); } }), label);
    const hint = helpHint(...hints);
    return hint ? h("div", { class: "lbl self" }, box, hint) : box;
  }
  let inp;
  if (def.type === "select") {
    inp = h("select", { onchange: e => { obj[def.key] = e.target.value; changed(); if (rerender) render(); } },
      def.options.map(o => h("option", { value: o, selected: o === v ? true : null }, optLabel(def, o, type))));
  } else if (def.type === "device") {         // a device id or ""; choices: devices of the listed types, except this one
    const mode = self ? String(propsOf(self).mode) : "";
    const kinds = type === "led_matrix" && def.key === "source" ? mxKinds(mode) : def.kinds || [];
    const list = comps().filter(c => kinds.includes(c.type) && c !== self);
    inp = h("select", { onchange: e => { obj[def.key] = e.target.value; changed(); } },
      h("option", { value: "", selected: !v ? true : null }, list.length ? t("mx.pick") : t("mx.nodev")),
      list.map(c => h("option", { value: c.id, selected: c.id === v ? true : null }, c.name || c.id)),
      v && !list.some(c => c.id === v) ? h("option", { value: v, selected: true }, t("blocks.missing", v)) : null);
  } else {
    inp = h("input", { type: def.type === "number" ? "number" : "text", value: v, min: def.min, max: def.max, step: def.step || "any",
      oninput: e => { obj[def.key] = def.type === "number" ? (e.target.value === "" ? def.default : +e.target.value) : e.target.value; changed(); } });
  }
  return h("div", {}, lab(label, ...hints), inp);
}
function inspector(b, reserved) {
  const c = SEL && SEL.comp ? compById(SEL.comp) : null;
  if (!c) {
    const p = SEL && SEL.board === b.id ? pinOf(b, SEL.pin) : null;
    if (!p) return [h("h3", {}, t("nav.boards")), h("p", { class: "muted" }, t("pin.select")), h("div", { class: "note info" }, t("pin.tip"))];
    if (reserved[p.id]) return [h("h3", {}, pinName(p)), h("p", { class: "muted" }, t("pin.reserved", p.label)), pinNotes(b, p)];
    const types = Object.entries(META.types).filter(([, ty]) => ty.cap && p.caps.includes(ty.cap));
    return [h("h3", {}, t("pin.free", pinName(p))), h("p", { class: "muted small" }, t("pin.free.hint")),
      h("div", { class: "choices" }, types.map(([k, ty]) => h("button", { class: "choice", onclick: () => addComp(k, b.id, p.id) },
        h("span", { class: "tag f-" + ty.cap }, ty.tag), h("b", {}, typeLabel(k)), h("span", { class: "d" }, t("type." + k + ".d"))))),
      pinNotes(b, p)];
  }
  const ty = META.types[c.type], cb = boardById(c.board);
  const p = cb ? pinOf(cb, c.pin) : null;
  c.props = c.props || {};
  const f = h("div", { class: "form" });
  f.append(h("h3", {}, h("span", { class: "tag f-" + (ty.cap || "virt") }, ty.tag), " ", typeLabel(c.type), p ? h("span", { class: "onpin" }, pinName(p)) : null));
  f.append(h("label", {}, t("pin.name")), h("input", { type: "text", value: c.name, oninput: e => { c.name = e.target.value; changed(); } }));
  f.append(lab(t("pin.id"), "pin.id"), h("input", { type: "text", value: c.id, spellcheck: "false", onchange: e => {
    const nv = e.target.value.trim();
    if (!ID_RE.test(nv)) { toast(t("pin.id.bad")); e.target.value = c.id; return; }
    if (compById(nv) && nv !== c.id) { toast(t("pin.id.used")); e.target.value = c.id; return; }
    renameComp(c, nv); changed(); render();
  } }));
  if (ty.cap && cb) {
    const res = reservedPins(cb);
    const opts = modelOf(cb).pins.filter(x => x.caps.includes(ty.cap) && !res[x.id]).map(x => {
      const u = compAt(cb.id, x.id), taken = u && u.id !== c.id;
      return h("option", { value: JSON.stringify(x.id), selected: x.id === c.pin ? true : null, disabled: taken ? true : null }, pinName(x) + (taken ? " (" + u.name + ")" : ""));
    });
    f.append(h("label", {}, t("pin.pin")), h("select", { onchange: e => { c.pin = JSON.parse(e.target.value); changed(); render(); } }, opts));
  }
  const pr = propsOf(c);
  for (const def of ty.props) {
    if (def.show) { const [k, want] = def.show.split("="); if (!String(want).split("|").includes(String(pr[k]))) continue; }
    f.append(field(def, c.props, c.type, ty.props.some(x => x.show && x.show.startsWith(def.key + "=")), c));
  }
  if (p) f.append(pinNotes(cb, p));
  f.append(h("div", { style: "margin-top:16px;display:flex;gap:8px" }, h("button", { class: "btn danger", onclick: () => removeComp(c.id) }, t("remove")),
    h("button", { class: "btn", onclick: () => { SEL = null; render(); } }, t("close"))));
  return [f];
}
function removeBoard(b) {
  const n = comps().filter(c => c.board === b.id).length;
  if (!confirm(t("boards.remove.confirm", b.name || b.id, n))) return;
  DRAFT.components = comps().filter(c => c.board !== b.id);
  DRAFT.boards = DRAFT.boards.filter(x => x.id !== b.id);
  SELB = null; SEL = null;
  changed(); render();
}
function masterHost() {   // what another board should dial; "localhost" would point at itself
  return /^(localhost|127\.|\[?::1)/.test(location.hostname) ? t("fw.host") : location.hostname;
}
const FLASH_HELP = { unoq: "unoq", uno: "avr", nano: "avr", mega: "avr", r4m: "r4", r4w: "r4", nanor4: "r4", esp32: "esp32", esp32c3: "esp32c3", esp8266: "esp8266" };
function firmwareHelp(b) {
  const l = b.link || {}, box = h("div", {}), model = modelOf(b) || {};
  if (l.type === "local") return box;
  box.append(h("h3", { style: "margin-top:18px" }, t("fw.title")));
  if (META.sim) box.append(h("div", { class: "note info" }, t("wire.sim")));
  if (b.model === "unoq") {
    box.append(h("p", { class: "small" }, t("fw.node")), h("pre", { class: "code" }, t("fw.node.vals", b.id || "?", masterHost(), DRAFT.mqtt.port || 1883)));
  } else {
    const lines = { usb: ["#define QL_LINK  QL_USB", "#define QL_BAUD  " + (l.baud || 115200)],
      uart: ["#define QL_LINK  QL_UART", "#define QL_BAUD  " + (l.baud || 115200)],
      i2c: ["#define QL_LINK  QL_I2C", "#define QL_I2C_ADDRESS  0x" + (l.address || 16).toString(16).toUpperCase()],
      wifi: ["#define QL_LINK  QL_WIFI", '#define QL_BOARD_ID     "' + (b.id || "?") + '"', '#define QL_MASTER_HOST  "' + masterHost() + '"',
        "#define QL_MASTER_PORT  " + (DRAFT.mqtt.mode === "external" ? DRAFT.mqtt.ext_port : DRAFT.mqtt.port || 1883), '#define QL_WIFI_SSID    "..."', '#define QL_WIFI_PASS    "..."'] }[l.type] || [];
    box.append(h("p", { class: "small" }, t("fw.sat")), h("pre", { class: "code" }, lines.join("\n")));
  }
  let wire = t("wire." + l.type);
  if (l.type === "uart") {
    const [rx, tx] = (model.uart_pins || model.serial_pins || []).map(id => (model.pins || []).find(p => p.id === id));
    wire = [wire, rx && tx ? t("wire.uart.pins", pinName(rx), pinName(tx)) : null, t(model.logic === 3.3 ? "wire.uart.33" : "wire.uart.5v"), t("wire.uart.modules")].filter(Boolean).join(" ");
  }
  box.append(h("p", { class: "small muted", style: "margin-top:8px" }, wire));
  const flash = FLASH_HELP[b.model];
  if (flash && helpPage("boards")) box.append(h("p", { class: "small", style: "margin-top:8px" }, helpLink(t("fw.more"), "boards", flash)));
  return box;
}
function boardDialog(existing, preset) {
  const isNew = !existing;
  const hasLocal = DRAFT.boards.some(x => (x.link || {}).type === "local" && x !== existing);
  const b = existing ? clone(existing) : Object.assign({ id: "", name: "", model: "uno", link: { type: "usb", port: "auto" } }, clone(preset || {}));
  const slug = s => s.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^[^a-z]+/, "").replace(/_+$/, "").slice(0, 24);
  const fixedId = isNew && !!(preset && preset.id);        // a found Wi-Fi board: the id is in its firmware
  if (isNew && !b.id && b.name) { const base = slug(b.name); b.id = boardById(base) ? newId(base.slice(0, 22) + "_", x => !!boardById(x)) : base; }
  let idTouched = !isNew || fixedId;
  const modal = $("#modal");
  const closeDlg = () => { modal.hidden = true; modal.replaceChildren(); HINT_OPEN = null; };
  function linkTypes() { return modelOf(b).links.filter(k => k !== "local" || (!hasLocal && META.has_local)); }
  function setLink(type) {
    const used = DRAFT.boards.filter(x => x !== existing && (x.link || {}).type === "i2c").map(x => x.link.address);
    let addr = 16; while (used.includes(addr)) addr++;
    b.link = { local: { type: "local" }, usb: { type: "usb", port: "auto" }, uart: { type: "uart", baud: 115200 },
      i2c: { type: "i2c", bus: "wire", address: addr }, wifi: { type: "wifi" } }[type];
  }
  function draw() {
    if (!linkTypes().includes(b.link.type)) setLink(linkTypes()[0]);
    const l = b.link, f = h("div", { class: "form" });
    f.append(h("div", { class: "row" },
      h("div", {}, h("label", {}, t("board.name")), h("input", { type: "text", value: b.name, id: "bdName", oninput: e => {
        b.name = e.target.value;
        if (!idTouched) { b.id = slug(e.target.value); $("#bdId").value = b.id; }
      } })),
      h("div", {}, lab(t("board.id"), "board.id"), h("input", { type: "text", value: b.id, id: "bdId", disabled: isNew && !fixedId ? null : true, spellcheck: "false",
        title: fixedId ? t("found.id.fixed") : null, oninput: e => { idTouched = true; b.id = e.target.value.trim(); } }))));
    if (fixedId) f.append(h("p", { class: "small muted", style: "margin-top:6px" }, t("found.id.fixed")));
    f.append(h("label", {}, t("board.model")), h("select", { id: "bdModel", disabled: isNew ? null : true, onchange: e => { b.model = e.target.value; draw(); } },
      Object.entries(META.models).map(([k, mm]) => h("option", { value: k, selected: k === b.model ? true : null }, mm.label))));
    f.append(lab(t("board.link"), "board.link"), h("div", { class: "seg" }, linkTypes().map(k =>
      h("button", { "aria-pressed": l.type === k ? "true" : "false", "data-link": k, onclick: () => { setLink(k); draw(); } }, t("link." + k)))));
    if (l.type === "usb") {
      const names = ["auto", ...new Set([...PORTS.map(p => p.name), l.port].filter(x => x && x !== "auto"))];
      f.append(lab(t("link.port"), "link.port"), h("select", { id: "bdPort", onchange: e => { l.port = e.target.value; } },
        names.map(n => h("option", { value: n, selected: n === (l.port || "auto") ? true : null }, n === "auto" ? t("link.port.auto") : n))));
    } else if (l.type === "uart") {
      f.append(h("label", {}, t("link.baud")), h("select", { onchange: e => { l.baud = +e.target.value; draw(); } },
        [9600, 19200, 38400, 57600, 115200].map(n => h("option", { value: n, selected: n === l.baud ? true : null }, String(n)))));
    } else if (l.type === "i2c") {
      f.append(h("div", { class: "row" },
        h("div", {}, h("label", {}, t("link.bus")), h("select", { onchange: e => { l.bus = e.target.value; } },
          ["wire", "qwiic"].map(k => h("option", { value: k, selected: k === l.bus ? true : null }, t("link.bus." + k))))),
        h("div", {}, lab(t("link.addr"), "link.addr"), h("input", { type: "number", min: 8, max: 119, value: l.address, onchange: e => { l.address = +e.target.value; draw(); } }))));
    }
    f.append(firmwareHelp(b));
    const ok = () => {
      b.name = b.name.trim() || b.id;
      if (!ID_RE.test(b.id)) { toast(t("pin.id.bad")); return; }
      if (isNew && boardById(b.id)) { toast(t("pin.id.used")); return; }
      if (isNew) DRAFT.boards.push(b); else Object.assign(existing, b);
      const res = reservedPins(b);               // a link may claim pins that already had a job
      DRAFT.components = comps().filter(c => !(c.board === b.id && res[c.pin]));
      SELB = b.id; SEL = null;
      closeDlg(); changed(); render();
    };
    modal.replaceChildren(h("div", { class: "dialog", role: "dialog", "aria-modal": "true", "aria-label": t(isNew ? "boards.add" : "boards.edit") },
      h("h2", {}, t(isNew ? "boards.add" : "boards.edit")), f,
      h("div", { class: "actions" }, h("button", { class: "btn", onclick: closeDlg }, t("cancel")), h("button", { class: "btn primary", id: "bdOk", onclick: ok }, t(isNew ? "add" : "done")))));
  }
  modal.hidden = false;
  draw();
  api("/api/ports").then(p => { PORTS = p || []; if (!modal.hidden && b.link.type === "usb" && !typingIn(modal)) draw(); }).catch(() => {});
  setTimeout(() => { const n = $("#bdName"); if (n) n.focus(); }, 0);
}

// ------------------------------------------------------------------ blocks
async function showBlocks() {
  if (!BLOCKS_READY) {
    BLOCKS_READY = true;
    await QBlocks.init($("#blocklyDiv"), { comps: () => DRAFT.components, boards: () => DRAFT.boards, kinds: META.entity_fields,
      matrix: META.matrix || { icons: {}, anims: [] } }, META.colors,
      ws => { DRAFT.scripts = DRAFT.scripts || {}; DRAFT.scripts.workspace = ws; changed(); });
  }
  QBlocks.resize();
  QBlocks.load((DRAFT.scripts || {}).workspace);   // also refreshes device names inside blocks
  blocksFoot();
}
function blocksFoot() {
  $("#blocksFoot").replaceChildren(h("span", {}, t("blocks.hint")), h("span", { class: "grow" }),
    h("span", { class: "vars" }, varChips()),
    h("span", { class: "chip" }, h("span", { class: "dot " + (ST && ST.running ? "ok" : "") }), t("blocks.running", ST ? ST.running : 0)));
}

// ------------------------------------------------------------------ settings
// Browsers still report some old zone names.
const TZ_ALIAS = { "Asia/Calcutta": "Asia/Kolkata", "Europe/Kiev": "Europe/Kyiv", "Asia/Saigon": "Asia/Ho_Chi_Minh", "Asia/Katmandu": "Asia/Kathmandu",
  "Asia/Rangoon": "Asia/Yangon", "America/Buenos_Aires": "America/Argentina/Buenos_Aires", "Atlantic/Faeroe": "Atlantic/Faroe" };
function tzPicker(d) {
  const tzm = META.tz || {}, zones = tzm.zones || [], fixed = tzm.fixed || [], FIXED = "*";
  const cur = d.tz || tzm.default || "UTC";
  const isFixed = v => fixed.includes(v) || fixedMinutes(v) != null || !v.includes("/");
  const regions = [...new Set(zones.map(z => z.split("/")[0]))];
  const region = isFixed(cur) ? FIXED : cur.split("/")[0];
  if (region !== FIXED && !regions.includes(region)) regions.push(region);     // a saved zone this computer does not list
  const setTz = v => { d.tz = v; changed(); render(); };
  const nowFixed = () => { const n = ST && ST.time ? fixedName(ST.time.offset) : "UTC"; return fixed.includes(n) || !fixed.length ? n : "UTC"; };
  const regSel = h("select", { id: "tzRegion", onchange: e => setTz(e.target.value === FIXED ? nowFixed() : zones.find(z => z.startsWith(e.target.value + "/")) || cur) },
    regions.map(r => h("option", { value: r, selected: r === region ? true : null }, r)),
    h("option", { value: FIXED, selected: region === FIXED ? true : null }, t("set.tz.fixed")));
  const list = region === FIXED ? fixed.slice() : zones.filter(z => z.startsWith(region + "/"));
  if (!list.includes(cur)) list.push(cur);                 // never silently changed
  const cityName = v => (region === FIXED ? v : v.slice(region.length + 1).replace(/_/g, " ").replace(/\//g, " / "));
  const citySel = h("select", { id: "tzCity", onchange: e => setTz(e.target.value) }, list.map(v => h("option", { value: v, selected: v === cur ? true : null }, cityName(v))));
  let bz = "", fallback = false;
  try { bz = Intl.DateTimeFormat().resolvedOptions().timeZone || ""; } catch (e) { /* no Intl */ }
  if (!zones.includes(bz)) {
    if (TZ_ALIAS[bz] && zones.includes(TZ_ALIAS[bz])) bz = TZ_ALIAS[bz];
    else { fallback = bz.includes("/") && !bz.startsWith("Etc/"); bz = fixedName(-new Date().getTimezoneOffset()); }
  }
  const out = [h("div", { class: "row" }, h("div", {}, h("label", {}, t("set.tz.region")), regSel), h("div", {}, h("label", {}, t("set.tz.city")), citySel))];
  if (bz !== cur) out.push(h("button", { class: "btn sm", id: "tzBrowser", style: "margin-top:8px", onclick: () => { if (fallback) toast(t("set.tz.fallback", bz)); setTz(bz); } }, t("set.tz.browser", bz)));
  if (tzm.db === false) out.push(h("div", { class: "note" }, t("set.tz.nodb")));
  out.push(h("p", { class: "small", id: "tznow", style: "margin-top:10px" }), h("p", { class: "small muted", id: "tzprev", hidden: true }), h("div", { id: "tzwarn" }));
  return out;
}
function viewSettings(m) {
  const d = DRAFT.device, q = DRAFT.mqtt;
  const inp = (o, k, label, type, hint) => h("div", {}, lab(label, hint), h("input", { type: type || "text", value: o[k] ?? "", autocomplete: type === "password" ? "new-password" : "off",
    oninput: e => { o[k] = type === "number" ? +e.target.value : e.target.value; changed(); } }));
  const seg = (o, k, opts) => h("div", { class: "seg" }, opts.map(([v, label]) =>
    h("button", { "aria-pressed": (o[k] || opts[0][0]) === v ? "true" : "false", onclick: () => { o[k] = v; changed(); render(); } }, label)));
  const g = h("div", { class: "cols" });
  m.append(g);
  g.append(h("div", { class: "panel form" }, h("h3", {}, t("set.device")), inp(d, "name", t("set.name")), inp(d, "node", t("set.node"), null, "set.node"),
    inp(d, "web_password", t("set.pw"), "password", "set.pw"),
    h("p", { class: "small muted", style: "margin-top:10px" }, t("set.url", location.origin))));
  g.append(h("div", { class: "panel form", id: "tzpanel" }, h("h3", {}, t("set.tz"), helpHint("set.tz")), tzPicker(d)));
  if (META.has_local) {
    const role = h("div", { class: "panel form" }, h("h3", {}, t("set.role"), helpHint("set.role")), seg(d, "role", [["master", t("role.master")], ["node", t("role.node")]]),
      h("p", { class: "small muted", style: "margin-top:8px" }, t("role." + (d.role || "master") + ".d")));
    if (d.role === "node") role.append(inp(d, "master_host", t("set.master_host")), inp(d, "master_port", t("set.master_port"), "number"),
      h("div", { class: "row" }, inp(d, "master_user", t("set.master_user")), inp(d, "master_pass", t("set.master_pass"), "password")));
    g.append(role);
  }
  if (!isNode() && q) {
    const mq = h("div", { class: "panel form" }, h("h3", {}, t("set.mqtt"), helpHint("set.mqtt")),
      seg(q, "mode", [["internal", t("mqtt.internal")], ["external", t("mqtt.external")], ["off", t("mqtt.off")]]));
    if (q.mode === "internal") {
      mq.append(inp(q, "port", t("mqtt.port"), "number"), h("div", { class: "row" }, inp(q, "username", t("mqtt.user")), inp(q, "password", t("mqtt.pass"), "password")),
        h("div", { class: "note info" }, t("mqtt.ha", location.hostname, q.port || 1883)));
      if (!q.username) mq.append(h("div", { class: "note" }, t("mqtt.open")));
    } else if (q.mode === "external") {
      mq.append(h("div", { class: "row" }, inp(q, "host", t("mqtt.host")), inp(q, "ext_port", t("mqtt.port"), "number")),
        h("div", { class: "row" }, inp(q, "username", t("mqtt.user")), inp(q, "password", t("mqtt.pass"), "password")));
    }
    if (q.mode !== "off") mq.append(h("label", { class: "check" }, h("input", { type: "checkbox", checked: q.discovery !== false, onchange: e => { q.discovery = e.target.checked; changed(); } }), t("mqtt.discovery")),
      inp(q, "prefix", t("mqtt.prefix"), null, "mqtt.prefix"), h("p", { class: "small muted", style: "margin-top:10px" }, t("mqtt.topics", d.node)));
    g.append(mq);
    const usb = h("div", { class: "panel" }, h("h3", {}, t("set.usb"), helpHint("set.usb")), h("p", { class: "small muted" }, t("set.usb.help", META.link_port || "-")), h("div", { id: "portlist" }));
    g.append(usb);
    api("/api/ports").then(p => {
      PORTS = p || [];
      const box = $("#portlist");
      if (box) box.replaceChildren(PORTS.length ? h("ul", { class: "pinnotes" }, PORTS.map(x => h("li", {}, x.name + (x.busy ? " (" + t("set.busy") + ")" : "")))) : h("p", { class: "small muted" }, t("set.usb.none")));
    }).catch(() => {});
  }
  const file = h("input", { type: "file", accept: ".json", hidden: true, onchange: async e => {
    const f = e.target.files[0];
    if (!f) return;
    try {
      const j = JSON.parse(await f.text());
      if (!j.components || !j.device) throw new Error("shape");
      j.boards = j.boards || [{ id: "main", name: "UNO Q", model: "unoq", link: { type: "local" } }];
      j.components.forEach(c => { if (!c.board && META.types[c.type] && META.types[c.type].cap) c.board = "main"; });
      j.scripts = j.scripts || { workspace: {} };
      delete j.automations;
      if (j.device.tz === undefined && j.device.tz_offset !== undefined) {      // files from before 2.1 (the server migrates as well)
        const off = +j.device.tz_offset;
        j.device.tz = isFinite(off) ? fixedName(Math.max(-720, Math.min(840, Math.round(off * 4) * 15))) : (META.tz || {}).default || "UTC";
      }
      delete j.device.tz_offset;
      // Devices on the UNO Q bottom connector (pins 25-49, gone in 2.1): the server drops them only
      // from a file that still looks old, and the zone was just converted, so drop them here too.
      const unoq = j.boards.filter(b => b && b.model === "unoq").map(b => b.id);
      const gone = j.components.filter(c => c && unoq.includes(c.board) && Number.isInteger(c.pin) && c.pin >= 25);
      j.components = j.components.filter(c => !gone.includes(c));
      const off = unhookComps(j, gone.map(c => c.id));
      DRAFT = j; SEL = null; changed();
      toast(gone.length ? t("set.imported.dropped", gone.length, gone.map(c => c.id).join(", ")) + (off ? " " + t("set.imported.scripts", off) : "") : t("set.imported")); render();
    } catch (err) { toast(t("set.import.bad")); }
  } });
  g.append(h("div", { class: "panel" }, h("h3", {}, t("set.backup")), h("div", { style: "display:flex;gap:8px;flex-wrap:wrap" },
    h("a", { class: "btn", href: "/api/export" }, t("set.export")), h("button", { class: "btn", onclick: () => file.click() }, t("set.import")), file)));
  clockTick();
}

// ------------------------------------------------------------------ log
function logLine(l) { return h("div", { class: l.lvl }, h("span", { class: "muted" }, new Date(l.t * 1000).toLocaleTimeString()), h("span", {}, l.msg)); }
function viewLog(m) {
  m.append(h("div", { class: "panel log", id: "logbox" }, LOGS.length ? LOGS.slice().reverse().map(logLine) : h("p", { class: "muted" }, t("log.empty"))));
}

// ------------------------------------------------------------------ help
// Content: window.QHELP (assets/help.js, strict JSON written by the docs). This file only renders it:
// everything is built with h() and text nodes, the inline markup goes through a small tokenizer.
const helpData = () => window.QHELP || { pages: [], hints: {} };
const L = v => (typeof v === "string" ? v : v && typeof v === "object" ? (v[LANG] != null ? v[LANG] : v.en != null ? v.en : "") : v == null ? "" : String(v));
function helpPages() { return (helpData().pages || []).filter(p => p && p.id && (!Array.isArray(p.roles) || p.roles.includes(META.role))); }
function helpPage(id) { return helpPages().find(p => p.id === id) || null; }
function helpFill(s) {            // {{placeholders}} -> live values of this installation
  const q = CFG.mqtt || {};
  const vars = { url: location.origin, host: masterHost(), node: (CFG.device || {}).node, web_port: META.web_port || location.port || 7000,
    mqtt_port: (q.mode === "external" ? q.ext_port : q.port) || 1883, link_port: META.link_port, version: META.version };
  return String(s).replace(/\{\{(\w+)\}\}/g, (m, k) => (vars[k] == null ? m : String(vars[k])));
}
function helpLink(label, page, anchor) {      // a link into the help; plain text when the page does not exist
  if (!helpPage(page)) return document.createTextNode(label);
  return h("a", { class: "hlink", href: helpHref(page, anchor), onclick: e => {
    if ($("#modal").hidden) { e.preventDefault(); helpOpen(page, anchor); }
    else { e.currentTarget.target = "_blank"; e.currentTarget.rel = "noopener"; }     // keep the open dialog: read in a new tab
  } }, label);
}
function inline(text) {           // **bold**, `code`, [label](#page) or [label](#page/anchor)
  const out = [], re = /\*\*([^*]+)\*\*|`([^`]+)`|\[([^\]]+)\]\(([^)\s]+)\)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    if (m[1] != null) out.push(h("b", {}, inline(m[1])));
    else if (m[2] != null) out.push(h("code", {}, m[2]));
    else if (/^https?:\/\//.test(m[4])) out.push(h("a", { href: m[4], target: "_blank", rel: "noopener" }, m[3]));
    else if (m[4][0] === "#") { const [pg, an] = m[4].slice(1).split(/[/#]/); out.push(helpLink(m[3], pg, an)); }
    else out.push(m[3]);
    last = re.lastIndex;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}
const rich = v => inline(helpFill(L(v)));
function helpTable(head, rows) {
  return h("div", { class: "tablewrap" }, h("table", { class: "htable" },
    h("thead", {}, h("tr", {}, head.map(x => h("th", {}, x)))), h("tbody", {}, rows.map(r => h("tr", {}, r.map(x => h("td", {}, x)))))));
}
function helpGen(name) {          // tables built from live data, so they follow the installed version
  const models = Object.values(META.models || {}), mm = META.matrix || {};
  const count = (m, cap) => m.pins.filter(p => p.caps.includes(cap)).length || "";
  if (name === "boards") return helpTable(["board", "logic", "digital", "pwm", "adc", "dac", "cnt", "extras"].map(k => t("help.gen." + k)), models.map(m => {
    const adc = count(m, "adc"), rgb = count(m, "rgb");
    return [m.label, m.logic + " V", m.pins.filter(p => p.caps.includes("din") || p.caps.includes("dout")).length, count(m, "pwm"),
      adc ? t("help.gen.bits", adc, Math.round(Math.log2((m.adc_max || 1023) + 1))) : "", count(m, "dac"), count(m, "cnt"),
      [count(m, "matrix") ? t("help.gen.matrix") : null, rgb ? t("help.gen.rgb", rgb) : null].filter(Boolean).join(", ")];
  }));
  if (name === "links") {
    const kinds = ["local", "usb", "uart", "i2c", "wifi"].filter(k => models.some(m => m.links.includes(k)));
    return helpTable([t("help.gen.board"), ...kinds.map(k => t("link." + k))],
      models.map(m => [m.label, ...kinds.map(k => (m.links.includes(k) ? h("span", { class: "yes", title: t("help.gen.yes"), "aria-label": t("help.gen.yes") }, "✓") : ""))]));
  }
  if (name === "types") return helpTable([t("help.gen.tag"), t("help.gen.type"), t("help.gen.for")],
    Object.entries(META.types || {}).map(([k, ty]) => [h("span", { class: "tag f-" + (ty.cap || "virt") }, ty.tag), typeLabel(k), t("type." + k + ".d")]));
  if (name === "icons") return helpTable([t("help.gen.icon"), t("help.gen.name"), t("help.gen.code")],
    Object.entries(mm.icons || {}).map(([k, frame]) => [h("span", { class: "mxicon" }, matrixView(frame, "mxmini")), t("icon." + k), h("code", {}, k)]));
  if (name === "anims") return helpTable([t("help.gen.anim"), t("help.gen.code")], (mm.anims || []).map(k => [t("anim." + k), h("code", {}, k)]));
  return null;
}
function helpBlock(bl) {          // unknown block types are skipped
  if (!bl || typeof bl !== "object") return null;
  if (bl.t === "h") return h("h3", { id: bl.id ? "h-" + bl.id : null, class: "hsec" }, rich(bl.text));
  if (bl.t === "p") return h("p", {}, rich(bl.text));
  if (bl.t === "ul" || bl.t === "ol") return h(bl.t, {}, (bl.items || []).map(x => h("li", {}, rich(x))));
  if (bl.t === "code") return h("pre", { class: "code" }, helpFill(L(bl.text)));
  if (bl.t === "note") return h("div", { class: "note" + (bl.warn ? "" : " info") }, rich(bl.text));
  if (bl.t === "table") return helpTable((bl.head || []).map(rich), (bl.rows || []).map(r => (r || []).map(rich)));
  if (bl.t === "gen") return helpGen(bl.name);
  return null;
}
function helpText(bl) {           // the words of a block, for the search box
  if (!bl || typeof bl !== "object") return "";
  return [bl.text, ...(bl.items || []), ...(bl.head || []), ...(bl.rows || []).flat()].map(L).join(" ");
}
function helpMatches(pg, q) {     // null = no match; else the sections (headings) in which the words occur
  const secs = [];
  let cur = { id: null, title: "", text: L(pg.title) };
  for (const bl of pg.blocks || []) {
    if (bl && bl.t === "h") { secs.push(cur); cur = { id: bl.id, title: L(bl.text), text: "" }; }
    cur.text += " " + helpText(bl);
  }
  secs.push(cur);
  const hits = secs.filter(s => s.text.toLowerCase().includes(q));
  return hits.length ? hits.filter(s => s.id) : null;
}
function helpList() {
  const box = $("#helplist");
  if (!box) return;
  const q = HELP.q.trim().toLowerCase(), items = [];
  for (const pg of helpPages()) {
    const hits = q ? helpMatches(pg, q) : [];
    if (!hits) continue;
    items.push(h("button", { "aria-current": pg.id === HELP.page ? "page" : null, "data-page": pg.id, onclick: () => helpOpen(pg.id) }, L(pg.title)));
    for (const s of hits.slice(0, 4)) items.push(h("button", { class: "sub", onclick: () => helpOpen(pg.id, s.id) }, s.title));
  }
  box.replaceChildren(...(items.length ? items : [h("p", { class: "small muted" }, t("help.nomatch"))]));
}
function helpDoc() {
  const doc = $("#helpdoc"), pg = helpPage(HELP.page);
  if (!doc || !pg) return;
  const heads = (pg.blocks || []).filter(b => b && b.t === "h" && b.id);
  doc.replaceChildren(h("h2", {}, L(pg.title)),
    heads.length > 1 ? h("nav", { class: "helptoc", "aria-label": t("help.onpage") }, h("span", { class: "k" }, t("help.onpage")),
      heads.map(b => h("a", { class: "hlink", href: helpHref(pg.id, b.id), onclick: e => { e.preventDefault(); helpOpen(pg.id, b.id); } }, L(b.text)))) : null,
    ...(pg.blocks || []).map(helpBlock).filter(Boolean));
}
function viewHelp(m) {
  const pages = helpPages();
  if (!pages.length) { m.append(h("div", { class: "panel empty" }, h("p", {}, t("help.empty")))); return; }
  if (!helpPage(HELP.page)) { HELP.page = pages[0].id; HELP.anchor = null; }
  m.append(h("div", { class: "help" },
    h("div", { class: "panel helpside" }, h("input", { type: "search", id: "helpq", placeholder: t("help.search"), "aria-label": t("help.search"), value: HELP.q,
      oninput: e => { HELP.q = e.target.value; helpList(); } }), h("nav", { class: "helplist", id: "helplist", "aria-label": t("help.pages") })),
    h("article", { class: "panel helpdoc", id: "helpdoc" })));
  helpList();
  helpDoc();
  const target = HELP.anchor ? document.getElementById("h-" + HELP.anchor) : null;
  if (target) target.scrollIntoView({ block: "start" }); else m.scrollTop = 0;
}
function helpOpen(page, anchor) { // shows a help page; from inside a dialog it opens a new tab so the dialog survives
  if (!$("#modal").hidden) { window.open(location.pathname + location.search + helpHref(page, anchor), "_blank", "noopener"); return; }
  HELP.page = page; HELP.anchor = anchor || null;
  if (VIEW !== "help") go("help"); else render();
}
// Round "?" next to a field. Returns null when the help has no hint for any of the keys.
let HINT_OPEN = null;
function closeHints() {
  document.querySelectorAll(".hintbox").forEach(x => x.remove());
  document.querySelectorAll('.hint[aria-expanded="true"]').forEach(b => b.setAttribute("aria-expanded", "false"));
  HINT_OPEN = null;
}
function toggleHint(btn, keep) {
  const key = btn.dataset.hint, hint = (helpData().hints || {})[key], open = btn.getAttribute("aria-expanded") === "true";
  closeHints();
  if ((open && !keep) || !hint) return;
  const box = h("div", { class: "hintbox", role: "note" }, h("span", {}, rich(hint.text)));
  if (hint.more) { const [pg, an] = String(hint.more).split("#"); if (helpPage(pg)) box.append(" ", helpLink(t("help.more"), pg, an)); }
  const host = btn.closest(".lbl,h3,.note");
  if (!host) btn.after(box);
  else if (host.matches(".note")) host.append(box);
  else if (host.matches(".lbl:not(.self)") && host.nextElementSibling) host.nextElementSibling.after(box);
  else host.after(box);
  btn.setAttribute("aria-expanded", "true");
  HINT_OPEN = key;
}
function helpHint(...keys) {
  const hints = helpData().hints || {}, key = keys.find(k => k && hints[k] && L(hints[k].text));
  if (!key) return null;
  const btn = h("button", { class: "hint", type: "button", "aria-label": t("help.what"), title: t("help.what"), "aria-expanded": "false", "data-hint": key,
    onclick: e => { e.preventDefault(); e.stopPropagation(); toggleHint(btn); } }, "?");
  if (HINT_OPEN === key) queueMicrotask(() => { if (btn.isConnected) toggleHint(btn, true); });    // survives a redraw of the form
  return btn;
}

// ------------------------------------------------------------------ live updates
function applyLive(newLogs) {
  const chips = $("#chips");
  const list = isNode() ? [] : CFG.boards.map(b => {
    const s = (ST.boards || {})[b.id] || {};
    return h("span", { class: "chip", title: s.text || "" }, h("span", { class: "dot " + (s.online ? "ok" : "err") }), b.name || b.id);
  });
  if (META.sim) list.push(h("span", { class: "chip", style: "border-color:var(--adc);color:var(--adc)" }, t("sim.badge")));
  chips.replaceChildren(...list);
  const mq = $("#statMqtt"), ms = ST.mqtt || {};
  mq.querySelector(".dot").className = "dot " + (ms.ok ? "ok" : ms.mode === "off" ? "" : "warn");
  mq.querySelector(".lbl").textContent = "MQTT: " + (ms.text || "-");
  updateBadge();
  if (VIEW === "dash") refreshDash();
  else if (VIEW === "boards") {
    document.querySelectorAll("#main .pin.used").forEach(el => {
      const raw = el.dataset.pin, c = compAt(SELB, isNaN(+raw) ? raw : +raw);
      if (!c) return;
      const v = el.querySelector(".val"), sock = el.querySelector(".sock");
      if (c.type === "led_matrix" || c.type === "rgb_led") fillSock(sock, c, el.classList.contains("bpart") ? "mxpart" : "mxmini");
      else if (v) v.textContent = stOf(c.id).txt || "";
    });
    const bs = $("#bstat"), s = (ST.boards || {})[SELB];
    if (bs && s) bs.replaceChildren(h("span", { class: "dot " + (s.online ? "ok" : "err") }), s.online ? t("online") : (s.text || t("offline")));
    document.querySelectorAll("#main .tabs [data-bid]").forEach(el => {
      el.querySelector(".dot").className = "dot " + (((ST.boards || {})[el.dataset.bid] || {}).online ? "ok" : "err");
    });
    fillFound();
  } else if (VIEW === "blocks") blocksFoot();
  else if (VIEW === "log" && newLogs) render();
}
let lastBoards = "";
async function poll() {
  try {
    const s = await api("/api/state?log=" + LOGSEQ);
    s.states = s.states || {}; s.boards = s.boards || {}; s.logs = s.logs || [];
    for (const l of s.logs) { LOGS.push(l); LOGSEQ = Math.max(LOGSEQ, l.n); }
    if (LOGS.length > 400) LOGS = LOGS.slice(-400);
    for (const [id, v] of Object.entries(s.states)) {
      if (typeof v.v !== "number") continue;
      const a = (HIST[id] = HIST[id] || []);
      if (a._t !== v.t) { a.push(v.v); a._t = v.t; if (a.length > 60) a.shift(); }
    }
    // sys and time change on every poll: they never decide about a redraw, the panel is patched in place
    const boardsNow = JSON.stringify(s.boards) + JSON.stringify(s.mqtt) + JSON.stringify(s.vars) + s.running + JSON.stringify(s.node || 0)
      + JSON.stringify(s.discovered || []) + JSON.stringify(s.mx || {}) + JSON.stringify(s.matrix || {});
    const fresh = !ST || ST.rev !== s.rev || boardsNow !== lastBoards;
    lastBoards = boardsNow;
    ST = s;
    if (s.time && typeof s.time.epoch === "number") SKEW = s.time.epoch * 1000 - Date.now();
    if (fresh || s.logs.length) applyLive(s.logs.length);
    sysPatch();
  } catch (e) {
    $("#statMqtt .dot").className = "dot err";
    $("#statMqtt .lbl").textContent = t("server.down");
  }
  setTimeout(poll, 800);
}

// ------------------------------------------------------------------ boot
function showErrors(list) {
  const eb = $("#errbox");
  eb.replaceChildren(h("b", {}, t("save.failed")), h("ul", {}, list.map(x => h("li", {}, x))));
  eb.hidden = false;
}
async function save() {
  const r = await api("/api/config", DRAFT);
  if (!r.ok) { showErrors(r.errors || ["?"]); return; }
  CFG = clone(DRAFT);
  $("#errbox").hidden = true;
  toast(t("saved"));
  if (r.restart) { toast(t("restart.note")); setTimeout(() => location.reload(), 5000); }
  render();
}
(async () => {
  document.documentElement.lang = LANG;
  $("#lang").replaceChildren(...Object.entries(LANG_NAMES).map(([k, label]) =>
    h("button", { "aria-pressed": k === LANG ? "true" : "false", onclick: () => { lsSet("qhome.lang", k); location.reload(); } }, label)));
  $("#bSave").textContent = t("save");
  $("#bUndo").textContent = t("discard");
  $("#bSave").onclick = save;
  $("#bUndo").onclick = () => { DRAFT = clone(CFG); SEL = null; $("#errbox").hidden = true; changed(); render(); };
  META = await api("/api/meta");
  CFG = await api("/api/config");
  CFG.scripts = CFG.scripts || { workspace: {} };
  DRAFT = clone(CFG);
  $("#ver").textContent = "QHome " + META.version;
  window.addEventListener("beforeunload", e => { if (dirty()) { e.preventDefault(); e.returnValue = ""; } });
  window.addEventListener("resize", () => { if (VIEW === "blocks") QBlocks.resize(); });
  window.addEventListener("hashchange", () => { if (readHash()) { renderNav(); render(); } });
  document.addEventListener("pointerdown", () => { PDOWN = true; }, true);
  for (const ev of ["pointerup", "pointercancel"]) document.addEventListener(ev, () => { PDOWN = false; }, true);
  document.addEventListener("keydown", e => {
    if (e.key !== "Escape") return;
    if (document.querySelector(".hintbox")) closeHints();
    else if (!$("#modal").hidden) { $("#modal").hidden = true; $("#modal").replaceChildren(); }
  });
  readHash();
  renderNav();
  render();
  setInterval(clockTick, 1000);
  poll();
})();
