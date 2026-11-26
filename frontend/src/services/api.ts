import type { ApiContext, ConfigSaveResult, DashboardSnapshot, QHomeConfig, QHomeMeta, SerialPortInfo } from "../types/api";

let authHeader: string | undefined;
let authPrompt: Promise<string | null> | null = null;

function basicHeader(password: string): string {
  const bytes = new TextEncoder().encode(`qhome:${password}`);
  return `Basic ${btoa(Array.from(bytes, byte => String.fromCharCode(byte)).join(""))}`;
}

async function askForPassword(): Promise<string | null> {
  if (!authPrompt) authPrompt = Promise.resolve(window.prompt("QHome web password / QHome web parolası") ?? null).finally(() => { authPrompt = null; });
  const password = await authPrompt;
  return password === null ? null : basicHeader(password);
}

async function authorizedResponse(path: string, init?: RequestInit): Promise<Response> {
  const send = (authorization?: string) => fetch(path, { ...init, headers: { Accept: "application/json", ...init?.headers, ...(authorization ? { Authorization: authorization } : {}) } });
  let response = await send(authHeader);
  if (response.status === 401) {
    authHeader = await askForPassword() ?? undefined;
    if (authHeader) response = await send(authHeader);
  }
  if (!response.ok) {
    const body = await response.text().catch(() => "");
    let detail = body;
    try {
      const parsed: unknown = JSON.parse(body);
      if (parsed && typeof parsed === "object" && "errors" in parsed && Array.isArray(parsed.errors)) {
        detail = parsed.errors.map(String).join("; ");
      } else if (parsed && typeof parsed === "object" && "error" in parsed && typeof parsed.error === "string") {
        detail = parsed.error;
      }
    } catch { /* the server can return a plain-text error body */ }
    throw new Error(`API ${response.status} ${response.statusText}${detail ? `: ${detail}` : ""}`);
  }
  return response;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await authorizedResponse(path, init);
  return response.json() as Promise<T>;
}

async function requestText(path: string): Promise<string> {
  return (await authorizedResponse(path)).text();
}

export const api = {
  setWebPassword(password: string) { authHeader = password ? basicHeader(password) : undefined; },
  getMeta: () => request<QHomeMeta>("/api/meta"),
  getConfig: () => request<QHomeConfig>("/api/config"),
  getState: (logSequence?: number) => request<DashboardSnapshot>(`/api/state${logSequence === undefined ? "" : `?log=${encodeURIComponent(String(logSequence))}`}`),
  getPorts: () => request<SerialPortInfo[]>("/api/ports"),
  getHelp: () => requestText("/static/help.js"),
  saveConfig: (config: QHomeConfig) => request<ConfigSaveResult>("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  }),
  async getDashboard(): Promise<ApiContext> {
    const [meta, config, snapshot] = await Promise.all([this.getMeta(), this.getConfig(), this.getState()]);
    return { meta, config, snapshot };
  },
  command(id: string, action: string, value?: unknown) {
    return request<{ ok: boolean }>("/api/cmd", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, action, value }),
    });
  },
  simulateInput(board: string, pin: string | number | undefined, value: number) {
    return request<{ ok: boolean }>("/api/sim", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ board, pin, value }),
    });
  },
};
