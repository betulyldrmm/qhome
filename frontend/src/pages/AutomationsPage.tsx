import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../services/api";
import type { ApiContext, ConfigSaveResult, QHomeConfig } from "../types/api";
import type { Language } from "../i18n";

interface Props { data: ApiContext; language: Language; active: boolean; onSaved: () => Promise<void>; onDirtyChange: (dirty: boolean) => void; }
interface QBlocksApi { init: (div: HTMLElement, context: Record<string, unknown>, colors: string[], changed: (workspace: WorkspaceJson) => void) => Promise<unknown>; load: (workspace: WorkspaceJson) => void; resize: () => void; save: () => WorkspaceJson; }
interface WorkspaceJson { blocks?: { blocks?: Array<Record<string, unknown>>; [key: string]: unknown }; [key: string]: unknown; }
interface BlocklyBridge { blocks: QBlocksApi; setLanguage: (language: string) => void; dispose: () => void; }
declare global { interface Window { __qhomeBlocklyBridge?: BlocklyBridge; Blockly?: { getMainWorkspace: () => { dispose: () => void } | null; }; } }

const emptyWorkspace: WorkspaceJson = { blocks: { languageVersion: 0, blocks: [] } };
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;
let scriptsReady: Promise<void> | undefined;
let initQueue = Promise.resolve();

function loadLegacyBlockly(): Promise<void> {
  if (scriptsReady) return scriptsReady;
  scriptsReady = (async () => {
    const sources = ["/static/vendor/blockly/blockly_compressed.js", "/static/vendor/blockly/blocks_compressed.js", "/static/i18n.js", "/static/blocks.js"];
    for (const src of sources) {
      await new Promise<void>((resolve, reject) => {
        const existing = document.querySelector<HTMLScriptElement>(`script[data-qhome-src="${src}"]`);
        if (existing?.dataset.loaded === "true") { resolve(); return; }
        const script = existing ?? document.createElement("script");
        script.src = src;
        script.dataset.qhomeSrc = src;
        script.onload = () => { script.dataset.loaded = "true"; resolve(); };
        script.onerror = () => reject(new Error(`Blockly resource could not be loaded: ${src}`));
        if (!existing) document.head.append(script);
      });
    }
    // The legacy scripts are classic scripts with lexical exports. This tiny bridge
    // exposes only their existing editor API; no Blockly implementation is copied.
    if (!window.__qhomeBlocklyBridge) {
      const bridge = document.createElement("script");
      bridge.text = "window.__qhomeBlocklyBridge={blocks:QBlocks,setLanguage:function(language){LANG=language;},dispose:function(){var workspace=Blockly.getMainWorkspace();if(workspace)workspace.dispose();}};";
      document.head.append(bridge);
      bridge.remove();
    }
    if (!window.__qhomeBlocklyBridge) throw new Error("QHome Blockly bridge was not initialized.");
  })().catch(error => { scriptsReady = undefined; throw error; });
  return scriptsReady;
}

const labels = {
  en: { title: "Automations", subtitle: "Create visual rules that run on the QHome controller.", hint: "Drag blocks from the toolbox and connect them below a yellow event block. Changes run after saving.", save: "Save automation", saving: "Saving…", saved: "Automation saved and applied.", running: "Running scripts", variables: "Variables", empty: "No automation blocks yet. Add an event block from the toolbox to begin.", loadError: "The Blockly editor could not be loaded.", saveError: "Automation could not be saved.", reload: "Reload saved workspace", dirty: "Unsaved automation changes", noDevice: "Entity blocks read the components configured under Boards & Pins." },
  tr: { title: "Otomasyonlar", subtitle: "QHome denetleyicisinde çalışacak görsel kurallar oluşturun.", hint: "Blokları araç kutusundan sürükleyip sarı olay bloğunun altına bağlayın. Değişiklikler kaydedilince çalışır.", save: "Otomasyonu kaydet", saving: "Kaydediliyor…", saved: "Otomasyon kaydedildi ve uygulandı.", running: "Çalışan betikler", variables: "Değişkenler", empty: "Henüz otomasyon bloğu yok. Başlamak için araç kutusundan bir olay bloğu ekleyin.", loadError: "Blockly editörü yüklenemedi.", saveError: "Otomasyon kaydedilemedi.", reload: "Kaydedilmiş çalışma alanını yükle", dirty: "Kaydedilmemiş otomasyon değişiklikleri", noDevice: "Cihaz blokları Kartlar ve Pinler bölümündeki bileşenleri kullanır." },
} as const;

