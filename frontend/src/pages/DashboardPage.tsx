import { useMemo, useState } from "react";
import { DeviceCard } from "../components/DeviceCard";
import { SystemOverview } from "../components/SystemOverview";
import { StatusBadge } from "../components/StatusBadge";
import type { ApiContext, ComponentConfig } from "../types/api";
import { translate, type Language } from "../i18n";

interface DashboardPageProps {
  data: ApiContext;
  language: Language;
}

export function DashboardPage({ data, language }: DashboardPageProps) {
  const { config, meta, snapshot } = data;
  const [commandError, setCommandError] = useState<string | null>(null);
  const t = (key: Parameters<typeof translate>[1]) => translate(language, key);
  const groups = useMemo(() => config.boards.map(board => ({
    board,
    components: config.components.filter(component => component.board === board.id && meta.types[component.type]?.cap),
  })).filter(group => group.components.length > 0), [config.boards, config.components, meta.types]);
  const virtualDevices: ComponentConfig[] = config.components.filter(component => !meta.types[component.type]?.cap);
  const sourceDefinition = meta.types.led_matrix?.props.find(property => property.key === "source");
  const matrixSourceTypes = Array.isArray(sourceDefinition?.kinds) ? sourceDefinition.kinds.filter((type): type is string => typeof type === "string") : [];
  const matrixSources = config.components.filter(component => matrixSourceTypes.includes(component.type));
  const matrixNumericTypes = meta.entity_fields?.get_value ?? matrixSourceTypes;

  return (
    <div className="dashboard-page">
      <header className="page-heading">
        <div><p className="eyebrow">QHOME · SMART HOME</p><h1>{t("dashboard")}</h1><p className="page-description">{t("tagline")}</p></div>
        <div className="live-indicator"><span className="live-pulse" />{t("live")}</div>
      </header>
      <SystemOverview config={config} meta={meta} snapshot={snapshot} language={language} />
      <section className="devices-section" aria-labelledby="devices-heading">
        <div className="section-heading"><div><p className="eyebrow">{t("setup")}</p><h2 id="devices-heading">{t("devices")}</h2></div><span className="device-count">{config.components.length} {t("configured")}</span></div>
        {commandError && <div className="inline-error" role="alert">{commandError}<button onClick={() => setCommandError(null)} aria-label="Dismiss">×</button></div>}
        {config.components.length === 0 ? <div className="empty-state"><span className="empty-icon">⌘</span><h3>{t("noDevices")}</h3><p>{t("noDevicesHelp")}</p></div> : <>
          {groups.map(({ board, components }) => {
            const boardState = snapshot.boards[board.id];
            return <section className="board-group" key={board.id}>
              <div className="board-heading"><div className="board-title"><span className={`mini-dot ${boardState?.online ? "" : "is-offline"}`} /><h3>{board.name || board.id}</h3><span className="model-label">{meta.models[board.model]?.label ?? board.model}</span></div><StatusBadge online={Boolean(boardState?.online)}>{boardState?.online ? t("online") : boardState?.text || t("offline")}</StatusBadge></div>
              <div className="device-grid">{components.map(component => <DeviceCard key={component.id} component={component} board={board} boardState={boardState} state={snapshot.states[component.id]} definition={meta.types[component.type]} colors={meta.colors} frame={snapshot.matrix?.[component.id]} matrixMode={snapshot.mx?.[component.id]} matrixModes={meta.matrix?.modes} matrixIcons={Object.keys(meta.matrix?.icons ?? {})} matrixAnimations={meta.matrix?.anims} matrixSources={matrixSources} matrixNumericTypes={matrixNumericTypes} maxVoltage={meta.models[board.model]?.vref} simulated={boardState?.text === "simulated"} language={language} onCommandError={setCommandError} />)}</div>
            </section>;
          })}
          {virtualDevices.length > 0 && <section className="board-group"><div className="board-heading"><div className="board-title"><h3>{t("virtual")}</h3></div><span className="model-label">{t("noPin")}</span></div><div className="device-grid">{virtualDevices.map(component => <DeviceCard key={component.id} component={component} state={snapshot.states[component.id]} definition={meta.types[component.type]} colors={meta.colors} language={language} onCommandError={setCommandError} />)}</div></section>}
        </>}
      </section>
      {Object.keys(snapshot.vars ?? {}).length > 0 && <section className="variables-section"><div className="section-heading"><div><p className="eyebrow">{t("automations")}</p><h2>{t("scriptVars")}</h2></div></div><div className="variables-list">{Object.entries(snapshot.vars ?? {}).map(([name, value]) => <span key={name} className="variable-chip">{name} <strong>{String(value)}</strong></span>)}</div></section>}
    </div>
  );
}
