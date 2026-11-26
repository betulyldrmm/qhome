export type DeviceType =
  | "binary_input"
  | "analog_sensor"
  | "pulse_counter"
  | "switch_output"
  | "pwm_output"
  | "dac_output"
  | "rgb_led"
  | "led_matrix"
  | "virtual_switch";

export interface ComponentConfig {
  id: string;
  type: DeviceType;
  name: string;
  board: string | null;
  pin?: string | number;
  props?: Record<string, unknown>;
}

export interface BoardConfig {
  id: string;
  name: string;
  model: string;
  link?: { type?: string; [key: string]: unknown };
}

export interface ModelPin { id: string | number; label: string; alt?: string; caps: string[]; notes: string[]; }
export interface BoardHeader { name?: string; side?: string; x: number; y: number; cols?: number; pins: Array<string | number | { pad?: string; same?: string | number }>; }
export interface BoardPart { type: string; x: number; y: number; w?: number; h?: number; label?: string; pin?: string | number; cols?: number; rows?: number; }
export interface BoardFootprint { w: number; h: number; headers?: BoardHeader[]; parts?: BoardPart[]; }
export interface DiscoveredBoard { key: string; link: "usb" | "wifi"; id?: string; port?: string; model?: string | null; proto?: string | null; boot?: string | null; t?: number; }
export interface SerialPortInfo { name: string; busy?: boolean; }
export interface ConfigSaveResult { ok: boolean; errors?: string[]; restart?: boolean; }

export interface QHomeConfig {
  device: { name?: string; node?: string; role?: "master" | "node"; master_host?: string; [key: string]: unknown };
  boards: BoardConfig[];
  components: ComponentConfig[];
  mqtt?: Record<string, unknown>;
  scripts?: { workspace?: Record<string, unknown>; [key: string]: unknown };
  [key: string]: unknown;
}

export interface DeviceState {
  v?: unknown;
  txt?: string;
  t?: number;
}

export interface BoardState {
  online?: boolean;
  text?: string;
  model?: string | null;
  fw?: number | null;
}

export interface SystemSample {
  cpu?: number | null;
  load?: number[] | null;
  mem?: { pct?: number; used?: number; total?: number } | null;
  disk?: { pct?: number; used?: number; total?: number } | null;
  temp?: number | null;
  os_uptime?: number | null;
  ips?: string[];
  port?: number;
}

export interface DashboardSnapshot {
  rev: number;
  states: Record<string, DeviceState>;
  boards: Record<string, BoardState>;
  mqtt?: { mode?: string; ok?: boolean; text?: string };
  matrix?: Record<string, string>;
  mx?: Record<string, { mode?: string; auto?: boolean; left?: number }>;
  discovered?: DiscoveredBoard[];
  vars?: Record<string, unknown>;
  running?: number;
  uptime?: number;
  sys?: SystemSample;
  time?: { tz?: string; epoch?: number; offset?: number; label?: string; abbr?: string; exact?: boolean };
  logs?: ApiLogEntry[];
}

export interface ApiLogEntry { n: number; t: number; lvl: "info" | "warn" | "err" | string; msg: string; }

export interface DevicePropertyDefinition {
  key: string;
  default: unknown;
  [key: string]: unknown;
}

export interface DeviceTypeDefinition {
  cap: string | null;
  tag: string;
  kind: string;
  props: DevicePropertyDefinition[];
}

export interface BoardModel {
  label?: string;
  pins: ModelPin[];
  links: string[];
  layout?: Array<[string, Array<string | number>]>;
  board?: BoardFootprint | null;
  serial_pins?: Array<string | number>;
  uart_pins?: Array<string | number>;
  i2c_pins?: Array<string | number>;
  usb_shares_uart?: boolean;
  logic?: number;
  adc_max?: number;
  vref?: number;
}

export interface QHomeMeta {
  version: string;
  role: "master" | "node";
  sim: boolean;
  has_local: boolean;
  web_port: number;
  link_port?: number;
  tz?: { zones?: string[]; fixed?: string[]; db?: boolean; default?: string };
  sys?: { board_model?: string; hostname?: string; python?: string; os?: string; arch?: string; cpus?: number };
  types: Record<DeviceType, DeviceTypeDefinition>;
  models: Record<string, BoardModel>;
  colors: string[];
  entity_fields?: Record<string, string[]>;
  matrix?: { modes?: string[]; anims?: string[]; icons?: Record<string, string> };
}

export interface ApiContext {
  config: QHomeConfig;
  meta: QHomeMeta;
  snapshot: DashboardSnapshot;
}
