import { useEffect, useMemo, useState } from "react";
import { Fragment, type CSSProperties, type FormEvent, type ReactNode } from "react";
import { api } from "../services/api";
import type { ApiContext, BoardConfig, BoardModel, BoardPart, ComponentConfig, DevicePropertyDefinition, DiscoveredBoard, ModelPin, QHomeConfig, SerialPortInfo } from "../types/api";
import { StatusBadge } from "../components/StatusBadge";
import type { Language } from "../i18n";

interface Props { data: ApiContext; language: Language; onSaved: () => Promise<void>; onDirtyChange: (dirty: boolean) => void; }
type Selection = { kind: "pin"; boardId: string; pin: string | number } | { kind: "component"; id: string } | null;
type LinkType = "local" | "usb" | "uart" | "i2c" | "wifi";
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;
const idPattern = /^[a-z][a-z0-9_]{0,31}$/;
const warningNotes = new Set(["strap", "boot_low", "boot_btn", "in_only"]);
const colorByValue: Record<string, string> = { red: "#e5564d", green: "#35a66f", yellow: "#e8b83c", blue: "#4e88dc", magenta: "#bd68c8", cyan: "#38b9bd", white: "#f5f5ee", off: "#66746e" };
const words = {
    en: {
    title: "Boards & Pins", subtitle: "Configure boards, communication links, pins and connected components.", addBoard: "Add board", none: "No boards configured", noBoards: "Add a board to begin assigning pins and devices.", edit: "Edit", remove: "Remove board", save: "Save changes", discard: "Discard", saved: "Board configuration saved.", saving: "Saving…", dirty: "You have unsaved board changes.", cancel: "Cancel", add: "Add", done: "Done", name: "Name", id: "Board ID", model: "Board model", link: "Connection type", port: "Serial port", auto: "Automatic port", baud: "Baud rate", bus: "I²C bus", address: "I²C address", board: "Board", online: "Online", offline: "Offline", pin: "Pin", selectPin: "Select a pin", selectHint: "Select a pin to see compatible components, or select a configured component to edit it.", free: "Available pin", reserved: "Reserved pin", used: "Configured pin", cap: "Capabilities", notes: "Electrical notes", occupied: "Used by", chooseDevice: "Add a compatible component", noCompatible: "No component type is compatible with this pin.", list: "Pin list", drawing: "Board drawing", virtual: "Virtual devices", addVirtual: "Add virtual switch", noVirtual: "No virtual devices configured.", component: "Component", compName: "Component name", compId: "Component ID", assignPin: "Assigned pin", removeComp: "Remove component", close: "Close inspector", properties: "Component settings", warning: "Caution", found: "Discovered boards", ignore: "Ignore", foundAdd: "Configure and add", noFound: "No unconfigured boards discovered.", linkInfo: "Link information", wiring: "Wiring / firmware setup", unsavedNav: "Discard unsaved board changes and leave this page?", confirmBoardRemove: "Remove board {0} and its {1} configured component(s)?", confirmCompRemove: "Remove component {0}? Existing automation references may need repair.", invalidId: "Use 1–32 lowercase letters, digits or underscores; start with a letter.", duplicateBoard: "This board ID is already in use.", duplicateComp: "This component ID is already in use.", badAddress: "I²C address must be between 8 and 119 and must be unique.", missingName: "Enter a board name.", noLocal: "Only one local board is supported.", unsupportedLink: "This connection is not supported by the selected model.", noModel: "Unknown board model.", portsFailed: "Serial ports could not be loaded.", backendFailed: "Could not load or save board configuration.", tryAgain: "Try again", legend: "Pin capabilities", otherBoard: "Actual board model differs from configured model.", fwUnoQ: "Configure the UNO Q node firmware with this board ID, master host and MQTT port.", fwOther: "Use the firmware link settings shown below when preparing this board.", local: "Host board", usb: "USB serial", uart: "UART", i2c: "I²C", wifi: "Wi-Fi", hostUart: "Used by a hosted UART connection", hostI2c: "Used by a hosted I²C connection", serialReserved: "Reserved for serial link", i2cReserved: "Reserved for I²C link", duplicate: "Already assigned", loading: "Loading board configuration…", noCaps: "This pin has no supported capabilities.", ignoreClear: "Show ignored discoveries", dismiss: "Dismiss", firmwareNote: "Firmware guidance only; this interface does not flash firmware.", updateError: "Configuration validation failed.", linked: "Connected", notLinked: "Not connected", configMissing: "Configured board is unavailable.", refError: "Could not update configuration.",
  },
  tr: {
    title: "Kartlar ve Pinler", subtitle: "Kartları, iletişim bağlantılarını, pinleri ve bağlı bileşenleri yapılandırın.", addBoard: "Kart ekle", none: "Yapılandırılmış kart yok", noBoards: "Pin ve cihaz atamak için bir kart ekleyin.", edit: "Düzenle", remove: "Kartı sil", save: "Değişiklikleri kaydet", discard: "Vazgeç", saved: "Kart yapılandırması kaydedildi.", saving: "Kaydediliyor…", dirty: "Kaydedilmemiş kart değişiklikleri var.", cancel: "İptal", add: "Ekle", done: "Tamam", name: "Ad", id: "Kart kimliği", model: "Kart modeli", link: "Bağlantı türü", port: "Seri port", auto: "Otomatik port", baud: "Baud hızı", bus: "I²C veri yolu", address: "I²C adresi", board: "Kart", online: "Çevrimiçi", offline: "Çevrimdışı", pin: "Pin", selectPin: "Bir pin seçin", selectHint: "Uyumlu bileşenleri görmek için pin seçin veya düzenlemek için tanımlı bir bileşeni seçin.", free: "Kullanılabilir pin", reserved: "Ayrılmış pin", used: "Yapılandırılmış pin", cap: "Yetenekler", notes: "Elektriksel notlar", occupied: "Kullanan cihaz", chooseDevice: "Uyumlu bileşen ekle", noCompatible: "Bu pinle uyumlu bileşen türü yok.", list: "Pin listesi", drawing: "Kart çizimi", virtual: "Sanal cihazlar", addVirtual: "Sanal anahtar ekle", noVirtual: "Yapılandırılmış sanal cihaz yok.", component: "Bileşen", compName: "Bileşen adı", compId: "Bileşen kimliği", assignPin: "Atanan pin", removeComp: "Bileşeni sil", close: "Denetçiyi kapat", properties: "Bileşen ayarları", warning: "Dikkat", found: "Bulunan kartlar", ignore: "Yok say", foundAdd: "Yapılandır ve ekle", noFound: "Yapılandırılmamış kart bulunamadı.", linkInfo: "Bağlantı bilgisi", wiring: "Kablo / firmware kurulumu", unsavedNav: "Kaydedilmemiş kart değişikliklerini silip bu sayfadan çıkılsın mı?", confirmBoardRemove: "{0} kartı ve yapılandırılmış {1} bileşeni silinsin mi?", confirmCompRemove: "{0} bileşeni silinsin mi? Otomasyon başvurularını düzeltmeniz gerekebilir.", invalidId: "1–32 küçük harf, rakam veya alt çizgi kullanın; harfle başlayın.", duplicateBoard: "Bu kart kimliği zaten kullanılıyor.", duplicateComp: "Bu bileşen kimliği zaten kullanılıyor.", badAddress: "I²C adresi 8–119 arasında ve benzersiz olmalı.", missingName: "Kart adı girin.", noLocal: "Yalnızca bir yerel kart desteklenir.", unsupportedLink: "Bu kart modeli seçilen bağlantıyı desteklemiyor.", noModel: "Bilinmeyen kart modeli.", portsFailed: "Seri portlar yüklenemedi.", backendFailed: "Kart yapılandırması yüklenemedi veya kaydedilemedi.", tryAgain: "Yeniden dene", legend: "Pin yetenekleri", otherBoard: "Gerçek kart modeli, yapılandırılan modelden farklı.", fwUnoQ: "UNO Q düğüm firmware'ini bu kart kimliği, ana bilgisayar ve MQTT portuyla yapılandırın.", fwOther: "Bu kartı hazırlarken aşağıda belirtilen firmware bağlantı ayarlarını kullanın.", local: "Ana kart", usb: "USB seri", uart: "UART", i2c: "I²C", wifi: "Wi-Fi", hostUart: "Ana kartta ayrılmış UART bağlantısı", hostI2c: "Ana kartta ayrılmış I²C bağlantısı", serialReserved: "Seri bağlantı için ayrılmış", i2cReserved: "I²C bağlantısı için ayrılmış", duplicate: "Zaten atanmış", loading: "Kart yapılandırması yükleniyor…", noCaps: "Bu pin için desteklenen yetenek yok.", ignoreClear: "Yok sayılanları göster", dismiss: "Kapat", firmwareNote: "Yalnızca firmware yönergesidir; bu arayüz firmware yüklemez.", updateError: "Yapılandırma doğrulaması başarısız.", linked: "Bağlı", notLinked: "Bağlı değil", configMissing: "Yapılandırılmış kart kullanılamıyor.", refError: "Yapılandırma güncellenemedi.",
  },
} as const;
type Key = keyof typeof words.en;
function capabilityNames(tr: boolean): Record<string, string> { return tr ? { din: "Dijital giriş", dout: "Dijital çıkış", adc: "Analog giriş", pwm: "PWM", dac: "DAC", cnt: "Sayaç", rgb: "RGB", matrix: "Matris" } : { din: "Digital input", dout: "Digital output", adc: "Analog input", pwm: "PWM", dac: "DAC", cnt: "Counter", rgb: "RGB", matrix: "Matrix" }; }
function componentTypeName(type: ComponentConfig["type"], tr: boolean) { const labels: Record<ComponentConfig["type"], [string, string]> = { binary_input: ["Binary input", "Dijital giriş"], analog_sensor: ["Analog sensor", "Analog sensör"], pulse_counter: ["Pulse counter", "Darbe sayacı"], switch_output: ["Switch output", "Anahtar çıkışı"], pwm_output: ["PWM output", "PWM çıkışı"], dac_output: ["DAC output", "DAC çıkışı"], rgb_led: ["RGB LED", "RGB LED"], led_matrix: ["LED matrix", "LED matrisi"], virtual_switch: ["Virtual switch", "Sanal anahtar"] }; return labels[type][tr ? 1 : 0]; }
function componentTag(type: ComponentConfig["type"]) { return ({ binary_input: "DI", analog_sensor: "AI", pulse_counter: "CNT", switch_output: "DO", pwm_output: "PWM", dac_output: "AO", rgb_led: "RGB", led_matrix: "MX", virtual_switch: "VS" } as const)[type]; }
function pinGroupName(name: string, tr: boolean) { const labels: Record<string, [string, string]> = { digital: ["Digital", "Dijital"], analog: ["Analog", "Analog"], onboard: ["On-board", "Kart üstü"], jspi: ["JSPI", "JSPI"], pins: ["Pins", "Pinler"] }; const key = name.toLowerCase(); return labels[key]?.[tr ? 1 : 0] ?? name; }
function pinNote(note: string, tr: boolean) { const texts: Record<string, [string, string]> = { uart_rx: ["Serial RX", "Seri RX"], uart_tx: ["Serial TX", "Seri TX"], no5v: ["Never apply more than 3.3 V", "3,3 V üstü gerilim uygulamayın"], ain3v3: ["Analog input: 3.3 V maximum", "Analog giriş: en çok 3,3 V"], can_tx: ["Also CAN TX", "Ayrıca CAN TX"], can_rx: ["Also CAN RX", "Ayrıca CAN RX"], spi_ss: ["Also SPI SS", "Ayrıca SPI SS"], spi_mosi: ["Also SPI COPI", "Ayrıca SPI COPI"], spi_miso: ["Also SPI CIPO", "Ayrıca SPI CIPO"], spi_sck: ["Also SPI SCK", "Ayrıca SPI SCK"], i2c_sda: ["Also I²C SDA", "Ayrıca I²C SDA"], i2c_scl: ["Also I²C SCL", "Ayrıca I²C SCL"], pwm_core: ["PWM requires a recent UNO Q core; use a ~ pin if dimming does not work.", "PWM için güncel UNO Q çekirdeği gerekir; çalışmazsa ~ işaretli pin kullanın."], jspi: ["On the 6-pin SPI header", "6 pinli SPI başlığında"], led_linux: ["Driven by Linux", "Linux tarafından sürülür"], led_status: ["Normally shows system status", "Normalde sistem durumunu gösterir"], strap: ["Boot pin: its power-up level changes startup behavior.", "Açılış pini: açılış seviyesi kartın başlama biçimini etkiler."], boot_low: ["Must be LOW at power-up or the board will not start.", "Kartın başlaması için açılışta LOW olmalı."], boot_btn: ["Shared with BOOT/FLASH; usable as a button after startup.", "BOOT/FLASH ile ortak; açılıştan sonra düğme olarak kullanılabilir."], boot_out: ["Briefly sends signals while the board starts.", "Kart açılırken kısa süre sinyal verir."], in_only: ["Input only; no internal pull-up or pull-down.", "Yalnızca giriş; dahili pull-up/pull-down yok."], no_pullup: ["No internal pull-up and no pulse counting.", "Dahili pull-up ve darbe sayımı yok."], led_builtin_low: ["Shared with built-in LED (active low).", "Kart üstü LED ile ortak (LOW iken yanar)."], adc_2v5: ["Analog input measures up to about 2.5 V.", "Analog giriş yaklaşık 2,5 V'a kadar ölçer."], a0_3v3: ["NodeMCU: 0–3.3 V (bare ESP-12: 0–1 V).", "NodeMCU: 0–3,3 V (çıplak ESP-12: 0–1 V)."], uart2_rx: ["Serial2 RX", "Seri2 RX"], uart2_tx: ["Serial2 TX", "Seri2 TX"], dac8: ["8-bit analog output", "8 bit analog çıkış"], led_mcu: ["Driven by the microcontroller", "Mikrodenetleyici tarafından sürülür"], matrix_13x8: ["13 × 8 LEDs, 8 brightness levels", "13 × 8 LED, 8 parlaklık seviyesi"], ain_only: ["Analog input only", "Yalnızca analog giriş"], led_builtin: ["Shared with built-in LED", "Kart üstü LED ile ortak"] }; return texts[note]?.[tr ? 1 : 0] ?? note.replaceAll("_", " "); }
const capColors: Record<string, string> = { din: "#58b8c7", dout: "#51ba87", adc: "#a381de", pwm: "#ec9c54", dac: "#dc7b9c", cnt: "#dfbd55", rgb: "#5996df", matrix: "#75c2bd" };

