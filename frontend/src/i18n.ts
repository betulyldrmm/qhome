export type Language = "en" | "tr";

const messages = {
  en: {
    dashboard: "Dashboard", tagline: "Monitor your boards and control connected devices.", live: "Live data",
    overview: "Overview", devices: "Devices", system: "SYSTEM", setup: "YOUR SETUP", configured: "configured",
    connected: "Connected to backend", boards: "Boards & pins", automations: "Automations", settings: "Settings", logs: "Logs", help: "Help",
    noDevices: "No devices configured", noDevicesHelp: "Add a board and assign its pins in the existing QHome interface to see live devices here.",
    online: "Online", offline: "Offline", host: "Host", uptime: "Uptime", cpu: "CPU load", memory: "Memory",
    storage: "Storage", temperature: "Temperature", webAddress: "Web address", software: "Software", boardsOnline: "Boards online",
    appUptime: "Application uptime", hostTemp: "Host temperature", systemMemory: "System memory", dataVolume: "Data volume",
    mqttConnected: "MQTT connected", mqttOffline: "MQTT offline", virtual: "Virtual devices", noPin: "No physical pin",
    pin: "Pin", on: "On", asConfigured: "As configured", clock: "Clock", boardStatus: "Board status", off: "Off", showText: "Show text...", show: "Show",
    recent: "Recent sensor readings", backendUnavailable: "Backend unavailable", startBackend: "Start the Python backend on port 7000, then try again.",
    retry: "Retry connection", interrupted: "Backend connection interrupted. Showing the last received snapshot.", noResponse: "No response from QHome.",
    scriptsRunning: "automation scripts running", of: "of", connecting: "Connecting to QHome backend...", language: "Language", changed: "Changed",
    cores: "cores", load: "Load", port: "Port", commandFailed: "Command could not be sent.", virtualDevice: "Virtual device", dismiss: "Dismiss", holdSim: "Hold to press (simulation)", scriptVars: "Script variables",
  },
  tr: {
    dashboard: "Pano", tagline: "Kartlar\u0131n\u0131z\u0131 izleyin ve ba\u011fl\u0131 cihazlar\u0131 y\u00f6netin.", live: "Canl\u0131 veri",
    overview: "Genel bak\u0131\u015f", devices: "Cihazlar", system: "S\u0130STEM", setup: "KURULUMUNUZ", configured: "tan\u0131ml\u0131",
    connected: "Backend'e ba\u011fl\u0131", boards: "Kartlar ve pinler", automations: "Otomasyonlar", settings: "Ayarlar", logs: "G\u00fcnl\u00fckler", help: "Yard\u0131m",
    noDevices: "Tan\u0131ml\u0131 cihaz yok", noDevicesHelp: "Canl\u0131 cihazlar\u0131 burada g\u00f6rmek i\u00e7in mevcut QHome aray\u00fcz\u00fcnden kart ekleyip pinleri atay\u0131n.",
    online: "\u00c7evrimi\u00e7i", offline: "\u00c7evrimd\u0131\u015f\u0131", host: "Sunucu", uptime: "\u00c7al\u0131\u015fma s\u00fcresi", cpu: "\u0130\u015flemci y\u00fck\u00fc", memory: "Bellek",
    storage: "Depolama", temperature: "S\u0131cakl\u0131k", webAddress: "Web adresi", software: "Yaz\u0131l\u0131m", boardsOnline: "\u00c7evrimi\u00e7i kartlar",
    appUptime: "Uygulama \u00e7al\u0131\u015fma s\u00fcresi", hostTemp: "Sunucu s\u0131cakl\u0131\u011f\u0131", systemMemory: "Sistem belle\u011fi", dataVolume: "Veri alan\u0131",
    mqttConnected: "MQTT ba\u011fl\u0131", mqttOffline: "MQTT ba\u011flant\u0131s\u0131 yok", virtual: "Sanal cihazlar", noPin: "Fiziksel pin yok",
    pin: "Pin", on: "A\u00e7\u0131k", asConfigured: "Yap\u0131land\u0131r\u0131ld\u0131\u011f\u0131 gibi", clock: "Saat", boardStatus: "Kart durumu", off: "Kapal\u0131", showText: "Metin g\u00f6ster...", show: "G\u00f6ster",
    recent: "Son sens\u00f6r okumalar\u0131", backendUnavailable: "Backend kullan\u0131lam\u0131yor", startBackend: "Python backend'ini 7000 portunda ba\u015flat\u0131p yeniden deneyin.",
    retry: "Yeniden ba\u011flan", interrupted: "Backend ba\u011flant\u0131s\u0131 kesildi. Son al\u0131nan veriler g\u00f6steriliyor.", noResponse: "QHome yan\u0131t vermiyor.",
    scriptsRunning: "otomasyon beti\u011fi \u00e7al\u0131\u015f\u0131yor", of: "/", connecting: "QHome backend'ine ba\u011flan\u0131yor...", language: "Dil", changed: "De\u011fi\u015fti",
    cores: "\u00e7ekirdek", load: "Y\u00fck", port: "Port", commandFailed: "Komut g\u00f6nderilemedi.", virtualDevice: "Sanal cihaz", dismiss: "Kapat", holdSim: "Bas\u0131l\u0131 tut (sim\u00fclasyon)", scriptVars: "Betik de\u011fi\u015fkenleri",
  },
} as const;

type MessageKey = keyof typeof messages.en;

export function translate(language: Language, key: MessageKey): string {
  return messages[language][key];
}
