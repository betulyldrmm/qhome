import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../services/api";
import type { ApiContext, QHomeConfig } from "../types/api";
import type { Language } from "../i18n";

interface Props { data: ApiContext; language: Language; onSaved: () => Promise<void>; onDirtyChange: (dirty: boolean) => void; }
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;
const text = {
  en: { title: "Settings", subtitle: "Manage controller identity, access, time, MQTT and backups.", device: "This QHome", name: "Home name", node: "Node name", nodeHint: "MQTT prefix; lowercase letters, digits, - and _.", password: "Web password", passwordHint: "Blank means no password. Any username is accepted by the browser prompt.", timezone: "Time zone", region: "Region", city: "City or offset", fixed: "UTC / fixed offset", browserZone: "Use this browser's time zone", timezoneDb: "The time zone database is unavailable on this computer. Named zones may use a fixed offset without daylight saving.", clockNow: "Controller clock now", clockAfter: "After saving", role: "Role of this board", master: "Master", nodeRole: "Node", masterInfo: "Runs scripts, manages boards and hosts the web interface.", nodeInfo: "Hands this UNO Q's pins to another master over Wi-Fi.", masterHost: "Master address (IP or host name)", masterPort: "MQTT port", masterUser: "MQTT username", masterPass: "MQTT password", mqtt: "MQTT and Home Assistant", internal: "Built-in broker", external: "Use another broker", off: "Off", mqttPort: "Broker port", mqttHost: "Broker address", username: "Username (blank = anyone)", mqttPass: "Password", discovery: "Home Assistant discovery", prefix: "Discovery prefix", prefixHint: "Keep homeassistant unless Home Assistant uses another discovery prefix.", ha: "In Home Assistant, add the MQTT integration and use this controller's address and port.", topics: "Topics: {0}/<id>/state, {0}/<id>/set and {0}/status", insecure: "Without a username and password, anyone on your network may control outputs.", usb: "USB boards", usbHelp: "USB helper port: {0}. Connected ports visible to this controller:", noPorts: "No USB ports found.", busy: "in use", backup: "Backup", export: "Download setup (.json)", import: "Import setup", importReady: "Configuration loaded. Save to apply it.", importBad: "This file is not a valid QHome configuration.", importedDropped: "{0} unsupported UNO Q device(s) were removed. {1} script(s) using them were disabled and can be repaired in Automations.", save: "Save settings", saving: "Saving…", saved: "Settings saved.", restart: "Settings saved. The backend requested a restart; reconnect after it comes back.", dirty: "You have unsaved settings.", discard: "Discard", changed: "Changed", validation: "Check the highlighted settings.", loadError: "Could not load serial port information.", saveError: "Settings could not be saved.", readOnlyInfo: "Only settings supported by the current backend are shown here." },
  tr: { title: "Ayarlar", subtitle: "Denetleyici kimliğini, erişimi, saati, MQTT'yi ve yedekleri yönetin.", device: "Bu QHome", name: "Ev adı", node: "Düğüm adı", nodeHint: "MQTT öneki; küçük harf, rakam, - ve _ kullanın.", password: "Web parolası", passwordHint: "Boş bırakılırsa parola istenmez. Tarayıcı penceresinde kullanıcı adı herhangi bir değer olabilir.", timezone: "Saat dilimi", region: "Bölge", city: "Şehir veya fark", fixed: "UTC / sabit fark", browserZone: "Bu tarayıcının saat dilimini kullan", timezoneDb: "Bu bilgisayarda saat dilimi veritabanı yok. Adlı dilimler yaz saati olmadan sabit fark kullanabilir.", clockNow: "Denetleyici saati şimdi", clockAfter: "Kaydedilince", role: "Bu kartın rolü", master: "Ana kart", nodeRole: "Düğüm", masterInfo: "Betikleri çalıştırır, kartları yönetir ve web arayüzünü sunar.", nodeInfo: "Bu UNO Q'nun pinlerini Wi-Fi üzerinden başka bir ana karta verir.", masterHost: "Ana kart adresi (IP veya ad)", masterPort: "MQTT portu", masterUser: "MQTT kullanıcı adı", masterPass: "MQTT parolası", mqtt: "MQTT ve Home Assistant", internal: "Dahili sunucu", external: "Başka sunucu kullan", off: "Kapalı", mqttPort: "Sunucu portu", mqttHost: "Sunucu adresi", username: "Kullanıcı adı (boş = herkes)", mqttPass: "Parola", discovery: "Home Assistant otomatik keşif", prefix: "Keşif öneki", prefixHint: "Home Assistant'ınız başka bir keşif öneki kullanmıyorsa homeassistant kalsın.", ha: "Home Assistant'ta MQTT entegrasyonu ekleyip bu denetleyicinin adresini ve portunu kullanın.", topics: "Konular: {0}/<kimlik>/state, {0}/<kimlik>/set ve {0}/status", insecure: "Kullanıcı adı ve parola olmadan ağınızdaki herkes çıkışları kontrol edebilir.", usb: "USB kartlar", usbHelp: "USB yardımcı portu: {0}. Bu denetleyicinin gördüğü bağlı portlar:", noPorts: "USB port bulunamadı.", busy: "kullanımda", backup: "Yedek", export: "Kurulumu indir (.json)", import: "Kurulum dosyası yükle", importReady: "Yapılandırma yüklendi. Uygulamak için kaydedin.", importBad: "Bu dosya geçerli bir QHome yapılandırması değil.", importedDropped: "Desteklenmeyen {0} UNO Q cihazı kaldırıldı. Bunları kullanan {1} betik devre dışı bırakıldı; Otomasyonlar'da onarılabilir.", save: "Ayarları kaydet", saving: "Kaydediliyor…", saved: "Ayarlar kaydedildi.", restart: "Ayarlar kaydedildi. Backend yeniden başlama istedi; geri geldiğinde yeniden bağlanın.", dirty: "Kaydedilmemiş ayarlar var.", discard: "Vazgeç", changed: "Değişti", validation: "Vurgulanan ayarları kontrol edin.", loadError: "Seri port bilgileri alınamadı.", saveError: "Ayarlar kaydedilemedi.", readOnlyInfo: "Burada yalnızca mevcut backend'in desteklediği ayarlar gösterilir." },
} as const;

