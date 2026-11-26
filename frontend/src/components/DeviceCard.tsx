import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { api } from "../services/api";
import type { BoardConfig, BoardState, ComponentConfig, DeviceState, DeviceTypeDefinition } from "../types/api";
import { StatusBadge } from "./StatusBadge";
import { translate, type Language } from "../i18n";

interface DeviceCardProps {
  component: ComponentConfig;
  board?: BoardConfig;
  boardState?: BoardState;
  state?: DeviceState;
  definition: DeviceTypeDefinition;
  colors: string[];
  frame?: string;
  matrixMode?: { mode?: string; auto?: boolean; left?: number };
  matrixModes?: string[];
  matrixIcons?: string[];
  matrixAnimations?: string[];
  matrixSources?: ComponentConfig[];
  matrixNumericTypes?: string[];
  maxVoltage?: number;
  simulated?: boolean;
  language: Language;
  onCommandError: (message: string) => void;
}

const colorValue: Record<string, string> = {
  off: "#66746e", red: "#e5564d", green: "#35a66f", yellow: "#e8b83c",
  blue: "#4e88dc", magenta: "#bd68c8", cyan: "#38b9bd", white: "#f5f5ee",
};

function pwmLevel(value: unknown): number {
  return value && typeof value === "object" && "level" in value ? Number(value.level) || 0 : 0;
}

function pwmIsOn(value: unknown): boolean {
  return Boolean(value && typeof value === "object" && "on" in value && value.on);
}

function createSparkline(values: number[]): string | null {
  if (values.length < 2) return null;
  const min = Math.min(...values), range = Math.max(...values) - min || 1;
  return values.map((sample, index) => `${(index / (values.length - 1) * 100).toFixed(1)},${(26 - (sample - min) / range * 24).toFixed(1)}`).join(" ");
}

function commandError(error: unknown, report: (message: string) => void, language: Language) {
  report(error instanceof Error ? error.message : translate(language, "commandFailed"));
}

