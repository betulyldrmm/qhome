import { Fragment, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../services/api";
import type { ApiContext } from "../types/api";
import type { Language } from "../i18n";

type Localized = string | Partial<Record<Language, string>>;
interface HelpBlock { t: string; id?: string; text?: Localized; items?: Localized[]; head?: Localized[]; rows?: Localized[][]; warn?: boolean; name?: string; }
interface HelpPageData { id: string; title: Localized; roles?: string[]; blocks?: HelpBlock[]; }
interface HelpHint { text: Localized; more?: string; }
interface HelpDoc { pages?: HelpPageData[]; hints?: Record<string, HelpHint>; }
declare global { interface Window { QHELP?: HelpDoc; } }
let helpLoaded: Promise<HelpDoc> | undefined;

function loadHelp(): Promise<HelpDoc> {
  if (window.QHELP) return Promise.resolve(window.QHELP);
  if (!helpLoaded) helpLoaded = api.getHelp().then(source => {
    const marker = /^window\.QHELP\s*=\s*/m.exec(source);
    if (!marker) throw new Error("Help content is empty.");
    const raw = source.slice(marker.index + marker[0].length).trim().replace(/;\s*$/, "");
    const document = JSON.parse(raw) as HelpDoc;
    window.QHELP = document;
    return document;
  }).catch(error => { helpLoaded = undefined; throw error; });
  return helpLoaded;
}
function local(value: Localized | undefined, language: Language): string {
  if (typeof value === "string") return value;
  return value?.[language] ?? value?.en ?? "";
}

const words = {
  en: { title: "Help", subtitle: "Guides for setup, device connections, automations and troubleshooting.", search: "Search help", pages: "Help pages", onPage: "On this page", more: "Read more", noMatch: "No matching help sections.", loading: "Loading help…", loadError: "Help content could not be loaded.", tryAgain: "Try again", empty: "No help pages are available for this controller role.", board: "Board", logic: "Logic", digital: "Digital", pwm: "PWM", adc: "ADC", dac: "DAC", count: "Count", extras: "Extras", yes: "yes", tag: "Tag", type: "Device type", purpose: "Purpose", icon: "Icon", name: "Name", code: "Code", animation: "Animation", connected: "Connection", boardType: "Board model", matrix: "LED matrix", rgb: "RGB LED", voltage: "V", genericPurpose: "Configured I/O device" },
  tr: { title: "Yardım", subtitle: "Kurulum, cihaz bağlantıları, otomasyonlar ve sorun giderme kılavuzları.", search: "Yardımda ara", pages: "Yardım sayfaları", onPage: "Bu sayfada", more: "Yardımda devamı", noMatch: "Eşleşen yardım bölümü yok.", loading: "Yardım yükleniyor…", loadError: "Yardım içeriği yüklenemedi.", tryAgain: "Yeniden dene", empty: "Bu denetleyici rolü için yardım sayfası yok.", board: "Kart", logic: "Lojik", digital: "Dijital", pwm: "PWM", adc: "ADC", dac: "DAC", count: "Sayaç", extras: "Ekler", yes: "var", tag: "Etiket", type: "Cihaz türü", purpose: "Kullanım", icon: "İkon", name: "Ad", code: "Kod", animation: "Animasyon", connected: "Bağlantı", boardType: "Kart modeli", matrix: "LED matris", rgb: "RGB LED", voltage: "V", genericPurpose: "Yapılandırılmış G/Ç cihazı" },
} as const;

interface Props { data: ApiContext; language: Language; }
export function HelpPage({ data, language }: Props) {
  const tr = language === "tr", t = words[language];
  const [doc, setDoc] = useState<HelpDoc | null>(null), [error, setError] = useState(""), [search, setSearch] = useState("");
  const [selected, setSelected] = useState(""), [anchor, setAnchor] = useState("");
  const role = data.meta.role;
  const pages = useMemo(() => (doc?.pages ?? []).filter(page => !page.roles || page.roles.includes(role)), [doc, role]);
  useEffect(() => { let alive = true; void loadHelp().then(value => { if (alive) { setDoc(value); setSelected(current => current || (value.pages ?? []).find(page => !page.roles || page.roles.includes(role))?.id || ""); } }).catch(cause => { if (alive) setError(cause instanceof Error ? cause.message : t.loadError); }); return () => { alive = false; }; }, [role, t.loadError]);
  const fill = (value: string) => {
    const mqtt = data.config.mqtt ?? {};
    const vars: Record<string, unknown> = { url: location.origin, host: data.config.device.master_host || location.hostname, node: data.config.device.node, web_port: data.meta.web_port || location.port || 7000, mqtt_port: mqtt.mode === "external" ? mqtt.ext_port : mqtt.port || 1883, link_port: data.meta.link_port, version: data.meta.version };
    return value.replace(/\{\{(\w+)\}\}/g, (all, key: string) => vars[key] == null ? all : String(vars[key]));
  };
  const selectedPage = pages.find(page => page.id === selected) ?? pages[0];
  const localized = (value: Localized | undefined) => fill(local(value, language));
  const matches = (page: HelpPageData, query: string) => {
    const sections: Array<{ id: string; title: string; body: string }> = [];
    let current = { id: "", title: local(page.title, language), body: local(page.title, language) };
    for (const block of page.blocks ?? []) {
      if (block.t === "h") { sections.push(current); current = { id: block.id ?? "", title: localized(block.text), body: "" }; }
      current.body += " " + [block.text, ...(block.items ?? []), ...(block.head ?? []), ...(block.rows ?? []).flat()].map(localized).join(" ");
    }
    sections.push(current);
    const found = sections.filter(section => `${section.title} ${section.body}`.toLocaleLowerCase(tr ? "tr-TR" : "en-US").includes(query));
    return found.length ? found.filter(section => section.id).slice(0, 4) : null;
  };
  const query = search.trim().toLocaleLowerCase(tr ? "tr-TR" : "en-US");
  const matchesByPage = new Map(pages.map(page => [page.id, query ? matches(page, query) : []]));
  const visiblePages = query ? pages.filter(page => matchesByPage.get(page.id) !== null) : pages;
  useEffect(() => {
    if (!selectedPage || !anchor) return;
    const frame = requestAnimationFrame(() => document.getElementById(`help-${selectedPage.id}-${anchor}`)?.scrollIntoView({ block: "start", behavior: "smooth" }));
    return () => cancelAnimationFrame(frame);
  }, [anchor, selectedPage]);
  const open = (pageId: string, section = "") => { setSelected(pageId); setAnchor(section); };
  const headingId = (pageId: string, blockId: string) => `help-${pageId}-${blockId}`;

  function rich(value: Localized | undefined, pageId: string, keyPrefix: string): ReactNode[] {
    const raw = localized(value), out: ReactNode[] = [], pattern = /\*\*([^*]+)\*\*|`([^`]+)`|\[([^\]]+)\]\(([^)\s]+)\)/g;
    keyPrefix = `${pageId}-${keyPrefix}`;
    let cursor = 0, match: RegExpExecArray | null, key = 0;
    while ((match = pattern.exec(raw))) {
      if (match.index > cursor) out.push(raw.slice(cursor, match.index));
      if (match[1] !== undefined) out.push(<strong key={`${keyPrefix}-${key++}`}>{match[1]}</strong>);
      else if (match[2] !== undefined) out.push(<code key={`${keyPrefix}-${key++}`}>{match[2]}</code>);
      else {
        const [destPage, destAnchor] = match[4].startsWith("#") ? match[4].slice(1).split(/[\/#]/) : ["", ""];
        if (/^https?:\/\//.test(match[4])) out.push(<a key={`${keyPrefix}-${key++}`} href={match[4]} target="_blank" rel="noopener noreferrer">{match[3]}</a>);
        else if (destPage && pages.some(page => page.id === destPage)) out.push(<a key={`${keyPrefix}-${key++}`} href={`#${destPage}${destAnchor ? `/${destAnchor}` : ""}`} onClick={event => { event.preventDefault(); open(destPage, destAnchor); }}>{match[3]}</a>);
        else out.push(match[3]);
      }
      cursor = pattern.lastIndex;
    }
    if (cursor < raw.length) out.push(raw.slice(cursor));
    return out;
  }
  function table(head: ReactNode[], rows: ReactNode[][], key: string) {
    return <div className="help-table-wrap" key={key}><table><thead><tr>{head.map((cell, i) => <th key={i}>{cell}</th>)}</tr></thead><tbody>{rows.map((row, i) => <tr key={i}>{row.map((cell, j) => <td key={j}>{cell}</td>)}</tr>)}</tbody></table></div>;
  }
  function generated(name: string, key: string): ReactNode {
    const models = Object.entries(data.meta.models ?? {}), matrix = data.meta.matrix ?? {};
    const capCount = (model: (typeof data.meta.models)[string], cap: string) => model.pins.filter(pin => pin.caps.includes(cap)).length || "";
    if (name === "boards") return table([t.board, t.logic, t.digital, t.pwm, t.adc, t.dac, t.count, t.extras], models.map(([id, model]) => [model.label ?? id, `${model.logic ?? "?"} ${t.voltage}`, model.pins.filter(pin => pin.caps.includes("din") || pin.caps.includes("dout")).length, capCount(model, "pwm"), capCount(model, "adc"), capCount(model, "dac"), capCount(model, "cnt"), [capCount(model, "matrix") ? t.matrix : "", capCount(model, "rgb") ? t.rgb : ""].filter(Boolean).join(", ")]), key);
    if (name === "links") { const kinds = ["local", "usb", "uart", "i2c", "wifi"], labels: Record<string, string> = { local: tr ? "Yerel" : "Built in", usb: "USB", uart: "UART", i2c: "I²C", wifi: "Wi-Fi (MQTT)" }; const supported = kinds.filter(kind => models.some(([, model]) => model.links.includes(kind))); return table([t.boardType, ...supported.map(kind => labels[kind])], models.map(([id, model]) => [model.label ?? id, ...supported.map(kind => model.links.includes(kind) ? t.yes : "")]), key); }
    if (name === "types") return table([t.tag, t.type, t.purpose], Object.entries(data.meta.types).map(([id, type]) => [type.tag, tr ? ({ binary_input: "Dijital giriş", analog_sensor: "Analog sensör", pulse_counter: "Darbe sayacı", switch_output: "Dijital çıkış", pwm_output: "PWM çıkışı", dac_output: "Analog çıkış", rgb_led: "RGB LED", led_matrix: "LED matris", virtual_switch: "Sanal anahtar" } as Record<string, string>)[id] ?? id : id.replace(/_/g, " "), type.kind || t.genericPurpose]), key);
    if (name === "icons") return table([t.icon, t.name, t.code], Object.entries(matrix.icons ?? {}).map(([id, frame]) => [<span className="help-icon-grid" role="img" aria-label={id}>{String(frame).split("").slice(0, 104).map((pixel, index) => <i className={pixel !== "0" ? "pixel-on" : ""} key={index} />)}</span>, tr ? ({ smile: "Gülümseme", heart: "Kalp", check: "Onay" } as Record<string, string>)[id] ?? id : id, <code>{id}</code>]), key);
    if (name === "anims") return table([t.animation, t.code], (matrix.anims ?? []).map(id => [id, <code>{id}</code>]), key);
    return null;
  }
  function renderBlock(block: HelpBlock, pageId: string, index: number): ReactNode {
    const key = `${pageId}-${index}`;
    if (block.t === "h") return <h3 id={headingId(pageId, block.id ?? String(index))} key={key}>{rich(block.text, pageId, key)}</h3>;
    if (block.t === "p") return <p key={key}>{rich(block.text, pageId, key)}</p>;
    if (block.t === "ul" || block.t === "ol") { const List = block.t; return <List key={key}>{(block.items ?? []).map((item, i) => <li key={i}>{rich(item, pageId, `${key}-${i}`)}</li>)}</List>; }
    if (block.t === "code") return <pre key={key}>{localized(block.text)}</pre>;
    if (block.t === "note") return <aside className={`help-note ${block.warn ? "help-note-warning" : ""}`} key={key}>{rich(block.text, pageId, key)}</aside>;
    if (block.t === "table") return table((block.head ?? []).map((item, i) => <Fragment key={i}>{rich(item, pageId, `${key}-h-${i}`)}</Fragment>), (block.rows ?? []).map((row, i) => row.map((item, j) => <Fragment key={j}>{rich(item, pageId, `${key}-${i}-${j}`)}</Fragment>)), key);
    if (block.t === "gen") return generated(block.name ?? "", key);
    return null;
  }

  if (error) return <section className="help-page"><header className="page-heading"><div><p className="eyebrow">QHOME · DOCUMENTATION</p><h1>{t.title}</h1><p className="page-description">{t.subtitle}</p></div></header><div className="boards-error" role="alert"><span>{error}</span><button onClick={() => { setError(""); helpLoaded = undefined; void loadHelp().then(setDoc).catch(cause => setError(cause instanceof Error ? cause.message : t.loadError)); }}>{t.tryAgain}</button></div></section>;
  if (!doc) return <section className="help-page"><header className="page-heading"><div><p className="eyebrow">QHOME · DOCUMENTATION</p><h1>{t.title}</h1><p className="page-description">{t.subtitle}</p></div></header><div className="help-loading"><span className="spinner" />{t.loading}</div></section>;
  if (!pages.length) return <section className="help-page"><header className="page-heading"><div><p className="eyebrow">QHOME · DOCUMENTATION</p><h1>{t.title}</h1></div></header><p>{t.empty}</p></section>;
  return <section className="help-page">
    <header className="page-heading"><div><p className="eyebrow">QHOME · DOCUMENTATION</p><h1>{t.title}</h1><p className="page-description">{t.subtitle}</p></div></header>
    <div className="help-layout"><aside className="panel help-sidebar"><label className="help-search">{t.search}<input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder={t.search} /></label><nav aria-label={t.pages} className="help-nav">{visiblePages.length ? visiblePages.map(page => <div key={page.id}><button className="help-page-link" aria-current={page.id === selectedPage?.id ? "page" : undefined} onClick={() => open(page.id)}>{localized(page.title)}</button>{(matchesByPage.get(page.id) ?? []).map(section => <button key={section.id} className="help-section-link" onClick={() => open(page.id, section.id)}>{section.title}</button>)}</div>) : <p className="help-muted">{t.noMatch}</p>}</nav></aside>
      <article className="panel help-document">{selectedPage ? <><h2>{localized(selectedPage.title)}</h2>{(selectedPage.blocks ?? []).some(block => block.t === "h" && block.id) && <nav className="help-toc" aria-label={t.onPage}><strong>{t.onPage}</strong>{(selectedPage.blocks ?? []).filter(block => block.t === "h" && block.id).map(block => <a key={block.id} href={`#${headingId(selectedPage.id, block.id ?? "")}`} onClick={event => { event.preventDefault(); setAnchor(block.id ?? ""); }}>{localized(block.text)}</a>)}</nav>}{(selectedPage.blocks ?? []).map((block, index) => renderBlock(block, selectedPage.id, index))}</> : null}</article></div>
  </section>;
}