function reservedPins(board: BoardConfig, boards: BoardConfig[], models: Record<string, BoardModel>) {
  const model = models[board.model]; const reserved: Record<string, string> = {}; if (!model) return reserved;
  const type = board.link?.type;
  if (type === "uart") for (const p of model.uart_pins || model.serial_pins || []) reserved[String(p)] = "serial";
  if (type === "usb" && model.usb_shares_uart) for (const p of model.serial_pins || []) reserved[String(p)] = "serial";
  if (type === "i2c") for (const p of model.i2c_pins || []) reserved[String(p)] = "i2c";
  if (type === "local") for (const other of boards) {
    if (other.id === board.id) continue;
    if (other.link?.type === "uart") for (const p of model.uart_pins || model.serial_pins || []) reserved[String(p)] = "hostUart";
    if (other.link?.type === "i2c" && (other.link.bus ?? "wire") === "wire") for (const p of model.i2c_pins || []) reserved[String(p)] = "hostI2c";
  }
  return reserved;
}
function defaultProps(definitions: DevicePropertyDefinition[]) { return Object.fromEntries(definitions.map(def => [def.key, def.default])); }
function slug(value: string) { return value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^[^a-z]+/, "").replace(/_+$/, "").slice(0, 24); }
function settingName(key: string, tr: boolean) {
  const values: Record<string, [string, string]> = { pull: ["Pull resistor", "Pull direnci"], invert: ["Invert input", "Girişi tersle"], debounce: ["Debounce (ms)", "Sıçrama önleme (ms)"], interval: ["Sampling interval (ms)", "Örnekleme aralığı (ms)"], calib: ["Calibration", "Kalibrasyon"], in_min: ["Input minimum", "Giriş alt sınırı"], in_max: ["Input maximum", "Giriş üst sınırı"], out_min: ["Output minimum", "Çıkış alt sınırı"], out_max: ["Output maximum", "Çıkış üst sınırı"], unit: ["Unit", "Birim"], decimals: ["Decimals", "Ondalık basamak"], avg: ["Averaging samples", "Ortalama örnek sayısı"], delta: ["Minimum change", "En küçük değişim"], restore: ["Restore state", "Durum geri yükleme"], ha_as: ["Home Assistant entity", "Home Assistant varlığı"], min_pct: ["Minimum percent", "En düşük yüzde"], max_pct: ["Maximum percent", "En yüksek yüzde"], brightness: ["Brightness", "Parlaklık"], mode: ["Display mode", "Görüntüleme modu"], startup_text: ["Startup text", "Başlangıç metni"], source: ["Value source", "Değer kaynağı"], bar_style: ["Bar style", "Çubuk stili"], bar_min: ["Bar minimum", "Çubuk alt sınırı"], bar_max: ["Bar maximum", "Çubuk üst sınırı"], graph_secs: ["Graph duration (s)", "Grafik süresi (sn)"], anim: ["Animation", "Animasyon"], speed: ["Speed", "Hız"], icon: ["Icon", "Simge"], clock_12h: ["12-hour clock", "12 saat biçimi"], scroll_ms: ["Scroll interval (ms)", "Kaydırma aralığı (ms)"], device_class: ["Sensor class", "Sensör sınıfı"], multiplier: ["Multiplier", "Çarpan"] };
  return values[key]?.[tr ? 1 : 0] ?? key.replaceAll("_", " ");
}

