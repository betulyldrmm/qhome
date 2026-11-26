import { useEffect, useState } from "react";
import { DashboardPage } from "./pages/DashboardPage";
import { BoardsPage } from "./pages/BoardsPage";
import { AutomationsPage } from "./pages/AutomationsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { LogsPage } from "./pages/LogsPage";
import { HelpPage } from "./pages/HelpPage";
import { useDashboard } from "./hooks/useDashboard";
import { translate, type Language } from "./i18n";

type Page = "dashboard" | "boards" | "automations" | "settings" | "logs" | "help";
const pages: Page[] = ["dashboard", "boards", "automations", "settings", "logs", "help"];
const pageFromPath = (): Page => {
  const candidate = window.location.pathname.replace(/^\/+|\/+$/g, "") as Page;
  return pages.includes(candidate) ? candidate : "dashboard";
};
const pathForPage = (target: Page) => target === "dashboard" ? "/" : `/${target}`;

export default function App() {
  const { data, error, refreshing, refresh } = useDashboard();
  const [language] = useState<Language>(() => localStorage.getItem("qhome.lang") === "tr" ? "tr" : "en");
  const [page, setPage] = useState<Page>(pageFromPath);
  const [boardsDirty, setBoardsDirty] = useState(false);
  const [automationsDirty, setAutomationsDirty] = useState(false);
  const [settingsDirty, setSettingsDirty] = useState(false);
  const t = (key: Parameters<typeof translate>[1]) => translate(language, key);

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if ((page === "boards" && boardsDirty) || (page === "automations" && automationsDirty) || (page === "settings" && settingsDirty)) { event.preventDefault(); event.returnValue = ""; }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [page, boardsDirty, automationsDirty, settingsDirty]);

  useEffect(() => {
    const restorePage = () => setPage(pageFromPath());
    window.addEventListener("popstate", restorePage);
    return () => window.removeEventListener("popstate", restorePage);
  }, []);

  const navigate = (target: Page) => {
    if (target === page) return;
    const dirty = (page === "boards" && boardsDirty) || (page === "automations" && automationsDirty) || (page === "settings" && settingsDirty);
    if (dirty && !window.confirm(language === "tr" ? "Kaydedilmemiş değişiklikler silinsin mi?" : "Discard unsaved changes and leave this page?")) return;
    window.history.pushState({}, "", pathForPage(target));
    setPage(target);
    setBoardsDirty(false);
    setAutomationsDirty(false);
    setSettingsDirty(false);
  };
  const selectLanguage = (next: Language) => {
    if (next === language) return;
    const dirty = (page === "boards" && boardsDirty) || (page === "automations" && automationsDirty) || (page === "settings" && settingsDirty);
    if (dirty && !window.confirm(language === "tr" ? "Dil değişikliği kaydedilmemiş değişiklikleri siler. Devam edilsin mi?" : "Changing language discards unsaved changes. Continue?")) return;
    localStorage.setItem("qhome.lang", next);
    window.location.reload();
  };

  if (!data && refreshing) return <main className="app-state"><span className="spinner" /><p>{t("connecting")}</p></main>;
  if (!data) return <main className="app-state"><div className="error-panel"><span className="error-mark">!</span><h1>{t("backendUnavailable")}</h1><p>{error || t("noResponse")}</p><p className="muted">{t("startBackend")}</p><button className="primary-button" onClick={() => void refresh(true)}>{t("retry")}</button></div></main>;

  return <div className="app-shell">
    <aside className="sidebar">
      <button className="brand" onClick={() => navigate("dashboard")}><span className="brand-symbol">Q</span><span>QHome</span></button>
      <nav aria-label="Main navigation">
        <button className={`nav-item ${page === "dashboard" ? "active" : ""}`} onClick={() => navigate("dashboard")}><span>⌂</span>{t("dashboard")}</button>
        <button className={`nav-item ${page === "boards" ? "active" : ""}`} onClick={() => navigate("boards")}><span>▦</span>{t("boards")}</button>
        <button className={`nav-item ${page === "automations" ? "active" : ""}`} onClick={() => navigate("automations")}><span>▧</span>{t("automations")}</button>
        <button className={`nav-item ${page === "settings" ? "active" : ""}`} onClick={() => navigate("settings")}><span>⚙</span>{t("settings")}</button>
        <button className={`nav-item ${page === "logs" ? "active" : ""}`} onClick={() => navigate("logs")}><span>≡</span>{t("logs")}</button>
        <button className={`nav-item ${page === "help" ? "active" : ""}`} onClick={() => navigate("help")}><span>?</span>{t("help")}</button>
      </nav>
      <div className="sidebar-bottom"><div className={`backend-status ${error ? "backend-offline" : ""}`}><span className={error ? "offline-pulse" : "live-pulse"} />{error ? t("offline") : t("connected")}</div><div className="language-toggle" aria-label={t("language")}><button className={language === "en" ? "selected" : ""} onClick={() => selectLanguage("en")}>EN</button><button className={language === "tr" ? "selected" : ""} onClick={() => selectLanguage("tr")}>TR</button></div><span className="app-version">QHome {data.meta.version}</span></div>
    </aside>
    <main className="main-content">{page === "dashboard" && <DashboardPage data={data} language={language} />}{page === "boards" && <BoardsPage data={data} language={language} onSaved={() => refresh(false)} onDirtyChange={setBoardsDirty} />}{page === "settings" && <SettingsPage data={data} language={language} onSaved={() => refresh(false)} onDirtyChange={setSettingsDirty} />}{page === "logs" && <LogsPage language={language} />}{page === "help" && <HelpPage data={data} language={language} />}<div className={page === "automations" ? "automation-route-active" : "automation-route-hidden"}><AutomationsPage data={data} language={language} active={page === "automations"} onSaved={() => refresh(false)} onDirtyChange={setAutomationsDirty} /></div></main>
    {error && <div className="connection-warning" role="status">{t("interrupted")}</div>}
  </div>;
}
