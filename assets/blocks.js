// Scratch-style blocks for QHome, built on Blockly (the engine Scratch itself is based on).
// The Python side (python/qh_script.py) runs the saved workspace directly; block type and
// field names here must match that file.
"use strict";
const QBlocks = (() => {
  const C = { events: "#D99A00", devices: "#3F7FE0", sensing: "#2F9CC4", control: "#E08A14",
              operators: "#40A148", vars: "#EC6F17", net: "#8A5BE0" };
  let ctx = { comps: () => [], boards: () => [], kinds: {}, matrix: { icons: {}, anims: [] } };   // filled in by app.js
  let ws = null, onChange = null, loading = false;

  function entOptions(btype, want) {
    const kinds = ctx.kinds[btype] || [];
    const opts = ctx.comps().filter(c => kinds.includes(c.type)).map(c => [c.name || c.id, c.id]);
    if (want && !opts.some(o => o[1] === want)) opts.push([t("blocks.missing", want), want]);
    return opts.length ? opts : [[t("blocks.none"), ""]];
  }
  function boardOptions(want) {
    const opts = ctx.boards().map(b => [b.name || b.id, b.id]);
    if (want && !opts.some(o => o[1] === want)) opts.push([t("blocks.missing", want), want]);
    return opts.length ? opts : [[t("blocks.noboard"), ""]];
  }
  // Dropdowns whose choices come from the current setup. A saved value that no longer
  // exists stays visible as "missing: x" instead of silently jumping to another device.
  class EntityField extends Blockly.FieldDropdown {
    constructor(btype) { super(function () { return entOptions(btype, this.want_); }); }
    doClassValidation_(v) {
      if (typeof v !== "string") return null;
      this.want_ = v; this.generatedOptions = null;
      return super.doClassValidation_(v);
    }
    static fromJson(o) { return new EntityField(o.btype); }
  }
  class BoardField extends Blockly.FieldDropdown {
    constructor() { super(function () { return boardOptions(this.want_); }); }
    doClassValidation_(v) {
      if (typeof v !== "string") return null;
      this.want_ = v; this.generatedOptions = null;
      return super.doClassValidation_(v);
    }
    static fromJson() { return new BoardField(); }
  }

  const dd = (name, keys, prefix = "blk.") => ({ type: "field_dropdown", name, options: keys.map(k => [t(prefix + k), k]) });
  const ent = btype => ({ type: "field_entity", name: "ENT", btype });
  const val = (name, check) => ({ type: "input_value", name, check });
  const stmt = name => ({ type: "input_statement", name });
  const DAYS = ["all", "weekdays", "weekend", "mon", "tue", "wed", "thu", "fri", "sat", "sun"];

  function define(colors) {
    Blockly.fieldRegistry.register("field_entity", EntityField);
    Blockly.fieldRegistry.register("field_board", BoardField);
    const hat = (type, args) => ({ type, message0: t("blk." + type), args0: args || [], nextStatement: null, style: "q_events", inputsInline: true });
    const cmd = (type, style, args, extra) => Object.assign({ type, message0: t("blk." + type), args0: args || [], previousStatement: null, nextStatement: null, style, inputsInline: true }, extra || {});
    const rep = (type, style, out, args) => ({ type, message0: t("blk." + type), args0: args || [], output: out, style, inputsInline: true });
    const body = (type, args, extra) => Object.assign(cmd(type, "q_control", args), { message1: "%1", args1: [stmt("DO")] }, extra || {});
    const time = (name, def) => ({ type: "field_input", name, text: def });
    const mx = ctx.matrix || {};                           // icon and animation names come from the server
    const mxNames = (list, fallback) => (list && list.length ? list : [fallback]);   // a dropdown needs one option
    Blockly.common.defineBlocksWithJsonArray([
      hat("ev_start"),
      hat("ev_state", [ent("ev_state"), { type: "field_dropdown", name: "TO", options: [[t("blk.st_on"), "on"], [t("blk.st_off"), "off"], [t("blk.changes"), "change"]] }]),
      hat("ev_above", [ent("ev_above"), dd("OP", ["above", "below"]), val("VALUE", "Number")]),
      hat("ev_every", [val("N", "Number"), dd("UNIT", ["s", "m", "h"])]),
      hat("ev_time", [time("AT", "07:30"), dd("DAYS", DAYS)]),
      hat("ev_mqtt", [{ type: "field_input", name: "TOPIC", text: "home/#" }]),
      hat("ev_board", [{ type: "field_board", name: "BOARD" }, dd("TO", ["online", "offline"])]),
      cmd("do_turn", "q_devices", [ent("do_turn"), dd("TO", ["on", "off"])]),
      cmd("do_toggle", "q_devices", [ent("do_toggle")]),
      cmd("do_set", "q_devices", [ent("do_set"), val("VALUE", "Number")]),
      cmd("do_rgb", "q_devices", [ent("do_rgb"), { type: "field_dropdown", name: "COLOR", options: colors.map(k => [t("color." + k), k]) }]),
      cmd("do_show", "q_devices", [ent("do_show"), val("TEXT")]),
      cmd("do_clear", "q_devices", [ent("do_clear")]),
      cmd("do_show_for", "q_devices", [ent("do_show_for"), val("TEXT"), val("SECS", "Number")]),
      cmd("do_mx_icon", "q_devices", [ent("do_mx_icon"), dd("ICON", mxNames(Object.keys(mx.icons || {}), "smile"), "icon.")]),
      cmd("do_mx_anim", "q_devices", [ent("do_mx_anim"), dd("ANIM", mxNames(mx.anims, "wave"), "anim.")]),
      cmd("do_mx_value", "q_devices", [ent("do_mx_value"), { type: "field_entity", name: "SRC", btype: "do_mx_value.SRC" },
                                       dd("AS", ["value", "bar"], "mxas.")]),
      cmd("do_mx_mode", "q_devices", [ent("do_mx_mode"), dd("MODE", ["auto", "clock", "status", "ip", "off"], "mx.")]),
      cmd("do_publish", "q_net", [val("PAYLOAD"), val("TOPIC")]),
      cmd("do_log", "q_net", [val("TEXT")]),
      rep("get_on", "q_sensing", "Boolean", [ent("get_on")]),
      rep("get_value", "q_sensing", "Number", [ent("get_value")]),
      rep("get_board", "q_sensing", "Boolean", [{ type: "field_board", name: "BOARD" }]),
      rep("get_time", "q_sensing", "Number", [dd("WHAT", ["hour", "minute", "second", "weekday", "uptime"])]),
      rep("get_between", "q_sensing", "Boolean", [time("FROM", "22:00"), time("TO", "06:00")]),
      rep("get_mqtt", "q_net", "String"),
      cmd("ctl_wait", "q_control", [val("SECS", "Number")]),
      body("ctl_repeat", [val("TIMES", "Number")]),
      body("ctl_forever", [], { nextStatement: undefined }),
      body("ctl_if", [val("COND", "Boolean")]),
      Object.assign(body("ctl_ifelse", [val("COND", "Boolean")]), { message0: t("blk.ctl_if"), message2: t("blk.else"), args2: [], message3: "%1", args3: [stmt("ELSE")] }),
      cmd("ctl_wait_until", "q_control", [val("COND", "Boolean")]),
      body("ctl_repeat_until", [val("COND", "Boolean")]),
      cmd("ctl_stop", "q_control", [], { nextStatement: undefined }),
    ]);
    for (const type of ["ev_time", "get_between"]) {       // keep HH:MM fields well-formed
      const init = Blockly.Blocks[type].init;
      Blockly.Blocks[type].init = function () {
        init.call(this);
        for (const n of ["AT", "FROM", "TO"]) {
          const f = this.getField(n);
          if (f) f.setValidator(v => (/^([01]?\d|2[0-3]):[0-5]\d$/.test(v.trim()) ? v.trim() : null));
        }
      };
    }
  }

  const num = n => ({ shadow: { type: "math_number", fields: { NUM: n } } });
  const txt = s => ({ shadow: { type: "text", fields: { TEXT: s } } });
  const blk = (type, inputs) => (inputs ? { kind: "block", type, inputs } : { kind: "block", type });
  const cat = (key, contents) => ({ kind: "category", name: t("cat." + key), colour: C[key], contents });
  function toolbox() {
    return { kind: "categoryToolbox", contents: [
      cat("events", [blk("ev_start"), blk("ev_state"), blk("ev_above", { VALUE: num(30) }), blk("ev_every", { N: num(10) }),
                     blk("ev_time"), blk("ev_board"), blk("ev_mqtt")]),
      cat("devices", [blk("do_turn"), blk("do_toggle"), blk("do_set", { VALUE: num(50) }), blk("do_rgb"),
                      blk("do_show", { TEXT: txt("HELLO") }), blk("do_clear"),
                      blk("do_show_for", { TEXT: txt("HELLO"), SECS: num(5) }), blk("do_mx_icon"), blk("do_mx_anim"),
                      blk("do_mx_value"), blk("do_mx_mode")]),
      cat("sensing", [blk("get_on"), blk("get_value"), blk("get_board"), blk("get_time"), blk("get_between")]),
      cat("control", [blk("ctl_wait", { SECS: num(1) }), blk("ctl_repeat", { TIMES: num(10) }), blk("ctl_forever"), blk("ctl_if"),
                      blk("ctl_ifelse"), blk("ctl_wait_until"), blk("ctl_repeat_until"), blk("ctl_stop")]),
      cat("operators", [blk("math_arithmetic", { A: num(1), B: num(1) }), blk("logic_compare", { A: num(0), B: num(50) }),
                        blk("logic_operation"), blk("logic_negate"), blk("logic_boolean"),
                        blk("math_random_int", { FROM: num(1), TO: num(10) }), blk("math_round", { NUM: num(3.1) }),
                        blk("math_modulo", { DIVIDEND: num(64), DIVISOR: num(10) }),
                        blk("math_constrain", { VALUE: num(50), LOW: num(0), HIGH: num(100) }),
                        blk("math_number"), blk("text"), blk("text_join")]),
      { kind: "category", name: t("cat.vars"), colour: C.vars, custom: "VARIABLE" },
      cat("net", [blk("do_publish", { PAYLOAD: txt("ON"), TOPIC: txt("home/light") }), blk("get_mqtt"), blk("do_log", { TEXT: txt("hello") })]),
    ] };
  }

  function theme() {
    const st = c => ({ colourPrimary: c, colourSecondary: shade(c, -0.12), colourTertiary: shade(c, -0.22) });
    return Blockly.Theme.defineTheme("qhome", {
      base: Blockly.Themes.Zelos, startHats: true,
      blockStyles: { q_events: Object.assign(st(C.events), { hat: "cap" }), q_devices: st(C.devices), q_sensing: st(C.sensing),
        q_control: st(C.control), q_net: st(C.net), math_blocks: st(C.operators), logic_blocks: st(C.operators),
        text_blocks: st(C.operators), variable_blocks: st(C.vars), variable_dynamic_blocks: st(C.vars) },
      categoryStyles: {},
      componentStyles: { workspaceBackgroundColour: "#F8FAF9", toolboxBackgroundColour: "#FFFFFF", toolboxForegroundColour: "#14211F",
        flyoutBackgroundColour: "#E9EEEC", flyoutForegroundColour: "#14211F", flyoutOpacity: 0.96, scrollbarColour: "#9AA8A4",
        scrollbarOpacity: 0.6, insertionMarkerColour: "#14211F", insertionMarkerOpacity: 0.25, cursorColour: "#0A7C86" },
      fontStyle: { family: '"Barlow", system-ui, sans-serif', weight: "500", size: 11.5 },
    });
  }
  function shade(hex, f) {
    const n = parseInt(hex.slice(1), 16);
    const ch = s => Math.max(0, Math.min(255, Math.round(((n >> s) & 255) * (1 + f))));
    return "#" + ((1 << 24) | (ch(16) << 16) | (ch(8) << 8) | ch(0)).toString(16).slice(1);
  }

  // Blockly's own blocks (operators, variables) come translated; load the matching pack.
  function loadLocale(lang) {
    return new Promise(res => {
      const s = document.createElement("script");
      s.src = "/static/vendor/blockly/msg/" + (lang === "tr" ? "tr" : "en") + ".js";
      s.onload = s.onerror = res;
      document.head.append(s);
    });
  }

  async function init(div, context, colors, changed) {
    ctx = context; onChange = changed;
    await loadLocale(LANG);
    define(colors);
    ws = Blockly.inject(div, {
      toolbox: toolbox(), renderer: "zelos", theme: theme(), media: "/static/vendor/blockly/media/",
      trashcan: true, sounds: false, collapse: false, comments: false,
      zoom: { controls: true, wheel: true, startScale: 0.85, maxScale: 1.6, minScale: 0.4, scaleSpeed: 1.1 },
      move: { scrollbars: true, drag: true, wheel: true }, grid: { spacing: 28, length: 2, colour: "#D5DCD9", snap: false },
    });
    ws.addChangeListener(ev => {
      if (loading || ev.isUiEvent || !onChange) return;
      onChange(Blockly.serialization.workspaces.save(ws));
    });
    return ws;
  }
  function load(json) {
    if (!ws) return;
    loading = true;
    try {
      Blockly.Events.disable();
      ws.clear();
      if (json && json.blocks) Blockly.serialization.workspaces.load(json, ws);
    } catch (e) {
      console.error("Could not load the block workspace", e);
    } finally {
      Blockly.Events.enable();
      loading = false;
    }
  }
  function resize() { if (ws) Blockly.svgResize(ws); }
  function save() { return ws ? Blockly.serialization.workspaces.save(ws) : {}; }
  return { init, load, resize, save, colors: C };
})();