export function BoardsPage({ data, language, onSaved, onDirtyChange }: Props) {
  const tr = language === "tr"; const t = (key: Key) => words[language][key];
  const capNames = capabilityNames(tr);
  const [draft, setDraft] = useState<QHomeConfig>(() => clone(data.config));
  const [selectedBoard, setSelectedBoard] = useState<string | null>(draft.boards[0]?.id ?? null);
  const [selection, setSelection] = useState<Selection>(null);
  const [view, setView] = useState<"drawing" | "list">(() => localStorage.getItem("qhome.boardview") === "list" ? "list" : "drawing");
  const [dialog, setDialog] = useState<BoardConfig | DiscoveredBoard | "new" | null>(null);
  const [ports, setPorts] = useState<SerialPortInfo[]>([]); const [portsError, setPortsError] = useState(false);
  const [portsLoading, setPortsLoading] = useState(false);
  const [ignored, setIgnored] = useState<string[]>(() => { try { return JSON.parse(localStorage.getItem("qhome.found.ignored") || "[]") as string[]; } catch { return []; } });
  const [showIgnored, setShowIgnored] = useState(false); const [saving, setSaving] = useState(false); const [pageError, setPageError] = useState<string | null>(null); const [notice, setNotice] = useState("");
  const dirty = useMemo(() => JSON.stringify(draft) !== JSON.stringify(data.config), [draft, data.config]);
  useEffect(() => onDirtyChange(dirty), [dirty, onDirtyChange]);
  useEffect(() => { setDraft(clone(data.config)); setSelectedBoard(current => data.config.boards.some(b => b.id === current) ? current : data.config.boards[0]?.id ?? null); }, [data.config]);
  useEffect(() => { if (dialog === null) return; let active = true; setPortsLoading(true); void api.getPorts().then(value => { if (active) { setPorts(value); setPortsError(false); } }).catch(() => { if (active) setPortsError(true); }).finally(() => { if (active) setPortsLoading(false); }); return () => { active = false; }; }, [dialog]);
  const currentBoard = draft.boards.find(board => board.id === selectedBoard) ?? null;
  const boardState = currentBoard ? data.snapshot.boards[currentBoard.id] : undefined;
  const model = currentBoard ? data.meta.models[currentBoard.model] : undefined;
  const virtualComponents = draft.components.filter(c => !data.meta.types[c.type]?.cap);
  const reserved = currentBoard ? reservedPins(currentBoard, draft.boards, data.meta.models) : {};
  const found = (data.snapshot.discovered ?? []).filter(item => item.key && !draft.boards.some(board => item.link === "wifi" ? board.id === item.id : board.link?.type === "usb" && board.link.port === item.port));
  const visibleFound = found.filter(item => showIgnored || !ignored.includes(item.key));
  const updateComponent = (id: string, transform: (component: ComponentConfig) => ComponentConfig) => { setNotice(""); setDraft(prev => ({ ...prev, components: prev.components.map(component => component.id === id ? transform(component) : component) })); };
  const save = async () => {
    setSaving(true); setPageError(null); setNotice("");
    try { const result = await api.saveConfig(draft); if (!result.ok) { setPageError((result.errors ?? [t("updateError")]).join(" • ")); return; } await onSaved(); setNotice(t("saved")); }
    catch (error) { setPageError(error instanceof Error ? error.message : t("backendFailed")); }
    finally { setSaving(false); }
  };
  const discard = () => { setDraft(clone(data.config)); setSelection(null); setSelectedBoard(data.config.boards[0]?.id ?? null); setPageError(null); setNotice(""); };
  const addComponent = (type: ComponentConfig["type"], boardId: string | null, pin?: string | number) => {
    const prefix: Record<ComponentConfig["type"], string> = { binary_input: "input", analog_sensor: "sensor", pulse_counter: "counter", switch_output: "relay", pwm_output: "dimmer", dac_output: "analog_out", rgb_led: "led", led_matrix: "matrix", virtual_switch: "flag" };
    const base = prefix[type]; let n = 1; while (draft.components.some(component => component.id === `${base}${n}`)) n++;
    const id = `${base}${n}`; const def = data.meta.types[type]; const props = defaultProps(def.props);
    const target = draft.boards.find(board => board.id === boardId); const pinInfo = target && data.meta.models[target.model]?.pins.find(item => String(item.id) === String(pin));
    if (type === "analog_sensor" && target && data.meta.models[target.model]?.vref !== 3.3) props.in_max = data.meta.models[target.model]?.vref ?? 5;
    if (type === "binary_input" && pinInfo?.notes.some(note => note === "in_only" || note === "no_pullup")) props.pull = "none";
    const component: ComponentConfig = { id, type, name: `${componentTypeName(type, tr)} ${n}`, board: boardId, ...(pin === undefined ? {} : { pin }), props };
      setDraft(prev => ({ ...prev, components: [...prev.components, component] })); setSelection({ kind: "component", id }); setPageError(null); setNotice("");
  };
  const selectPin = (board: BoardConfig, pin: ModelPin) => {
    const component = draft.components.find(item => item.board === board.id && String(item.pin) === String(pin.id));
    setSelection(component ? { kind: "component", id: component.id } : { kind: "pin", boardId: board.id, pin: pin.id });
  };
  const removeBoard = (board: BoardConfig) => {
    const count = draft.components.filter(component => component.board === board.id).length;
    const message = t("confirmBoardRemove").replace("{0}", board.name || board.id).replace("{1}", String(count));
    if (!window.confirm(message)) return;
    setDraft(prev => ({ ...prev, boards: prev.boards.filter(item => item.id !== board.id), components: prev.components.filter(component => component.board !== board.id) })); setNotice("");
    setSelection(null); const next = draft.boards.find(item => item.id !== board.id); setSelectedBoard(next?.id ?? null);
  };
  const removeComponent = (component: ComponentConfig) => {
    if (!window.confirm(t("confirmCompRemove").replace("{0}", component.id))) return;
    setDraft(prev => ({ ...prev, components: prev.components.filter(item => item.id !== component.id).map(item => item.type === "led_matrix" && item.props?.source === component.id ? { ...item, props: { ...item.props, source: "", ...(item.props.mode === "value" || item.props.mode === "bar" ? { mode: "text" } : {}) } } : item) })); setSelection(null); setNotice("");
  };
  const changeComponentId = (component: ComponentConfig, nextId: string) => {
    if (!idPattern.test(nextId)) throw new Error(t("invalidId"));
    if (draft.components.some(item => item.id === nextId && item.id !== component.id)) throw new Error(t("duplicateComp"));
    const oldId = component.id;
    setDraft(prev => {
      let scripts = prev.scripts;
      if (scripts) { const json = JSON.stringify(scripts).replaceAll(`"ENT":"${oldId}"`, `"ENT":"${nextId}"`).replaceAll(`"SRC":"${oldId}"`, `"SRC":"${nextId}"`); scripts = JSON.parse(json) as QHomeConfig["scripts"]; }
      return { ...prev, scripts, components: prev.components.map(item => item.id === oldId ? { ...item, id: nextId } : item).map(item => item.type === "led_matrix" && item.props?.source === oldId ? { ...item, props: { ...item.props, source: nextId } } : item) };
    }); setSelection({ kind: "component", id: nextId });
  };

  if (!data.config || !data.meta.models) return <main className="boards-loading">{t("loading")}</main>;
  return <div className="boards-page">
    <header className="page-heading boards-page-heading"><div><p className="eyebrow">QHOME · HARDWARE</p><h1>{t("title")}</h1><p className="page-description">{t("subtitle")}</p></div><button className="primary-button" onClick={() => setDialog("new")}>＋ {t("addBoard")}</button></header>
    {pageError && <div className="boards-error" role="alert"><span>{pageError}</span><button aria-label={t("dismiss")} onClick={() => setPageError(null)}>×</button></div>}
    {notice && !dirty && <div className="boards-notice" role="status">{notice}</div>}
    <section className="found-section"><div className="section-heading"><div><p className="eyebrow">{t("found")}</p><h2>{t("found")}</h2></div><button className="secondary-button" onClick={() => setShowIgnored(value => !value)}>{showIgnored ? t("dismiss") : t("ignoreClear")}</button></div>
      {visibleFound.length ? visibleFound.map(item => <FoundBoard key={item.key} item={item} meta={data} tr={tr} ignored={ignored.includes(item.key)} onAdd={() => setDialog(item)} onIgnore={() => { const next = [...new Set([...ignored, item.key])]; setIgnored(next); localStorage.setItem("qhome.found.ignored", JSON.stringify(next)); }} onRestore={() => { const next = ignored.filter(key => key !== item.key); setIgnored(next); localStorage.setItem("qhome.found.ignored", JSON.stringify(next)); }} />) : <p className="muted-line">{t("noFound")}</p>}
    </section>
    {draft.boards.length === 0 ? <section className="boards-empty"><div className="empty-icon">⌘</div><h2>{t("none")}</h2><p>{t("noBoards")}</p><button className="primary-button" onClick={() => setDialog("new")}>{t("addBoard")}</button></section> : <>
      <div className="board-tabs" role="tablist" aria-label={t("title")}>
        {draft.boards.map(board => { const status = data.snapshot.boards[board.id]; return <button key={board.id} role="tab" aria-selected={board.id === selectedBoard} onClick={() => { setSelectedBoard(board.id); setSelection(null); }}><span className={`board-tab-dot ${status?.online ? "" : "is-offline"}`} />{board.name || board.id}</button>; })}
        <button className="board-tab-add" onClick={() => setDialog("new")}>＋ {t("addBoard")}</button>
      </div>
      {!currentBoard || !model ? <div className="boards-error" role="alert">{t("configMissing")}</div> : <>
        <div className="board-overview"><div className="board-overview-title"><h2>{currentBoard.name || currentBoard.id}</h2><span className="board-model-label">{model.label || currentBoard.model}</span><code>{currentBoard.id}</code></div><div className="board-overview-actions"><StatusBadge online={Boolean(boardState?.online)}>{boardState?.online ? t("online") : boardState?.text || t("offline")}</StatusBadge><button className="secondary-button" onClick={() => setDialog(currentBoard)}>{t("edit")}</button><button className="danger-button" onClick={() => removeBoard(currentBoard)}>{t("remove")}</button></div></div>
        {boardState?.model && boardState.model !== currentBoard.model && data.meta.models[boardState.model] && <div className="boards-warning" role="status">{t("otherBoard")} ({data.meta.models[boardState.model].label})</div>}
        <div className="board-workspace">
          <section className="board-panel" aria-label={model.label}>
            <div className="board-toolbar"><div className="capability-legend"><strong>{t("legend")}:</strong>{[...new Set(model.pins.flatMap(pin => pin.caps))].map(cap => <span key={cap}><i style={{ backgroundColor: capColors[cap] ?? "#899" }} />{capNames[cap] ?? cap}</span>)}</div>{model.board && <div className="segmented-control"><button aria-pressed={view === "drawing"} onClick={() => { setView("drawing"); localStorage.setItem("qhome.boardview", "board"); }}>{t("drawing")}</button><button aria-pressed={view === "list"} onClick={() => { setView("list"); localStorage.setItem("qhome.boardview", "list"); }}>{t("list")}</button></div>}</div>
            {model.board && view === "drawing" ? <BoardDrawing board={currentBoard} model={model} pins={model.pins} components={draft.components} reserved={reserved} states={data.snapshot.states} frames={data.snapshot.matrix ?? {}} selection={selection} capNames={capNames} onPin={pin => selectPin(currentBoard, pin)} /> : <PinList model={model} board={currentBoard} components={draft.components} reserved={reserved} states={data.snapshot.states} frames={data.snapshot.matrix ?? {}} selection={selection} onPin={pin => selectPin(currentBoard, pin)} capNames={capNames} language={language} />}
            <p className="board-touch-hint">{tr ? "Pin seçerek uygun bileşen ekleyin veya mevcut atamayı düzenleyin." : "Select a pin to add a compatible component or edit its current assignment."}</p>
          </section>
          <aside className="board-inspector" aria-label={t("component")}>
            <Inspector selection={selection} board={currentBoard} model={model} draft={draft} meta={data} reserved={reserved} language={language} onSelectComponent={id => setSelection({ kind: "component", id })} onAdd={addComponent} onUpdate={updateComponent} onRename={changeComponentId} onRemove={removeComponent} onClose={() => setSelection(null)} />
          </aside>
        </div>
        <section className="link-help"><h3>{t("wiring")}</h3><p>{t("firmwareNote")}</p><FirmwareInfo board={currentBoard} meta={data} tr={tr} /></section>
      </>}
      <section className="virtual-section"><div className="section-heading"><div><p className="eyebrow">QHOME</p><h2>{t("virtual")}</h2></div><button className="secondary-button" onClick={() => addComponent("virtual_switch", null)}>{t("addVirtual")}</button></div>{virtualComponents.length === 0 ? <p className="muted-line">{t("noVirtual")}</p> : <div className="virtual-chips">{virtualComponents.map(component => <button key={component.id} aria-pressed={selection?.kind === "component" && selection.id === component.id} onClick={() => setSelection({ kind: "component", id: component.id })}><span>VS</span>{component.name || component.id}</button>)}</div>}</section>
    </>}
    <div className="boards-savebar" aria-live="polite">{dirty ? <span>{t("dirty")}</span> : <span />}{dirty && <><button className="secondary-button" onClick={discard} disabled={saving}>{t("discard")}</button><button className="primary-button" onClick={() => void save()} disabled={saving}>{saving ? t("saving") : t("save")}</button></>}</div>
    {dialog !== null && <BoardDialog value={dialog} boards={draft.boards} meta={data} ports={ports} portsError={portsError} portsLoading={portsLoading} language={language} onCancel={() => setDialog(null)} onSubmit={(board, isNew) => {
      const originalId = !isNew && typeof dialog === "object" && "id" in dialog ? dialog.id : undefined;
      const conflict = draft.boards.some(item => item.id === board.id && item.id !== originalId);
      if (!idPattern.test(board.id)) return t("invalidId"); if (conflict) return t("duplicateBoard");
      const link = board.link ?? { type: "" };
      if (link.type === "local" && draft.boards.some(item => item.id !== board.id && item.link?.type === "local")) return t("noLocal");
      const addresses = draft.boards.filter(item => item.id !== board.id && item.link?.type === "i2c").map(item => item.link?.address);
      if (link.type === "i2c" && (!Number.isInteger(Number(link.address)) || Number(link.address) < 8 || Number(link.address) > 119 || addresses.includes(link.address))) return t("badAddress");
      setPageError(null);
      const nextBoards = isNew ? [...draft.boards, board] : draft.boards.map(item => item.id === board.id ? board : item);
      const newlyReserved = reservedPins(board, nextBoards, data.meta.models);
      setDraft(prev => ({ ...prev, boards: nextBoards, components: prev.components.filter(component => !(component.board === board.id && newlyReserved[String(component.pin)])) }));
      setSelectedBoard(board.id); setSelection(null); setDialog(null); setNotice(""); return null;
    }} />}
  </div>;
}

