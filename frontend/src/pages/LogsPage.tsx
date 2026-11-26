import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../services/api";
import type { ApiLogEntry } from "../types/api";
import type { Language } from "../i18n";

const words = {
  en: { title: "Logs", subtitle: "Recent events reported by the QHome controller.", refresh: "Refresh", refreshing: "Refreshing…", search: "Search log messages", level: "Level", all: "All levels", info: "Info", warn: "Warnings", err: "Errors", empty: "No log entries yet.", noMatches: "No log entries match these filters.", loading: "Loading logs…", count: "entries", connectionError: "Could not load logs from the backend.", sequence: "Sequence" },
  tr: { title: "Günlükler", subtitle: "QHome denetleyicisinin bildirdiği son olaylar.", refresh: "Yenile", refreshing: "Yenileniyor…", search: "Günlük mesajlarında ara", level: "Seviye", all: "Tüm seviyeler", info: "Bilgi", warn: "Uyarılar", err: "Hatalar", empty: "Henüz günlük kaydı yok.", noMatches: "Bu filtrelerle eşleşen kayıt yok.", loading: "Günlükler yükleniyor…", count: "kayıt", connectionError: "Günlükler backend'den alınamadı.", sequence: "Sıra" },
} as const;
const pollMs = 1500;

export function LogsPage({ language }: { language: Language }) {
  const t = words[language];
  const [logs, setLogs] = useState<ApiLogEntry[]>([]);
  const [loading, setLoading] = useState(true), [refreshing, setRefreshing] = useState(false), [error, setError] = useState("");
  const [query, setQuery] = useState(""), [level, setLevel] = useState("all");
  const cursor = useRef(0), timer = useRef<number | undefined>(undefined), alive = useRef(true);

  const apply = useCallback((entries: ApiLogEntry[], replace = false) => {
    if (entries.length) cursor.current = Math.max(cursor.current, ...entries.map(entry => entry.n));
    setLogs(current => {
      const next = replace ? entries : [...current, ...entries.filter(entry => !current.some(old => old.n === entry.n))];
      return next.slice(-400);
    });
  }, []);
  const refresh = useCallback(async (replace = true) => {
    setRefreshing(true);
    try { const snapshot = await api.getState(replace ? 0 : cursor.current); apply(snapshot.logs ?? [], replace); setError(""); }
    catch (cause) { setError(cause instanceof Error ? cause.message : t.connectionError); }
    finally { if (alive.current) { setRefreshing(false); setLoading(false); } }
  }, [apply, t.connectionError]);

  useEffect(() => {
    alive.current = true;
    let stopped = false;
    const poll = async () => {
      try { const state = await api.getState(cursor.current); if (!stopped) { apply(state.logs ?? []); setError(""); } }
      catch (cause) { if (!stopped) setError(cause instanceof Error ? cause.message : t.connectionError); }
      finally { if (!stopped) timer.current = window.setTimeout(poll, pollMs); }
    };
    void refresh(true).then(() => { if (!stopped) timer.current = window.setTimeout(poll, pollMs); });
    return () => { stopped = true; alive.current = false; if (timer.current !== undefined) window.clearTimeout(timer.current); };
  }, [apply, refresh, t.connectionError]);

  const filtered = useMemo(() => {
    const q = query.trim().toLocaleLowerCase(language === "tr" ? "tr-TR" : "en-US");
    return logs.filter(entry => (level === "all" || entry.lvl === level) && (!q || entry.msg.toLocaleLowerCase(language === "tr" ? "tr-TR" : "en-US").includes(q)));
  }, [language, level, logs, query]);
  const levelLabel = (value: string) => value === "err" ? t.err : value === "warn" ? t.warn : t.info;
  return <section className="logs-page">
    <header className="page-heading"><div><p className="eyebrow">QHOME · EVENTS</p><h1>{t.title}</h1><p className="page-description">{t.subtitle}</p></div><button className="secondary-button logs-refresh" onClick={() => void refresh(true)} disabled={refreshing}>{refreshing ? t.refreshing : t.refresh}</button></header>
    {error && <div className="boards-error" role="alert"><span>{error}</span><button onClick={() => setError("")} aria-label={language === "tr" ? "Kapat" : "Dismiss"}>×</button></div>}
    <div className="logs-filters panel"><label className="logs-search">{t.search}<input type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder={t.search} /></label><label>{t.level}<select value={level} onChange={event => setLevel(event.target.value)}><option value="all">{t.all}</option><option value="info">{t.info}</option><option value="warn">{t.warn}</option><option value="err">{t.err}</option></select></label><span className="logs-count">{filtered.length} / {logs.length} {t.count}</span></div>
    <div className="logs-list panel" aria-live="polite" aria-busy={loading}>
      {loading ? <div className="logs-empty"><span className="spinner" />{t.loading}</div> : !logs.length ? <p className="logs-empty">{t.empty}</p> : !filtered.length ? <p className="logs-empty">{t.noMatches}</p> : filtered.slice().reverse().map(entry => <article className={`log-entry log-${entry.lvl}`} key={entry.n}><time dateTime={new Date(entry.t * 1000).toISOString()}>{new Date(entry.t * 1000).toLocaleString(language === "tr" ? "tr-TR" : "en-US")}</time><span className="log-level">{levelLabel(entry.lvl)}</span><span className="log-seq">#{entry.n}</span><p>{entry.msg}</p></article>)}
    </div>
  </section>;
}