function fixedMinutes(name: string): number | null {
  const m = /^UTC(?:([+-])(\d{1,2})(?::(00|15|30|45))?)?$/.exec(name);
  if (!m) return null;
  const minutes = (Number(m[2] || 0) * 60 + Number(m[3] || 0)) * (m[1] === "-" ? -1 : 1);
  return minutes >= -720 && minutes <= 840 ? minutes : null;
}
function fixedName(minutes: number): string {
  if (!minutes) return "UTC";
  const a = Math.abs(minutes), mm = a % 60;
  return `UTC${minutes < 0 ? "-" : "+"}${Math.floor(a / 60)}${mm ? `:${String(mm).padStart(2, "0")}` : ""}`;
}
function unhookImportedDevices(config: QHomeConfig, removedIds: string[]): number {
  const missing = new Set(removedIds.filter(id => !config.components.some(component => component.id === id)));
  if (!missing.size) return 0;
  const usesMissing = (block: Record<string, unknown> | undefined): boolean => {
    for (let current = block; current; current = (current.next as { block?: Record<string, unknown> } | undefined)?.block) {
      const fields = current.fields as Record<string, unknown> | undefined;
      if (["ENT", "SRC"].some(field => missing.has(String(fields?.[field] ?? "")))) return true;
      const inputs = current.inputs as Record<string, { block?: Record<string, unknown>; shadow?: Record<string, unknown> }> | undefined;
      if (Object.values(inputs ?? {}).some(slot => usesMissing(slot.block ?? slot.shadow))) return true;
    }
    return false;
  };
  let disabled = 0;
  const tops = config.scripts?.workspace?.blocks as { blocks?: Array<Record<string, unknown>> } | undefined;
  for (const top of tops?.blocks ?? []) {
    const reasons = top.disabledReasons as unknown[] | undefined;
    if (/^ev_/.test(String(top.type ?? "")) && top.enabled !== false && !(reasons?.length) && usesMissing(top)) {
      top.disabledReasons = ["MANUALLY_DISABLED"]; disabled++;
    }
  }
  for (const component of config.components) {
    if (component.type !== "led_matrix" || !component.props || !missing.has(String(component.props.source ?? ""))) continue;
    component.props.source = "";
    if (component.props.mode === "value" || component.props.mode === "bar") component.props.mode = "text";
  }
  return disabled;
}
function timeAt(epoch: number, timezone: string, language: Language): string {
  try {
    const fixed = fixedMinutes(timezone);
    const date = new Date((epoch + (fixed ?? 0) * 60) * 1000);
    if (fixed !== null) return `${new Intl.DateTimeFormat(language, { timeZone: "UTC", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }).format(date)} · ${timezone}`;
    return new Intl.DateTimeFormat(language, { timeZone: timezone, dateStyle: "medium", timeStyle: "medium" }).format(new Date(epoch * 1000));
  } catch { return timezone; }
}