interface FoundProps { item: DiscoveredBoard; meta: ApiContext; tr: boolean; ignored: boolean; onAdd: () => void; onIgnore: () => void; onRestore: () => void; }
function FoundBoard({ item, meta, tr, ignored, onAdd, onIgnore, onRestore }: FoundProps) {
  const model = item.model ? meta.meta.models[item.model] : undefined;
  return <div className="found-board"><span className="found-dot" /><div><strong>{model?.label ?? item.model ?? (tr ? "Bilinmeyen kart" : "Unknown board")}</strong><small>{item.link === "wifi" ? `Wi-Fi · ${item.id}` : `USB · ${item.port}`}{item.proto ? ` · ${item.proto}` : ""}</small></div>{model && <button className="secondary-button" onClick={onAdd}>{tr ? "Yapılandır ve ekle" : "Configure and add"}</button>}{ignored ? <button className="text-button" onClick={onRestore}>{tr ? "Yeniden göster" : "Restore"}</button> : <button className="text-button" onClick={onIgnore}>{tr ? "Yok say" : "Ignore"}</button>}</div>;
}

interface DialogProps { value: BoardConfig | DiscoveredBoard | "new"; boards: BoardConfig[]; meta: ApiContext; ports: SerialPortInfo[]; portsError: boolean; portsLoading: boolean; language: Language; onCancel: () => void; onSubmit: (board: BoardConfig, isNew: boolean) => string | null; }
function BoardDialog({ value, boards, meta, ports, portsError, portsLoading, language, onCancel, onSubmit }: DialogProps) {
  const tr = language === "tr"; const isNew = value === "new" || "key" in value; const isFound = typeof value === "object" && "key" in value;
  const preset = isFound ? value as DiscoveredBoard : null;
  const existing = !isNew ? value as BoardConfig : null;
  const initialModel = existing?.model ?? (preset?.model && meta.meta.models[preset.model] ? preset.model : meta.meta.models.uno ? "uno" : Object.keys(meta.meta.models)[0]);
  const presetName = preset ? (preset.link === "wifi" ? preset.id ?? "" : initialModel ? meta.meta.models[initialModel]?.label ?? "" : "") : "";
  const localLinkAvailable = meta.meta.has_local && !boards.some(board => board.link?.type === "local" && board.id !== existing?.id);
  const [name, setName] = useState(existing?.name ?? presetName); const [id, setId] = useState(existing?.id ?? (preset?.link === "wifi" ? preset.id ?? "" : slug(presetName)));
  const [idTouched, setIdTouched] = useState(Boolean(existing || preset?.link === "wifi")); const [modelId, setModelId] = useState(initialModel);
  const [linkType, setLinkType] = useState<LinkType>((existing?.link?.type as LinkType) ?? preset?.link ?? "usb");
  const [port, setPort] = useState(String(existing?.link?.port ?? preset?.port ?? "auto")); const [baud, setBaud] = useState(Number(existing?.link?.baud ?? 115200));
  const [bus, setBus] = useState(String(existing?.link?.bus ?? "wire")); const [address, setAddress] = useState(Number(existing?.link?.address ?? nextI2cAddress(boards)));
  const [error, setError] = useState(""); const [showHelp, setShowHelp] = useState(false);
  const model = meta.meta.models[modelId];
  const linkTypes = (model?.links ?? []).filter(type => type !== "local" || localLinkAvailable) as LinkType[];
  useEffect(() => { if (!linkTypes.includes(linkType) && linkTypes[0]) setLinkType(linkTypes[0]); }, [modelId]);
  const updateLink = (type: LinkType) => { setLinkType(type); if (type === "i2c") setAddress(nextI2cAddress(boards)); };
  const submit = (event: FormEvent) => {
    event.preventDefault(); const finalName = name.trim(); const finalId = id.trim();
    if (!finalName) { setError(tr ? "Kart adı girin." : "Enter a board name."); return; }
    if (!idPattern.test(finalId)) { setError(tr ? "Kart kimliği küçük harfle başlamalı; yalnızca küçük harf, rakam ve _ kullanın." : "Board ID must start with a lowercase letter and contain only lowercase letters, digits and underscores."); return; }
    const duplicate = boards.some(board => board.id === finalId && board.id !== existing?.id);
    if (duplicate) { setError(tr ? "Bu kart kimliği zaten kullanılıyor." : "This board ID is already in use."); return; }
    if (!model || !linkTypes.includes(linkType)) { setError(tr ? "Kart modeli veya bağlantı türü geçersiz." : "The board model or connection type is invalid."); return; }
    const next: BoardConfig = { id: finalId, name: finalName, model: modelId, link: { type: linkType } };
    if (linkType === "usb") next.link = { type: "usb", port: port || "auto" };
    if (linkType === "uart") next.link = { type: "uart", baud };
    if (linkType === "i2c") next.link = { type: "i2c", bus, address };
    if (linkType === "wifi" && preset) next.id = preset.id ?? finalId;
    const problem = onSubmit(next, isNew); if (problem) { setError(problem); return; } setError("");
  };
  const labels = { name: tr ? "Kart adı" : "Board name", id: tr ? "Kart kimliği" : "Board ID", model: tr ? "Kart modeli" : "Board model", link: tr ? "Bağlantı türü" : "Connection type", port: tr ? "Seri port" : "Serial port", auto: tr ? "Otomatik" : "Automatic", baud: tr ? "Baud hızı" : "Baud rate", bus: tr ? "I²C veri yolu" : "I²C bus", address: tr ? "I²C adresi" : "I²C address", help: tr ? "Firmware / bağlantı yönergesi" : "Firmware / link guidance", sim: tr ? "Simülasyon modu: fiziksel port kullanılmaz." : "Simulation mode: physical ports are not used." };
  return <div className="boards-modal-backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) onCancel(); }}><form className="boards-modal" role="dialog" aria-modal="true" aria-labelledby="board-dialog-title" onSubmit={submit}>
    <h2 id="board-dialog-title">{isNew ? (tr ? "Kart ekle" : "Add board") : (tr ? "Kartı düzenle" : "Edit board")}</h2>{error && <p className="boards-error" role="alert">{error}</p>}
    <label>{labels.name}<input autoFocus required value={name} onChange={event => { const next = event.target.value; setName(next); if (!idTouched && !preset) setId(slug(next)); }} /></label>
    <label>{labels.id}<input required pattern="[a-z][a-z0-9_]{0,31}" disabled={!isNew || preset?.link === "wifi"} value={id} onChange={event => { setIdTouched(true); setId(event.target.value); }} /></label>
    <label>{labels.model}<select disabled={!isNew} value={modelId} onChange={event => { const next = event.target.value; setModelId(next); const supported = meta.meta.models[next]?.links ?? []; if (!supported.includes(linkType)) setLinkType((supported.find(link => link !== "local" || localLinkAvailable) as LinkType) ?? "usb"); }}>{Object.entries(meta.meta.models).map(([key, entry]) => <option key={key} value={key}>{entry.label ?? key}</option>)}</select></label>
    <fieldset><legend>{labels.link}</legend><div className="link-options">{linkTypes.map(type => <button type="button" key={type} aria-pressed={linkType === type} onClick={() => updateLink(type)}>{({ local: tr ? "Ana kart" : "Local", usb: "USB", uart: "UART", i2c: "I²C", wifi: "Wi-Fi" })[type]}</button>)}</div></fieldset>
    {linkType === "usb" && <label>{labels.port}<select value={port} onChange={event => setPort(event.target.value)}><option value="auto">{labels.auto}</option>{ports.map(item => <option key={item.name} value={item.name}>{item.name}{item.busy ? (tr ? " (kullanımda)" : " (busy)") : ""}</option>)}{port !== "auto" && !ports.some(item => item.name === port) && <option value={port}>{port}</option>}</select>{portsLoading && <small className="field-warning">{tr ? "Seri portlar yükleniyor…" : "Loading serial ports…"}</small>}{portsError && <small className="field-warning">{tr ? "Seri port listesi alınamadı; otomatik veya mevcut port seçilebilir." : "Could not list serial ports; automatic or existing ports can still be selected."}</small>}</label>}
    {linkType === "uart" && <label>{labels.baud}<select value={baud} onChange={event => setBaud(Number(event.target.value))}>{[9600, 19200, 38400, 57600, 115200].map(rate => <option key={rate} value={rate}>{rate}</option>)}</select></label>}
    {linkType === "i2c" && <div className="board-form-row"><label>{labels.bus}<select value={bus} onChange={event => setBus(event.target.value)}><option value="wire">Wire</option><option value="qwiic">Qwiic</option></select></label><label>{labels.address}<input type="number" min="8" max="119" value={address} onChange={event => setAddress(Number(event.target.value))} /></label></div>}
    {meta.meta.sim && <p className="field-warning">{labels.sim}</p>}<button type="button" className="text-button help-toggle" onClick={() => setShowHelp(value => !value)}>{labels.help}</button>{showHelp && model && <div className="firmware-snippet"><FirmwareInfo board={{ id, name, model: modelId, link: { type: linkType } }} meta={meta} tr={tr} /></div>}
    <div className="boards-modal-actions"><button type="button" className="secondary-button" onClick={onCancel}>{tr ? "İptal" : "Cancel"}</button><button className="primary-button" type="submit">{isNew ? (tr ? "Ekle" : "Add") : (tr ? "Tamam" : "Done")}</button></div>
  </form></div>;
}
function nextI2cAddress(boards: BoardConfig[]) { let address = 16; const used = new Set(boards.filter(board => board.link?.type === "i2c").map(board => Number(board.link?.address))); while (used.has(address) && address <= 119) address++; return Math.min(address, 119); }