export function DeviceCard({ component, board, boardState, state, definition, colors, frame, matrixMode, matrixModes = [], matrixIcons = [], matrixAnimations = [], matrixSources = [], matrixNumericTypes = [], maxVoltage = 5, simulated = false, language, onCommandError }: DeviceCardProps) {
  const [matrixText, setMatrixText] = useState("");
  const [matrixArgument, setMatrixArgument] = useState("");
  const [history, setHistory] = useState<number[]>([]);
  const lastSample = useRef<number | undefined>(undefined);
  const value = state?.v;
  const props = component.props ?? {};
  const online = definition.cap === null || Boolean(boardState?.online);
  const t = (key: Parameters<typeof translate>[1]) => translate(language, key);
  const send = (action: string, next?: unknown) => {
    void api.command(component.id, action, next).catch(error => commandError(error, onCommandError, language));
  };
  const displayName = component.name || component.id;

  useEffect(() => {
    if (typeof value !== "number" || state?.t == null || lastSample.current === state.t) return;
    lastSample.current = state.t;
    setHistory(current => [...current, value].slice(-60));
  }, [state?.t, value]);

  const sparkline = createSparkline(history);

  return (
    <article className={`device-card ${online ? "" : "is-device-offline"}`}>
      <div className="device-topline">
        <span className={`device-type type-${component.type}`}>{definition.tag}</span>
        <span className="device-name" title={displayName}>{displayName}</span>
        <span className="device-pin">{component.pin == null ? t("virtual") : `${t("pin")} ${component.pin}`}</span>
      </div>
      {component.type === "binary_input" && <div className="device-reading">
        <span className={`reading-lamp ${value ? "lamp-on" : ""}`} />
        <strong>{value == null ? "—" : value ? t("on") : t("off")}</strong>
        {simulated && component.board !== null && <button className="small-button" onPointerDown={() => {
          const press = (held: boolean) => api.simulateInput(component.board ?? "", component.pin, held ? (props.invert ? 0 : 1) : (props.invert ? 1 : 0)).catch(error => commandError(error, onCommandError, language));
          void press(true);
          const release = () => { void press(false); };
          window.addEventListener("pointerup", release, { once: true });
          window.addEventListener("pointercancel", release, { once: true });
        }}>{t("holdSim")}</button>}
      </div>}
      {(component.type === "analog_sensor" || component.type === "pulse_counter") && <div className="device-reading sensor-reading">
        <strong>{state?.txt || "—"}</strong><span>{String(props.unit ?? "")}</span>
        {sparkline && <svg className="device-sparkline" viewBox="0 0 100 28" preserveAspectRatio="none" aria-label="Recent sensor readings"><polyline points={sparkline} /></svg>}
      </div>}
      {(component.type === "switch_output" || component.type === "virtual_switch") && <div className="device-reading">
        <button className={`switch-control ${value ? "switch-on" : ""}`} role="switch" aria-checked={Boolean(value)} aria-label={`Toggle ${displayName}`} onClick={() => send("toggle")}>
          <span />
        </button><strong>{value ? t("on") : t("off")}</strong>
      </div>}
      {component.type === "pwm_output" && <div className="device-reading range-reading">
        <strong>{pwmIsOn(value) ? `${Math.round(pwmLevel(value))}%` : t("off")}</strong>
        <input aria-label={`${displayName} level`} type="range" min="0" max="100" value={pwmLevel(value)} onChange={event => send("set", Number(event.target.value))} />
      </div>}
      {component.type === "dac_output" && <div className="device-reading range-reading">
        <strong>{typeof value === "number" ? `${value.toFixed(2)} V` : "—"}</strong>
        <input aria-label={`${displayName} voltage`} type="range" min="0" max={maxVoltage} step="0.01" value={typeof value === "number" ? value : 0} onChange={event => send("set", Number(event.target.value))} />
      </div>}
      {component.type === "rgb_led" && <div className="color-controls" aria-label={`${displayName} color`}>
        {colors.map(color => <button key={color} title={color} aria-label={color} aria-pressed={value === color} style={{ "--swatch": colorValue[color] ?? color } as CSSProperties} onClick={() => send("set", color)} />)}
      </div>}
      {component.type === "led_matrix" && <div className="matrix-controls">
        <div><div className="matrix-preview" aria-label="LED matrix output">
          {Array.from({ length: 104 }, (_, index) => <i key={index} className={frame?.[index] && frame[index] !== "0" ? "pixel-on" : ""} />)}
        </div>{matrixMode && !matrixMode.auto && <span className="matrix-override">{t("changed")}{matrixMode.left ? ` · ${matrixMode.left}s` : ""}</span>}</div>
        <div className="matrix-actions">
          <select aria-label="LED matrix mode" value={matrixMode?.auto ? "auto" : matrixMode?.mode || "auto"} onChange={event => send("mode", event.target.value)}>
            <option value="auto">{t("asConfigured")}</option>
            {matrixModes.map(mode => <option key={mode} value={mode}>{({ clock: t("clock"), status: t("boardStatus"), off: t("off") } as Record<string, string>)[mode] || mode}</option>)}
          </select>
          {matrixMode?.mode === "icon" && <select aria-label="Matrix icon" value={matrixArgument} onChange={event => { setMatrixArgument(event.target.value); send("icon", event.target.value); }}><option value="">Choose icon...</option>{matrixIcons.map(icon => <option key={icon} value={icon}>{icon}</option>)}</select>}
          {matrixMode?.mode === "anim" && <select aria-label="Matrix animation" value={matrixArgument} onChange={event => { setMatrixArgument(event.target.value); send("anim", event.target.value); }}><option value="">Choose animation...</option>{matrixAnimations.map(animation => <option key={animation} value={animation}>{animation}</option>)}</select>}
          {(matrixMode?.mode === "value" || matrixMode?.mode === "bar") && <select aria-label="Matrix value source" value={matrixArgument || String(props.source ?? "")} onChange={event => { setMatrixArgument(event.target.value); send(matrixMode.mode || "value", event.target.value); }}><option value="">Choose a device...</option>{matrixSources.filter(source => matrixMode.mode !== "bar" || matrixNumericTypes.includes(source.type)).map(source => <option key={source.id} value={source.id}>{source.name || source.id}</option>)}</select>}
          {matrixMode?.mode === "text" && <form onSubmit={event => { event.preventDefault(); if (matrixText.trim()) send("text", matrixText); }}>
            <input aria-label={t("showText")} value={matrixText} onChange={event => setMatrixText(event.target.value)} placeholder={t("showText")} />
            <button type="submit" className="small-button">{t("show")}</button>
          </form>}
        </div>
      </div>}
      <div className="device-footer">
        {board ? <><span className={`mini-dot ${online ? "" : "is-offline"}`} />{board.name || board.id} <span>· {boardState?.text || board.model}</span></> : <span>{t("virtualDevice")}</span>}
        {component.type === "binary_input" && !online && <StatusBadge online={false}>{t("offline")}</StatusBadge>}
      </div>
    </article>
  );
}