export function SettingsPage({ data, language, onSaved, onDirtyChange }: Props) {
  const tr = language === "tr", s = text[language];
  const [draft, setDraft] = useState<QHomeConfig>(() => clone(data.config));
  const [saving, setSaving] = useState(false), [error, setError] = useState(""), [notice, setNotice] = useState("");
  const [ports, setPorts] = useState<Array<{ name: string; busy?: boolean }> | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const dirty = useMemo(() => JSON.stringify(draft) !== JSON.stringify(data.config), [draft, data.config]);
  const device = draft.device, mqtt = draft.mqtt ?? {};
  const zones = data.meta.tz?.zones ?? [], fixed = data.meta.tz?.fixed ?? [];
  const currentZone = String(device.tz ?? data.meta.tz?.default ?? "UTC");
  const currentFixed = fixed.includes(currentZone) || fixedMinutes(currentZone) !== null || !currentZone.includes("/");
  const selectedRegion = currentFixed ? "*" : currentZone.split("/")[0];
  const regions = [...new Set(zones.map(zone => zone.split("/")[0]))];
  if (selectedRegion !== "*" && !regions.includes(selectedRegion)) regions.push(selectedRegion);
  const zoneOptions = selectedRegion === "*" ? [...fixed] : zones.filter(zone => zone.startsWith(`${selectedRegion}/`));
  if (!zoneOptions.includes(currentZone)) zoneOptions.push(currentZone);
  const update = (section: "device" | "mqtt", key: string, value: unknown) => {
    setDraft(old => ({ ...old, [section]: { ...(old[section] as Record<string, unknown>), [key]: value } }));
    setError(""); setNotice("");
  };
  useEffect(() => { onDirtyChange(dirty); }, [dirty, onDirtyChange]);
  useEffect(() => { let live = true; api.getPorts().then(value => { if (live) setPorts(value); }).catch(() => { if (live) setError(s.loadError); }); return () => { live = false; }; }, []);
  useEffect(() => { if (!dirty) setDraft(clone(data.config)); }, [data.config, dirty]);

  async function save() {
    const issues: string[] = [];
    const nodeName = String(draft.device.node ?? "");
    if (!/^[a-z0-9_-]{1,32}$/.test(nodeName)) issues.push(tr ? "Düğüm adı 1–32 küçük harf, rakam, - veya _ içermeli." : "Node name must be 1–32 lowercase letters, digits, - or _.");
    const tz = draft.device.tz;
    if (typeof tz !== "string" || !tz) issues.push(tr ? "Bir saat dilimi seçin." : "Choose a time zone.");
    if (draft.device.role === "node" && data.meta.has_local) {
      if (!String(draft.device.master_host ?? "").trim()) issues.push(tr ? "Ana kart adresini girin." : "Enter the master address.");
      const port = Number(draft.device.master_port ?? 1883);
      if (!Number.isInteger(port) || port < 1 || port > 65535) issues.push(tr ? "MQTT portu 1–65535 arasında olmalı." : "MQTT port must be between 1 and 65535.");
    }
    if (issues.length) { setError(issues.join(" ")); return; }
    setSaving(true); setError(""); setNotice("");
    try {
      const result = await api.saveConfig(draft);
      if (!result.ok) throw new Error(result.errors?.join("; ") || s.saveError);
      api.setWebPassword(String(draft.device.web_password ?? ""));
      setDraft(clone(draft)); setNotice(result.restart ? s.restart : s.saved);
      await onSaved();
    } catch (cause) { setError(cause instanceof Error ? cause.message : s.saveError); }
    finally { setSaving(false); }
  }
  function discard() { setDraft(clone(data.config)); setError(""); setNotice(""); }
  async function importFile(file?: File) {
    if (!file) return;
    try {
      const imported = JSON.parse(await file.text()) as QHomeConfig;
      if (!imported || !imported.device || !Array.isArray(imported.components)) throw new Error("shape");
      imported.boards ??= [{ id: "main", name: "UNO Q", model: "unoq", link: { type: "local" } }];
      for (const component of imported.components) {
        if (!component.board && data.meta.types[component.type]?.cap) component.board = "main";
      }
      imported.scripts ??= { workspace: {} };
      if (imported.device.tz === undefined && imported.device.tz_offset !== undefined) { const offset = Number(imported.device.tz_offset); imported.device.tz = Number.isFinite(offset) ? fixedName(offset * 60) : data.meta.tz?.default ?? "UTC"; }
      delete imported.device.tz_offset;
      delete imported.automations;
      const oldUnoqIds = imported.boards.filter(board => board.model === "unoq").map(board => board.id);
      const removed = imported.components.filter(component => oldUnoqIds.includes(component.board ?? "") && Number.isInteger(component.pin) && Number(component.pin) >= 25);
      imported.components = imported.components.filter(component => !removed.includes(component));
      const disabled = unhookImportedDevices(imported, removed.map(component => component.id));
      setDraft(imported); setError(""); setNotice(removed.length ? s.importReady + " " + s.importedDropped.replace("{0}", String(removed.length)).replace("{1}", String(disabled)) : s.importReady);
    } catch { setError(s.importBad); }
    finally { if (fileRef.current) fileRef.current.value = ""; }
  }
  const role = String(device.role ?? "master"), mqttMode = String(mqtt.mode ?? "internal");
  const browserZone = (() => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone || ""; } catch { return ""; } })();
  const browserZoneFallback = browserZone && !zones.includes(browserZone) ? fixedName(-new Date().getTimezoneOffset()) : browserZone;
  const epoch = data.snapshot.time?.epoch ?? Date.now() / 1000;
  const openPorts = ports ?? [];
  return <section className="settings-page">
    <header className="page-heading settings-heading"><div><p className="eyebrow">QHOME · CONFIGURATION</p><h1>{s.title}</h1><p className="page-description">{s.subtitle}</p></div></header>
    <p className="settings-supported">{s.readOnlyInfo}</p>
    {error && <div className="boards-error" role="alert"><span>{error}</span><button onClick={() => setError("")} aria-label={tr ? "Kapat" : "Dismiss"}>×</button></div>}
    {notice && <div className="boards-notice" role="status">{notice}</div>}
    <div className="settings-grid">
      <section className="panel settings-panel"><h2>{s.device}</h2>
        <label>{s.name}<input value={String(device.name ?? "")} onChange={e => update("device", "name", e.target.value)} /></label>
        <label>{s.node}<small>{s.nodeHint}</small><input value={String(device.node ?? "")} onChange={e => update("device", "node", e.target.value)} autoComplete="off" /></label>
        <label>{s.password}<small>{s.passwordHint}</small><input type="password" value={String(device.web_password ?? "")} onChange={e => update("device", "web_password", e.target.value)} autoComplete="new-password" /></label>
        <p className="settings-url">{location.origin}</p>
      </section>
      <section className="panel settings-panel"><h2>{s.timezone}</h2>
        <div className="settings-two-col"><label>{s.region}<select value={selectedRegion} onChange={e => {
          const region = e.target.value;
          if (region === "*") update("device", "tz", fixed.includes(currentZone) ? currentZone : fixedName(data.snapshot.time?.offset ?? 0));
          else update("device", "tz", zones.find(zone => zone.startsWith(`${region}/`)) ?? currentZone);
        }}><option value="*">{s.fixed}</option>{regions.map(region => <option key={region} value={region}>{region}</option>)}</select></label>
          <label>{s.city}<select value={currentZone} onChange={e => update("device", "tz", e.target.value)}>{zoneOptions.map(zone => <option key={zone} value={zone}>{selectedRegion === "*" ? zone : zone.slice(selectedRegion.length + 1).replace(/_/g, " ").replace(/\//g, " / ")}</option>)}</select></label></div>
        {browserZoneFallback && browserZoneFallback !== currentZone && <button className="secondary-button settings-browser-zone" onClick={() => update("device", "tz", browserZoneFallback)}>{s.browserZone}: {browserZoneFallback}</button>}
        {data.meta.tz?.db === false && <div className="boards-warning">{s.timezoneDb}</div>}
        <div className="settings-clock"><span>{s.clockNow}</span><strong>{timeAt(epoch, String(data.snapshot.time?.tz ?? currentZone), language)}</strong><span>{s.clockAfter}</span><strong>{timeAt(epoch, currentZone, language)}</strong></div>
      </section>
      {data.meta.has_local && <section className="panel settings-panel"><h2>{s.role}</h2><div className="settings-segment" role="group" aria-label={s.role}><button aria-pressed={role === "master"} onClick={() => update("device", "role", "master")}>{s.master}</button><button aria-pressed={role === "node"} onClick={() => update("device", "role", "node")}>{s.nodeRole}</button></div><p className="settings-hint">{role === "node" ? s.nodeInfo : s.masterInfo}</p>
        {role === "node" && <><label>{s.masterHost}<input value={String(device.master_host ?? "")} onChange={e => update("device", "master_host", e.target.value)} /></label><label>{s.masterPort}<input type="number" min={1} max={65535} value={Number(device.master_port ?? 1883)} onChange={e => update("device", "master_port", Number(e.target.value))} /></label><div className="settings-two-col"><label>{s.masterUser}<input value={String(device.master_user ?? "")} onChange={e => update("device", "master_user", e.target.value)} /></label><label>{s.masterPass}<input type="password" autoComplete="new-password" value={String(device.master_pass ?? "")} onChange={e => update("device", "master_pass", e.target.value)} /></label></div></>}
      </section>}
      {role !== "node" && <section className="panel settings-panel"><h2>{s.mqtt}</h2><div className="settings-segment" role="group" aria-label={s.mqtt}>{([["internal", s.internal], ["external", s.external], ["off", s.off]] as const).map(([value, label]) => <button key={value} aria-pressed={mqttMode === value} onClick={() => update("mqtt", "mode", value)}>{label}</button>)}</div>
        {mqttMode === "internal" && <><label>{s.mqttPort}<input type="number" min={1} max={65535} value={Number(mqtt.port ?? 1883)} onChange={e => update("mqtt", "port", Number(e.target.value))} /></label><div className="settings-two-col"><label>{s.username}<input value={String(mqtt.username ?? "")} onChange={e => update("mqtt", "username", e.target.value)} /></label><label>{s.mqttPass}<input type="password" autoComplete="new-password" value={String(mqtt.password ?? "")} onChange={e => update("mqtt", "password", e.target.value)} /></label></div><p className="settings-hint">{s.ha} · {location.hostname}:{Number(mqtt.port ?? 1883)}</p>{!mqtt.username && <p className="boards-warning">{s.insecure}</p>}</>}
        {mqttMode === "external" && <><div className="settings-two-col"><label>{s.mqttHost}<input value={String(mqtt.host ?? "")} onChange={e => update("mqtt", "host", e.target.value)} /></label><label>{s.mqttPort}<input type="number" min={1} max={65535} value={Number(mqtt.ext_port ?? 1883)} onChange={e => update("mqtt", "ext_port", Number(e.target.value))} /></label></div><div className="settings-two-col"><label>{s.username}<input value={String(mqtt.username ?? "")} onChange={e => update("mqtt", "username", e.target.value)} /></label><label>{s.mqttPass}<input type="password" autoComplete="new-password" value={String(mqtt.password ?? "")} onChange={e => update("mqtt", "password", e.target.value)} /></label></div><p className="settings-hint">{tr ? "Harici sunucu ayarı kaydedildiğinde backend bu broker'a bağlanmayı dener." : "When saved, the backend will try to connect to this broker."}</p></>}
        {mqttMode !== "off" && <><label className="settings-checkbox"><input type="checkbox" checked={mqtt.discovery !== false} onChange={e => update("mqtt", "discovery", e.target.checked)} />{s.discovery}</label><label>{s.prefix}<small>{s.prefixHint}</small><input value={String(mqtt.prefix ?? "homeassistant")} onChange={e => update("mqtt", "prefix", e.target.value)} /></label><p className="settings-hint">{s.topics.replace("{0}", String(device.node ?? "qhome"))}</p></>}
      </section>}
      {!data.meta.role.includes("node") && <section className="panel settings-panel"><h2>{s.usb}</h2><p className="settings-hint">{s.usbHelp.replace("{0}", String(data.meta.link_port ?? "-"))}</p>{ports === null ? <p className="settings-muted"><span className="spinner spinner-small" /> {tr ? "Yükleniyor…" : "Loading…"}</p> : openPorts.length ? <ul className="settings-port-list">{openPorts.map(port => <li key={port.name}>{port.name}{port.busy ? ` (${s.busy})` : ""}</li>)}</ul> : <p className="settings-muted">{s.noPorts}</p>}</section>}
      <section className="panel settings-panel"><h2>{s.backup}</h2><div className="settings-actions"><a className="secondary-button" href="/api/export" download="qhome-config.json">{s.export}</a><button className="secondary-button" onClick={() => fileRef.current?.click()}>{s.import}</button><input ref={fileRef} type="file" accept=".json,application/json" hidden onChange={e => void importFile(e.target.files?.[0])} /></div></section>
    </div>
    <div className="settings-savebar" aria-live="polite"><span>{dirty ? s.dirty : notice}</span><button className="secondary-button" disabled={!dirty || saving} onClick={discard}>{s.discard}</button><button className="primary-button" disabled={!dirty || saving} onClick={() => void save()}>{saving ? s.saving : s.save}</button></div>
  </section>;
}