interface CanvasProps { board: BoardConfig; model: BoardModel; pins: ModelPin[]; components: ComponentConfig[]; reserved: Record<string, string>; states: ApiContext["snapshot"]["states"]; frames: Record<string, string>; selection: Selection; capNames: Record<string, string>; onPin: (pin: ModelPin) => void; }
function BoardDrawing({ board, model, pins, components, reserved, states, frames, selection, capNames, onPin }: CanvasProps) {
  const footprint = model.board; if (!footprint) return null;
  const sideNames = new Set((footprint.headers ?? []).map(header => header.side)); const margins = { left: sideNames.has("left") ? 5 : 3.2, right: sideNames.has("right") ? 5 : 1, top: sideNames.has("top") ? 4.8 : 1, bottom: sideNames.has("bottom") ? 4.8 : 1 };
  const totalW = margins.left + footprint.w + margins.right, totalH = margins.top + footprint.h + margins.bottom;
  const style = { "--board-w": footprint.w, "--board-h": footprint.h, "--board-total-w": totalW, "--board-total-h": totalH, "--board-left": margins.left, "--board-top": margins.top } as CSSProperties;
  const componentAt = (pin: string | number) => components.find(component => component.board === board.id && String(component.pin) === String(pin));
  const getPin = (id: string | number) => pins.find(pin => String(pin.id) === String(id));
  const pinButton = (pin: ModelPin, placement: Record<string, number | string>, asPart = false) => {
    const component = componentAt(pin.id); const reservedReason = reserved[String(pin.id)]; const selected = selection?.kind === "pin" ? selection.boardId === board.id && String(selection.pin) === String(pin.id) : selection?.kind === "component" && selection.id === component?.id;
    const warn = pin.notes?.some(note => warningNotes.has(note)); const classes = ["pin-target", component ? "pin-used" : "", reservedReason ? "pin-reserved" : "", warn ? "pin-warning" : "", asPart ? "pin-part" : ""].filter(Boolean).join(" ");
    const description = `${pin.label}${pin.alt ? ` (${pin.alt})` : ""}${reservedReason ? ` · ${reservedReason}` : component ? ` · ${component.name}` : ` · ${pin.caps.join(", ")}`}`;
    const state = component ? states[component.id] : undefined; const value = component?.type === "rgb_led" ? String(state?.v ?? "") : component?.type === "led_matrix" ? "MX" : "";
    const variableStyle = { "--x": placement.x, "--y": placement.y, "--flag": placement.flag ?? 0, "--part-w": placement.partWidth ?? 1.4, "--part-h": placement.partHeight ?? 1.4 } as CSSProperties;
    const caps = pin.caps.map(cap => <i key={cap} title={capNames[cap] ?? cap} style={{ backgroundColor: capColors[cap] ?? "#899" }} />);
    const matrixFrame = component?.type === "led_matrix" ? frames[component.id] ?? "" : "";
    return <button key={`pin-${String(pin.id)}`} type="button" className={`${classes} ${String(placement.className ?? "")}`} style={variableStyle} aria-label={`${pin.label}${component ? `, ${component.name}` : ""}`} aria-pressed={selected} title={description} onClick={() => onPin(pin)}>
      <span className={`pin-socket ${component?.type === "rgb_led" ? "socket-rgb" : ""} ${component?.type === "led_matrix" ? "socket-matrix-grid" : ""}`} style={component?.type === "rgb_led" ? { backgroundColor: colorByValue[String(state?.v)] ?? "" } : undefined}>{component?.type === "led_matrix" ? Array.from({ length: 104 }, (_, index) => <i key={index} className={matrixFrame[index] && matrixFrame[index] !== "0" ? "pixel-active" : ""} />) : value === "MX" ? <span className="socket-matrix">▦</span> : null}</span><span className="pin-silk">{pin.label}</span>
      {!component && !reservedReason && <span className="pin-cap-marks">{caps}</span>}{component && <span className="pin-flag"><b>{component.name}</b>{state?.txt && <small>{state.txt}</small>}</span>}{reservedReason && <span className="pin-flag">{reservedReason}</span>}
    </button>;
  };
  const headerNodes: ReactNode[] = [];
  for (const [headerIndex, header] of (footprint.headers ?? []).entries()) {
    const cols = header.cols || header.pins.length || 1; const rows = Math.ceil(header.pins.length / cols); const side = header.side || "inner";
    headerNodes.push(<div key={`h-${headerIndex}`} className="drawing-header" style={{ "--x": header.x - .5, "--y": header.y - .5, "--w": cols, "--h": rows } as CSSProperties} />);
    if (header.name && !["TOP", "BOTTOM", "LEFT", "RIGHT"].includes(header.name) && side !== "left" && side !== "right") headerNodes.push(<div key={`hn-${headerIndex}`} className="drawing-header-name" style={{ "--x": header.x - .5, "--y": side === "bottom" ? header.y - 2.35 : side === "top" ? header.y + rows + .85 : header.y - .55, "--w": cols } as CSSProperties}>{header.name}</div>);
    header.pins.forEach((entry, index) => {
      const x = header.x + index % cols, y = header.y + Math.floor(index / cols);
      if (typeof entry === "object") {
        const pad = String(entry.pad ?? ""); const twin = entry.same == null ? undefined : getPin(entry.same); const twinComponent = twin ? componentAt(twin.id) : undefined;
        headerNodes.push(<div key={`pad-${headerIndex}-${index}`} className={`drawing-pad ${/^gnd$/i.test(pad) ? "pad-ground" : /^(3V3|5V|VIN|VBATT|VBAT|VCC|VBUS)$/i.test(pad) ? "pad-power" : ""}`} style={{ "--x": x, "--y": y } as CSSProperties} title={`${pad}${twin ? ` · ${twin.label}` : ""}`}><span className="pin-socket" />{pad}{twinComponent && <small>{twinComponent.name}</small>}</div>); return;
      }
      const pin = getPin(entry); if (!pin) return;
      let flag = 0; let pos = "fo-n";
      const row = Math.floor(index / cols); const col = index % cols;
      if (side === "top" && row === 0) { pos = "fo-t"; flag = y; }
      if (side === "bottom" && row === rows - 1) { pos = "fo-b"; flag = footprint.h - y; }
      if (side === "right" && col === cols - 1) { pos = "fo-r"; flag = footprint.w - x; }
      if (side === "left" && col === 0) { pos = "fo-l"; flag = x; }
      const labels: string[] = [];
      if ((side === "top" && row === rows - 1) || (side === "bottom" && row === 0)) labels.push("silk-vertical");
      if (col === 0) labels.push("silk-left");
      if (col === cols - 1) labels.push("silk-right");
      headerNodes.push(pinButton(pin, { x, y, flag, className: `${pos} ${labels.join(" ")}` }));
    });
  }
  const parts = (footprint.parts ?? []).map((part: BoardPart, index) => {
    const x = part.x, y = part.y, w = part.w ?? 1, h = part.h ?? 1;
    if (part.pin != null) { const pin = getPin(part.pin); if (pin) return <Fragment key={`part-${index}`}>{pinButton(pin, { x: x + w / 2, y: y + h / 2, partWidth: w, partHeight: h, className: `fo-part ${part.type === "matrix" ? "matrix-part" : ""}` }, true)}</Fragment>; }
    return <div key={`part-${index}`} className={`drawing-part part-${part.type}`} style={{ "--x": x, "--y": y, "--w": w, "--h": h, "--cols": part.cols ?? 13, "--rows": part.rows ?? 8 } as CSSProperties} aria-hidden="true">{part.type === "matrix" ? Array.from({ length: (part.cols ?? 13) * (part.rows ?? 8) }, (_, i) => <i key={i} />) : part.label}</div>;
  });
  return <div className="board-canvas-wrap"><div className={`board-canvas model-${board.model}`} style={style} role="group" aria-label={model.label}><div className="board-outline">{parts}{headerNodes}</div></div></div>;
}