export function AutomationsPage({ data, language, active, onSaved, onDirtyChange }: Props) {
  const tr = language === "tr";
  const text = labels[language];
  const hostRef = useRef<HTMLDivElement>(null);
  const configRef = useRef<QHomeConfig>(clone(data.config));
  const [workspace, setWorkspace] = useState<WorkspaceJson>(() => clone(data.config.scripts?.workspace as WorkspaceJson | undefined ?? emptyWorkspace));
  const workspaceRef = useRef(workspace);
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const blockCount = useMemo(() => workspace.blocks?.blocks?.length ?? 0, [workspace]);

  useEffect(() => { onDirtyChange(dirty); }, [dirty, onDirtyChange]);
  useEffect(() => { configRef.current = clone(data.config); }, [data.config]);
  useEffect(() => { if (active) requestAnimationFrame(() => window.__qhomeBlocklyBridge?.blocks.resize()); }, [active]);
  useEffect(() => {
    if (!active && dirty) {
      const saved = clone(data.config.scripts?.workspace as WorkspaceJson | undefined ?? emptyWorkspace);
      workspaceRef.current = saved; setWorkspace(saved); setDirty(false); setError("");
      window.__qhomeBlocklyBridge?.blocks.load(saved);
    }
  }, [active, dirty, data.config]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    initQueue = initQueue.then(async () => {
      await loadLegacyBlockly();
      if (!active || !hostRef.current) return;
      const bridge = window.__qhomeBlocklyBridge;
      if (!bridge) throw new Error("Blockly API is unavailable.");
      bridge.setLanguage(language);
      configRef.current = clone(data.config);
      const context = {
        comps: () => configRef.current.components,
        boards: () => configRef.current.boards,
        kinds: data.meta.entity_fields ?? {},
        matrix: data.meta.matrix ?? { icons: {}, anims: [] },
      };
      await bridge.blocks.init(hostRef.current, context, data.meta.colors, next => {
        if (!active) return;
        const copy = clone(next);
        workspaceRef.current = copy;
        setWorkspace(copy);
        setDirty(true);
        setNotice("");
      });
      if (!active) { bridge.dispose(); return; }
      bridge.blocks.load(workspaceRef.current);
      requestAnimationFrame(() => bridge.blocks.resize());
      setLoading(false);
    }).catch(cause => {
      if (active) { setError(cause instanceof Error ? cause.message : text.loadError); setLoading(false); }
    });
    const resize = () => window.__qhomeBlocklyBridge?.blocks.resize();
    window.addEventListener("resize", resize);
    return () => {
      active = false;
      window.removeEventListener("resize", resize);
    };
    // The editor is recreated only when the route or language changes. Data refresh
    // polls state only; the configuration remains the editor's explicit save baseline.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => () => { window.__qhomeBlocklyBridge?.dispose(); }, []);

  async function save() {
    const blocks = window.__qhomeBlocklyBridge?.blocks;
    const nextWorkspace = blocks?.save() ?? workspaceRef.current;
    const next = clone(configRef.current);
    next.scripts = { ...(next.scripts ?? {}), workspace: nextWorkspace };
    setSaving(true); setError(""); setNotice("");
    try {
      const result: ConfigSaveResult = await api.saveConfig(next);
      if (!result.ok) throw new Error(result.errors?.join("; ") || text.saveError);
      configRef.current = next;
      workspaceRef.current = clone(nextWorkspace);
      setWorkspace(workspaceRef.current);
      setDirty(false);
      setNotice(text.saved);
      await onSaved();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : text.saveError);
    } finally { setSaving(false); }
  }

  function reloadSaved() {
    const saved = clone(data.config.scripts?.workspace as WorkspaceJson | undefined ?? emptyWorkspace);
    workspaceRef.current = saved;
    setWorkspace(saved);
    setDirty(false); setError(""); setNotice("");
    window.__qhomeBlocklyBridge?.blocks.load(saved);
  }

  const vars = data.snapshot.vars ?? {};
  const running = data.snapshot.running ?? 0;
  return <section className="automations-page" aria-hidden={!active}>
    <header className="page-heading automation-heading"><div><p className="eyebrow">QHOME · BLOCKLY</p><h1>{text.title}</h1><p className="page-description">{text.subtitle}</p></div><div className="automation-actions"><button className="secondary-button" disabled={!dirty || saving} onClick={reloadSaved}>{text.reload}</button><button className="primary-button" disabled={!dirty || saving || loading} onClick={() => void save()}>{saving ? text.saving : text.save}</button></div></header>
    {error && <div className="boards-error" role="alert"><span>{error}</span><button onClick={() => setError("")} aria-label={tr ? "Kapat" : "Dismiss"}>×</button></div>}
    {notice && <div className="boards-notice" role="status">{notice}</div>}
    <div className="automation-toolbar"><span>{text.hint}</span><span className="automation-spacer" /><span className="automation-status"><i className={running ? "is-running" : ""} />{text.running}: {running}</span><span className="automation-status">{text.variables}:</span>{Object.entries(vars).map(([name, value]) => <span className="automation-var" key={name}>{name} = {String(value)}</span>)}{!Object.keys(vars).length && <span className="automation-var-empty">0</span>}{dirty && <strong>{text.dirty}</strong>}</div>
    <div className="automation-editor-shell"><div ref={hostRef} className="automation-editor" aria-label={tr ? "Blockly otomasyon çalışma alanı" : "Blockly automation workspace"} />{loading && <div className="automation-overlay"><span className="spinner" /><span>{tr ? "Blockly yükleniyor…" : "Loading Blockly…"}</span></div>}{!loading && !blockCount && <div className="automation-empty-hint">{text.empty}</div>}</div>
    <p className="automation-footnote">{text.noDevice}</p>
  </section>;
}
