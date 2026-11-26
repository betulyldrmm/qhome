import { useEffect, useState } from "react";
import type { BoardConfig, DashboardSnapshot, QHomeConfig, QHomeMeta, SystemSample } from "../types/api";
import { MetricCard } from "./MetricCard";
import { StatusBadge } from "./StatusBadge";
import { translate, type Language } from "../i18n";

interface SystemOverviewProps {
  config: QHomeConfig;
  meta: QHomeMeta;
  snapshot: DashboardSnapshot;
  language: Language;
}

function bytes(value?: number, locale = "en") {
  if (typeof value !== "number") return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value, unit = 0;
  while (size >= 1024 && unit < units.length - 1) { size /= 1024; unit += 1; }
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: size >= 100 || unit < 2 ? 0 : 1 }).format(size)} ${units[unit]}`;
}

function duration(seconds?: number) {
  if (typeof seconds !== "number") return "—";
  const days = Math.floor(seconds / 86400), hours = Math.floor(seconds % 86400 / 3600), minutes = Math.floor(seconds % 3600 / 60);
  if (days) return `${days}d ${hours}h`;
  if (hours) return `${hours}h ${minutes}m`;
  if (minutes) return `${minutes}m`;
  return `${Math.floor(seconds)}s`;
}

function usage(sample?: SystemSample["mem"], locale = "en") {
  if (!sample || typeof sample.pct !== "number") return { value: "—", detail: "" };
  const word = locale === "tr" ? "/" : "of";
  return { value: `${Math.round(sample.pct)}%`, detail: `${bytes(sample.used, locale)} ${word} ${bytes(sample.total, locale)}` };
}

export function SystemOverview({ config, meta, snapshot, language }: SystemOverviewProps) {
  const t = (key: Parameters<typeof translate>[1]) => translate(language, key);
  const [clientNow, setClientNow] = useState(Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setClientNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const sys = snapshot.sys ?? {};
  const locale = language === "tr" ? "tr-TR" : "en-US";
  const memory = usage(sys.mem, locale), storage = usage(sys.disk, locale);
  const localBoard: BoardConfig | undefined = config.boards.find(board => board.link?.type === "local");
  const onlineCount = config.boards.filter(board => snapshot.boards[board.id]?.online).length;
  const addresses = sys.ips?.length ? sys.ips : [];
  const boardTime = snapshot.time?.epoch != null
    ? new Date(clientNow + (snapshot.time.epoch * 1000 - Date.now()) + (snapshot.time.offset ?? 0) * 60_000)
    : null;
  const clockValue = boardTime ? boardTime.toISOString().slice(11, 19) : "—";
  const clockDetail = boardTime ? `${boardTime.toISOString().slice(0, 10)} · ${snapshot.time?.label ?? "UTC"} ${snapshot.time?.tz ?? ""}` : "—";
  const boardDescription = meta.sys?.board_model || (meta.sim ? "PC simulator" : meta.has_local ? "Arduino UNO Q" : `PC hub${meta.sys?.hostname ? ` · ${meta.sys.hostname}` : ""}`);
  return (
    <section className="system-section" aria-labelledby="system-heading">
      <div className="section-heading"><div><p className="eyebrow">{t("system")}</p><h2 id="system-heading">{t("overview")}</h2></div><StatusBadge online={Boolean(snapshot.mqtt?.ok)}>{snapshot.mqtt?.ok ? t("mqttConnected") : t("mqttOffline")}</StatusBadge></div>
      <div className="metric-grid">
        <MetricCard label={t("host")} value={config.device.name || "QHome"} detail={boardDescription} icon="⌂" />
        <MetricCard label={t("clock")} value={clockValue} detail={clockDetail} icon="◷" />
        <MetricCard label={t("uptime")} value={duration(snapshot.uptime)} detail={typeof sys.os_uptime === "number" ? `${t("system")} ${duration(sys.os_uptime)}` : t("appUptime")} icon="◷" />
        <MetricCard label={t("cpu")} value={typeof sys.cpu === "number" ? `${sys.cpu.toFixed(1)}%` : "—"} detail={sys.load?.[0] != null ? `${t("load")} ${sys.load[0].toFixed(2)} · ${meta.sys?.cpus ?? "—"} ${t("cores")}` : "Live system metric"} percent={sys.cpu} icon="▥" />
        <MetricCard label={t("memory")} value={memory.value} detail={memory.detail || t("systemMemory")} percent={sys.mem?.pct} icon="▤" />
        <MetricCard label={t("storage")} value={storage.value} detail={storage.detail || t("dataVolume")} percent={sys.disk?.pct} icon="▰" />
        <MetricCard label={t("temperature")} value={typeof sys.temp === "number" ? `${sys.temp.toFixed(1)}°C` : "—"} detail={t("hostTemp")} icon="♨" />
        <MetricCard label={t("webAddress")} value={addresses[0] ?? "—"} detail={`${t("port")} ${sys.port ?? meta.web_port}`} href={addresses[0] ? `http://${addresses[0]}:${sys.port ?? meta.web_port}` : undefined} icon="⌁" />
        <MetricCard label={t("software")} value={`QHome ${meta.version}`} detail={[meta.sys?.python ? `Python ${meta.sys.python}` : null, meta.sys?.os, localBoard && snapshot.boards[localBoard.id]?.fw != null ? `Firmware v${snapshot.boards[localBoard.id].fw}` : null].filter(Boolean).join(" · ")} icon="⌘" />
        {meta.role !== "node" && <MetricCard label={t("boardsOnline")} value={`${onlineCount} / ${config.boards.length}`} detail={`${snapshot.running ?? 0} ${t("scriptsRunning")}`} icon="⌗" />}
      </div>
      {addresses.length > 1 && <div className="address-list">{addresses.slice(1).map(address => <span key={address}>{address}</span>)}</div>}
    </section>
  );
}