interface PinListProps { model: BoardModel; board: BoardConfig; components: ComponentConfig[]; reserved: Record<string, string>; states: ApiContext["snapshot"]["states"]; frames: Record<string, string>; selection: Selection; capNames: Record<string, string>; language: Language; onPin: (pin: ModelPin) => void; }
function PinList({ model, board, components, reserved, states, frames, selection, capNames, language, onPin }: PinListProps) {
  const pins = model.pins; const groups: Array<[string, Array<string | number>]> = model.layout?.length ? model.layout : [["pins", pins.map(pin => pin.id)]];
  return <div className="pin-list-view">{groups.map(([name, ids]) => <section key={name}><h3>{pinGroupName(name, language === "tr")}</h3><div className="pin-list-grid">{ids.map(id => { const pin = pins.find(item => String(item.id) === String(id)); if (!pin) return null; const component = components.find(item => item.board === board.id && String(item.pin) === String(pin.id)); const isReserved = Boolean(reserved[String(pin.id)]); const state = component ? states[component.id] : undefined; const frame = component?.type === "led_matrix" ? frames[component.id] ?? "" : ""; const selected = selection?.kind === "pin" && selection.boardId === board.id && String(selection.pin) === String(pin.id) || selection?.kind === "component" && selection.id === component?.id; return <button type="button" key={String(pin.id)} className={`pin-list-item ${component ? "pin-list-used" : ""} ${isReserved ? "pin-list-reserved" : ""}`} aria-pressed={selected} title={pin.notes?.map(note => pinNote(note, language === "tr")).join(", ")} onClick={() => onPin(pin)}><strong>{pin.label}</strong>{component ? <><span className={`pin-list-device ${component.type === "rgb_led" ? "pin-list-rgb" : ""} ${component.type === "led_matrix" ? "pin-list-matrix" : ""}`} style={component.type === "rgb_led" ? { backgroundColor: colorByValue[String(state?.v)] ?? "#66746e" } : undefined}>{component.type === "led_matrix" ? Array.from({ length: 104 }, (_, index) => <i key={index} className={frame[index] && frame[index] !== "0" ? "pixel-active" : ""} />) : component.type === "rgb_led" ? null : componentTag(component.type)}</span><small>{component.name || component.id}</small>{!(["rgb_led", "led_matrix"] as string[]).includes(component.type) && state?.txt && <small className="pin-list-value">{state.txt}</small>}</> : <>{!isReserved && <span className="pin-list-caps">{pin.caps.map(cap => <i key={cap} style={{ backgroundColor: capColors[cap] ?? "#899" }} title={capNames[cap] ?? cap} />)}</span>}<small>{reserved[String(pin.id)] ? (language === "tr" ? "Bağlantı için ayrılmış" : "Reserved for link") : pin.notes?.[0] ? pinNote(pin.notes[0], language === "tr") : ""}</small></>}</button>; })}</div></section>)}</div>;
}

interface InspectorProps { selection: Selection; board: BoardConfig; model: BoardModel; draft: QHomeConfig; meta: ApiContext; reserved: Record<string, string>; language: Language; onSelectComponent: (id: string) => void; onAdd: (type: ComponentConfig["type"], boardId: string | null, pin?: string | number) => void; onUpdate: (id: string, transform: (component: ComponentConfig) => ComponentConfig) => void; onRename: (component: ComponentConfig, id: string) => void; onRemove: (component: ComponentConfig) => void; onClose: () => void; }
function Inspector({ selection, board, model, draft, meta, reserved, language, onSelectComponent, onAdd, onUpdate, onRename, onRemove, onClose }: InspectorProps) {
  const tr = language === "tr"; const t = (en: string, trText: string) => tr ? trText : en; const [error, setError] = useState("");
  const component = selection?.kind === "component" ? draft.components.find(item => item.id === selection.id) : undefined;
  const selectedPin = selection?.kind === "pin" && selection.boardId === board.id ? model.pins.find(pin => String(pin.id) === String(selection.pin)) : component?.board === board.id ? model.pins.find(pin => String(pin.id) === String(component.pin)) : undefined;
  if (component) {
    const definition = meta.meta.types[component.type]; const assignedBoard = draft.boards.find(item => item.id === component.board); const compModel = assignedBoard ? meta.meta.models[assignedBoard.model] : undefined;
    const props = { ...defaultProps(definition.props), ...component.props };
    const pinOptions = component.board && compModel ? compModel.pins.filter(pin => pin.caps.includes(definition.cap ?? "") && !reservedPins(assignedBoard!, draft.boards, meta.meta.models)[String(pin.id)] && !draft.components.some(other => other.id !== component.id && other.board === component.board && String(other.pin) === String(pin.id))) : [];
    const setProp = (key: string, value: unknown) => onUpdate(component.id, current => ({ ...current, props: { ...(current.props ?? {}), [key]: value } }));
    const propertyFields = definition.props.filter(def => { if (!def.show) return true; const [key, expected] = String(def.show).split("="); return expected.split("|").includes(String(props[key] ?? "")); }).map(def => <PropertyField key={def.key} definition={def} value={props[def.key] ?? def.default} component={component} components={draft.components} language={language} onChange={value => setProp(def.key, value)} />);
    return <div className="inspector-content"><div className="inspector-heading"><span className="device-type">{definition.tag}</span><h3>{componentTypeName(component.type, tr)}</h3><button className="icon-button" aria-label={t("Close", "Kapat")} onClick={onClose}>×</button></div>
      <label>{t("Component name", "Bileşen adı")}<input value={component.name} onChange={event => onUpdate(component.id, current => ({ ...current, name: event.target.value }))} /></label>
      <label>{t("Component ID", "Bileşen kimliği")}<input key={component.id} defaultValue={component.id} onBlur={event => { const next = event.target.value.trim(); if (next !== component.id) try { onRename(component, next); setError(""); } catch (cause) { setError(cause instanceof Error ? cause.message : "Invalid ID"); event.target.value = component.id; } }} /></label>
      {error && <p className="field-error" role="alert">{error}</p>}
      {component.board && definition.cap && <label>{t("Assigned pin", "Atanan pin")}<select value={String(component.pin ?? "")} onChange={event => { const id = model.pins.find(pin => String(pin.id) === event.target.value)?.id; if (id !== undefined) onUpdate(component.id, current => ({ ...current, pin: id })); }}><option value={String(component.pin)}>{compModel?.pins.find(pin => String(pin.id) === String(component.pin))?.label ?? component.pin}</option>{pinOptions.map(pin => <option key={String(pin.id)} value={String(pin.id)}>{pin.label} · {pin.caps.join(", ")}</option>)}</select></label>}
      <h4>{t("Component settings", "Bileşen ayarları")}</h4>{propertyFields.length ? propertyFields : <p className="muted-line">{t("No extra settings.", "Ek ayar yok.")}</p>}
      {selectedPin && <PinNotes pin={selectedPin} model={compModel ?? model} tr={tr} />}
      <div className="inspector-actions"><button className="danger-button" onClick={() => onRemove(component)}>{t("Remove component", "Bileşeni sil")}</button><button className="secondary-button" onClick={onClose}>{t("Close", "Kapat")}</button></div>
    </div>;
  }
  if (!selectedPin) return <div className="inspector-empty"><span>⌖</span><h3>{t("Select a pin", "Bir pin seçin")}</h3><p>{t("Select a pin to see compatible components, or select a configured component to edit it.", "Uyumlu bileşenleri görmek için pin seçin veya düzenlemek için yapılandırılmış bir bileşeni seçin.")}</p></div>;
  const occupied = draft.components.find(item => item.board === board.id && String(item.pin) === String(selectedPin.id)); const reservation = reserved[String(selectedPin.id)];
  const options = Object.entries(meta.meta.types).filter(([, definition]) => definition.cap && selectedPin.caps.includes(definition.cap)) as Array<[ComponentConfig["type"], ApiContext["meta"]["types"][ComponentConfig["type"]]]>;
  return <div className="inspector-content"><div className="inspector-heading"><span className="pin-inspector-icon">{selectedPin.label}</span><h3>{reservation ? t("Reserved pin", "Ayrılmış pin") : occupied ? t("Configured pin", "Yapılandırılmış pin") : t("Available pin", "Kullanılabilir pin")}</h3></div><p className="pin-inspector-subtitle">{selectedPin.alt ?? (tr ? "Kart pini" : "Board pin")}</p>
    {reservation ? <p className="boards-warning">{reservation === "serial" ? t("Reserved for serial link", "Seri bağlantı için ayrılmış") : reservation === "i2c" ? t("Reserved for I²C link", "I²C bağlantısı için ayrılmış") : reservation === "hostUart" ? t("Used by a hosted UART connection", "Ana kartta ayrılmış UART bağlantısı") : t("Used by a hosted I²C connection", "Ana kartta ayrılmış I²C bağlantısı")}</p> : occupied ? <button className="occupied-component" onClick={() => onSelectComponent(occupied.id)}><span>{meta.meta.types[occupied.type].tag}</span><b>{occupied.name || occupied.id}</b><small>{occupied.id}</small></button> : options.length ? <><h4>{t("Add a compatible component", "Uyumlu bileşen ekle")}</h4><div className="component-choice-list">{options.map(([type, definition]) => <button key={type} onClick={() => onAdd(type, board.id, selectedPin.id)}><span>{definition.tag}</span><b>{componentTypeName(type, tr)}</b><small>{definition.kind} · {definition.cap}</small></button>)}</div></> : <p className="muted-line">{t("No component type is compatible with this pin.", "Bu pinle uyumlu bileşen türü yok.")}</p>}
    <PinNotes pin={selectedPin} model={model} tr={tr} />
  </div>;
}

interface FieldProps { definition: DevicePropertyDefinition; value: unknown; component: ComponentConfig; components: ComponentConfig[]; language: Language; onChange: (value: unknown) => void; }
function PropertyField({ definition, value, component, components, language, onChange }: FieldProps) {
  const tr = language === "tr"; const key = definition.key; const type = String(definition.type ?? "text"); const label = settingName(key, tr);
  if (type === "bool") return <label className="check-field"><input type="checkbox" checked={Boolean(value)} onChange={event => onChange(event.target.checked)} />{label}</label>;
  if (type === "select") { const choices = Array.isArray(definition.options) ? definition.options as unknown[] : []; return <label>{label}<select value={String(value ?? "")} onChange={event => onChange(event.target.value)}>{choices.map(option => <option key={String(option)} value={String(option)}>{String(option) || (tr ? "Yok" : "None")}</option>)}</select></label>; }
  if (type === "device") { const kinds = Array.isArray(definition.kinds) ? definition.kinds as string[] : []; const available = components.filter(item => item.id !== component.id && kinds.includes(item.type)); return <label>{label}<select value={String(value ?? "")} onChange={event => onChange(event.target.value)}><option value="">{available.length ? (tr ? "Cihaz seçin" : "Choose device") : (tr ? "Uygun cihaz yok" : "No compatible device")}</option>{available.map(item => <option key={item.id} value={item.id}>{item.name || item.id}</option>)}{value != null && String(value) !== "" && !available.some(item => item.id === String(value)) && <option value={String(value)}>{tr ? `Eksik: ${String(value)}` : `Missing: ${String(value)}`}</option>}</select></label>; }
  const numeric = type === "number"; return <label>{label}<input type={numeric ? "number" : "text"} value={String(value ?? "")} min={numeric && typeof definition.min === "number" ? definition.min : undefined} max={numeric && typeof definition.max === "number" ? definition.max : undefined} step={numeric && typeof definition.step === "number" ? definition.step : undefined} onChange={event => onChange(numeric ? (event.target.value === "" ? definition.default : Number(event.target.value)) : event.target.value)} /></label>;
}
function PinNotes({ pin, model, tr }: { pin: ModelPin; model: BoardModel; tr: boolean }) { const notes = pin.notes ?? []; return <div className="pin-notes"><h4>{tr ? "Elektriksel notlar" : "Electrical notes"}</h4><ul>{notes.map(note => <li key={note} className={warningNotes.has(note) ? "note-warning" : ""}>{pinNote(note, tr)}</li>)}<li>{tr ? `Lojik seviyesi: ${model.logic ?? "?"} V` : `Logic level: ${model.logic ?? "?"} V`}</li></ul></div>; }

function FirmwareInfo({ board, meta, tr }: { board: BoardConfig; meta: ApiContext; tr: boolean }) {
  const link = board.link ?? { type: "usb" }; const localHost = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1" ? (tr ? "ana bilgisayar adresini kullanın" : "use the host computer's LAN address") : window.location.hostname;
  const mqttPort = Number(meta.config.mqtt?.mode === "external" ? meta.config.mqtt.ext_port : meta.config.mqtt?.port ?? 1883);
  const snippet = board.model === "unoq" ? `Node name: ${board.id}\nMaster address: ${localHost}\nPort: ${mqttPort}` : ({ usb: `#define QL_LINK  QL_USB\n#define QL_BAUD  ${Number(link.baud ?? 115200)}`, uart: `#define QL_LINK  QL_UART\n#define QL_BAUD  ${Number(link.baud ?? 115200)}`, i2c: `#define QL_LINK  QL_I2C\n#define QL_I2C_ADDRESS  0x${Number(link.address ?? 16).toString(16).toUpperCase()}`, wifi: `#define QL_LINK  QL_WIFI\n#define QL_BOARD_ID     "${board.id}"\n#define QL_MASTER_HOST  "${localHost}"\n#define QL_MASTER_PORT  ${mqttPort}\n#define QL_WIFI_SSID    "..."\n#define QL_WIFI_PASS    "..."` } as Record<string, string>)[String(link.type)] ?? "";
  const model = meta.meta.models[board.model]; const serial = (model?.uart_pins ?? model?.serial_pins ?? []).map(pinId => model?.pins.find(pin => String(pin.id) === String(pinId))?.label).filter(Boolean);
  const wireText = link.type === "uart" ? (tr ? `Ana kart D1 (TX) → karşı kart RX, D0 (RX) → TX, GND → GND.${serial.length >= 2 ? ` Bu kartta RX ${serial[0]}, TX ${serial[1]}.` : ""} ${model?.logic === 3.3 ? "Bu kart 3,3 V lojik kullanır." : "5 V TX hattında seviye dönüştürücü kullanın."} RS-485 veya HC-05/HC-12 modülleri de kullanılabilir.` : `Master D1 (TX) → board RX, D0 (RX) → TX, GND → GND.${serial.length >= 2 ? ` On this board RX is ${serial[0]}, TX is ${serial[1]}.` : ""} ${model?.logic === 3.3 ? "This board uses 3.3 V logic." : "Use a level shifter for a 5 V TX line."} RS-485 or HC-05/HC-12 modules can also be used.`) : link.type === "i2c" ? (tr ? "SDA → SDA, SCL → SCL, GND → GND; pull-up dirençleri 3,3 V'a bağlayın. 5 V kartlarda seviye dönüştürücü kullanın ve kabloları kısa tutun." : "SDA → SDA, SCL → SCL, GND → GND; connect pull-ups to 3.3 V. Use a level shifter for 5 V boards and keep cables short.") : link.type === "wifi" ? (tr ? "UNO R4 WiFi, ESP32, ESP32-C3 veya ESP8266 bu ana kartın MQTT sunucusuna bağlanır; iki cihaz aynı ağda erişilebilir olmalıdır." : "UNO R4 WiFi, ESP32, ESP32-C3 or ESP8266 connects to this master's MQTT broker; both devices must be reachable on the same network.") : link.type === "usb" ? (tr ? "Kartı USB kablosuyla UNO Q'ya takın. App Lab kartı bulamazsa UNO Q üzerinde tools/qhome_usb_helper.py aracını bir kez çalıştırın." : "Connect the board to the UNO Q over USB. If App Lab does not find it, run tools/qhome_usb_helper.py once on the UNO Q.") : (tr ? "Yerel bağlantı bu ana UNO Q üzerinde çalışır." : "Local link runs on this host UNO Q.");
  return <div className="firmware-info"><div className="firmware-link-summary"><strong>{tr ? "Bağlantı" : "Link"}:</strong> {link.type === "i2c" ? `I²C · 0x${Number(link.address ?? 16).toString(16).toUpperCase()} · ${link.bus ?? "wire"}` : link.type === "uart" ? `UART · ${link.baud ?? 115200}` : link.type === "usb" ? `USB · ${link.port === "auto" ? (tr ? "Otomatik" : "Auto") : link.port ?? "Auto"}` : link.type}</div>{link.type !== "local" && <><p>{board.model === "unoq" ? (tr ? "UNO Q düğüm bilgileri:" : "UNO Q node values:") : (tr ? "Arduino IDE'de satellite/qhome_satellite klasörünü açın, aşağıdaki satırları config.h içine koyup firmware'i yükleyin:" : "Open satellite/qhome_satellite in Arduino IDE, put these lines into config.h and upload the firmware:")}</p><pre>{snippet}</pre></>}<div className="wire-note">{wireText}</div></div>;
}
