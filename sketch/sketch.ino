// QHome master firmware for the Arduino UNO Q microcontroller (STM32U585).
//
// Upload once. Pin roles, block scripts and settings are sent LIVE from the Linux side
// through the Router Bridge, so nothing here is ever recompiled when you change your setup.
//
// Pin numbers are the Arduino pin numbers of the Zephyr core:
//   0..13  D0..D13          14..19  A0..A5          20, 21  SDA, SCL (D20, D21)
//   22..24 JSPI header (CIPO, COPI, SCK)
//
// Pin modes: 0 off, 1 input, 2 input pull-up, 3 input pull-down, 4 digital output,
//            5 PWM, 6 analog input (14 bit), 7 DAC (12 bit, A0/A1), 8 pulse counter
//
// Links: the microcontroller also relays QLink text lines between Linux and other boards
//   kind 1  UART on D0/D1 (Serial1)      a = baud rate
//   kind 2  I2C on SDA/SCL (Wire)        a = satellite address, b = poll period in ms
//   kind 3  I2C on Qwiic (Wire1)         a = satellite address, b = poll period in ms
//
// Serial Monitor: Linux sends the address of the web page (q_info) and this sketch prints it
// on the App Lab Serial Monitor, again every 30 s and whenever a key is pressed there.

#include <Arduino_RouterBridge.h>
#include <Arduino_LED_Matrix.h>
#include <Wire.h>

#define QH_VERSION 5
#define NPIN 25
#define NLINK 4
#define LINE_MAX 127

enum { M_OFF = 0, M_DIN = 1, M_DIN_PU = 2, M_DIN_PD = 3, M_DOUT = 4,
       M_PWM = 5, M_ADC = 6, M_DAC = 7, M_CNT = 8 };
enum { L_NONE = 0, L_UART = 1, L_I2C_WIRE = 2, L_I2C_QWIIC = 3 };

static const int ANALOG_PINS[6] = { A0, A1, A2, A3, A4, A5 };

struct PinState {
  uint8_t  mode;
  int32_t  last;        // last value reported
  int32_t  pending;     // value waiting for debounce
  uint32_t pendSince;
  uint32_t lastReport;
  uint16_t interval;    // ms between ADC / counter reports
  uint16_t debounce;    // ms, digital inputs
};

struct LinkState {
  uint8_t  kind;
  uint8_t  addr;
  uint16_t pollMs;
  uint32_t lastPoll;
  uint8_t  len;
  char     line[LINE_MAX + 1];
};

static PinState P[NPIN];
static LinkState L[NLINK];
static volatile uint32_t CNT[NPIN];

Arduino_LED_Matrix matrix;
static uint8_t frame[104];

static int hwPin(int p) {
  if (p >= 0 && p <= 13) return p;
  if (p >= 14 && p <= 19) return ANALOG_PINS[p - 14];
  if (p >= 20 && p < NPIN) return p;
  return -1;
}

// --- pulse counter interrupt handlers, one per pin ---
template <int N> void cntIsr() { CNT[N]++; }
typedef void (*IsrFn)();
#define ISR10(b) cntIsr<b>, cntIsr<b + 1>, cntIsr<b + 2>, cntIsr<b + 3>, cntIsr<b + 4>, \
                 cntIsr<b + 5>, cntIsr<b + 6>, cntIsr<b + 7>, cntIsr<b + 8>, cntIsr<b + 9>
static IsrFn ISR_TABLE[NPIN] = { ISR10(0), ISR10(10), cntIsr<20>, cntIsr<21>, cntIsr<22>, cntIsr<23>, cntIsr<24> };

static void releasePin(int p) {
  int hp = hwPin(p);
  if (hp < 0) return;
  if (P[p].mode == M_CNT) detachInterrupt(digitalPinToInterrupt(hp));
  if (P[p].mode == M_DOUT || P[p].mode == M_PWM) digitalWrite(hp, LOW);
  if (P[p].mode != M_OFF) pinMode(hp, INPUT);
  P[p].mode = M_OFF;
}

// ---------------- RPC functions (Linux -> microcontroller) ----------------

int q_ver() { return QH_VERSION; }

int q_cfg(int p, int mode, int interval, int debounce) {
  int hp = hwPin(p);
  if (hp < 0) return -1;
  if (mode == M_DAC && !(p == 14 || p == 15)) return -2;   // DAC only on A0 / A1
  if (mode == M_ADC && !(p >= 14 && p <= 19)) return -2;   // ADC only on A0..A5
  releasePin(p);
  P[p].mode = mode;
  P[p].interval = interval < 20 ? 20 : interval;
  P[p].debounce = debounce < 0 ? 0 : debounce;
  P[p].lastReport = 0;
  P[p].last = -1;
  P[p].pending = -1;
  switch (mode) {
    case M_DIN:    pinMode(hp, INPUT); break;
    case M_DIN_PU: pinMode(hp, INPUT_PULLUP); break;
    case M_DIN_PD: pinMode(hp, INPUT_PULLDOWN); break;
    case M_DOUT:   pinMode(hp, OUTPUT); digitalWrite(hp, LOW); break;
    case M_PWM:    pinMode(hp, OUTPUT); analogWrite(hp, 0); break;
    case M_ADC:    break;
    case M_DAC:
#ifdef DAC0
      if (p == 14) analogWrite(DAC0, 0);
#endif
#ifdef DAC1
      if (p == 15) analogWrite(DAC1, 0);
#endif
      break;
    case M_CNT:
      pinMode(hp, INPUT_PULLUP);
      CNT[p] = 0;
      attachInterrupt(digitalPinToInterrupt(hp), ISR_TABLE[p], FALLING);
      break;
    default: P[p].mode = M_OFF; break;
  }
  return P[p].mode;
}

int q_dw(int p, int v) {
  int hp = hwPin(p);
  if (hp < 0 || P[p].mode != M_DOUT) return -1;
  digitalWrite(hp, v ? HIGH : LOW);
  return v ? 1 : 0;
}

// PWM / DAC value, always 0..4095
int q_aw(int p, int v) {
  int hp = hwPin(p);
  if (hp < 0) return -1;
  if (v < 0) v = 0;
  if (v > 4095) v = 4095;
  if (P[p].mode == M_PWM) { analogWrite(hp, v); return v; }
  if (P[p].mode == M_DAC) {
#ifdef DAC0
    if (p == 14) { analogWrite(DAC0, v); return v; }
#endif
#ifdef DAC1
    if (p == 15) { analogWrite(DAC1, v); return v; }
#endif
  }
  return -1;
}

int q_rd(int p) {
  int hp = hwPin(p);
  if (hp < 0) return -1;
  switch (P[p].mode) {
    case M_DIN: case M_DIN_PU: case M_DIN_PD: case M_DOUT: return digitalRead(hp);
    case M_ADC: return analogRead(hp);
    case M_CNT: return (int)CNT[p];
    default: return -1;
  }
}

// RGB LED 3 or 4. bits: 1 = red, 2 = green, 4 = blue (the LEDs are active-low)
int q_rgb(int led, int bits) {
  if (led == 3) {
    digitalWrite(LED3_R, (bits & 1) ? LOW : HIGH);
    digitalWrite(LED3_G, (bits & 2) ? LOW : HIGH);
    digitalWrite(LED3_B, (bits & 4) ? LOW : HIGH);
    return bits;
  }
  if (led == 4) {
    digitalWrite(LED4_R, (bits & 1) ? LOW : HIGH);
    digitalWrite(LED4_G, (bits & 2) ? LOW : HIGH);
    digitalWrite(LED4_B, (bits & 4) ? LOW : HIGH);
    return bits;
  }
  return -1;
}

// LED matrix frame: 104 characters '0'..'7', row by row (13 columns x 8 rows)
int q_mx(String f) {
  int n = f.length();
  for (int i = 0; i < 104; i++) {
    int c = (i < n) ? (f.charAt(i) - '0') : 0;
    frame[i] = (c < 0) ? 0 : (c > 7 ? 7 : c);
  }
  matrix.draw(frame);
  return n;
}

int q_reset() {
  for (int p = 0; p < NPIN; p++) releasePin(p);
  q_rgb(3, 0);
  q_rgb(4, 0);
  for (int i = 0; i < 104; i++) frame[i] = 0;
  matrix.draw(frame);
  return 1;
}

// ---------------- links to other boards ----------------

static TwoWire *busOf(int kind) { return kind == L_I2C_QWIIC ? &Wire1 : &Wire; }

int q_lopen(int id, int kind, int a, int b) {
  if (id < 0 || id >= NLINK) return -1;
  L[id].kind = L_NONE;
  L[id].len = 0;
  if (kind == L_UART) {
    Serial1.begin(a > 0 ? a : 115200);
  } else if (kind == L_I2C_WIRE || kind == L_I2C_QWIIC) {
    if (a < 8 || a > 119) return -2;
    busOf(kind)->begin();
    L[id].addr = (uint8_t)a;
    L[id].pollMs = b < 10 ? 10 : b;
    L[id].lastPoll = 0;
  } else {
    return -2;
  }
  L[id].kind = (uint8_t)kind;
  return 1;
}

int q_lclose(int id) {
  if (id < 0 || id >= NLINK) return -1;
  if (L[id].kind == L_UART) Serial1.end();
  L[id].kind = L_NONE;
  return 1;
}

int q_ltx(int id, String data) {
  if (id < 0 || id >= NLINK) return -1;
  int n = data.length();
  if (L[id].kind == L_UART) {
    Serial1.print(data);
    return n;
  }
  if (L[id].kind == L_I2C_WIRE || L[id].kind == L_I2C_QWIIC) {
    TwoWire *bus = busOf(L[id].kind);
    for (int i = 0; i < n; i += 30) {            // classic AVR Wire buffers hold 32 bytes
      bus->beginTransmission(L[id].addr);
      for (int k = i; k < n && k < i + 30; k++) bus->write((uint8_t)data.charAt(k));
      if (bus->endTransmission() != 0) return -3;
    }
    return n;
  }
  return -1;
}

static void linkChar(int id, char c) {
  LinkState &l = L[id];
  if (c == '\r') return;
  if (c == '\n') {
    if (l.len > 0) {
      l.line[l.len] = 0;
      Bridge.notify("q_lrx", id, String(l.line));
    }
    l.len = 0;
    return;
  }
  if (c < 32 || c > 126) return;                  // boot noise, padding
  if (l.len >= LINE_MAX) { l.len = 0; return; }
  l.line[l.len++] = c;
}

static void serviceLinks(uint32_t now) {
  for (int id = 0; id < NLINK; id++) {
    LinkState &l = L[id];
    if (l.kind == L_UART) {
      int budget = 256;
      while (Serial1.available() && budget-- > 0) linkChar(id, (char)Serial1.read());
    } else if (l.kind == L_I2C_WIRE || l.kind == L_I2C_QWIIC) {
      if (now - l.lastPoll < l.pollMs) continue;
      l.lastPoll = now;
      TwoWire *bus = busOf(l.kind);
      int got = bus->requestFrom((int)l.addr, 32);
      while (got-- > 0 && bus->available()) linkChar(id, (char)bus->read());
    }
  }
}

// ---- start banner on the Serial Monitor (the text comes from Linux: q_info) ----
// The microcontroller cannot see a monitor being opened later, so the banner is repeated
// every INFO_EVERY_MS and whenever a key is typed in the monitor.
//
// Cost: `if (Monitor)` is one blocking RPC to the router (mon/connected) for as long as no monitor
// has ever been attached, which is the normal state of a running board. In that state it is
// therefore asked once per INFO_EVERY_MS and never more often. Once a monitor has been attached
// the answer is cached (Monitor.is_connected(), no RPC) and new text or a key press is printed at
// once.
static char infoText[200];
static volatile bool infoDirty = false;
static uint32_t infoLast = 0, monPoll = 0;
#ifndef INFO_EVERY_MS
  #define INFO_EVERY_MS 30000UL
#endif

int q_info(String t) {                // Bridge handler: store only, never print here
  strncpy(infoText, t.c_str(), sizeof(infoText) - 1);
  infoText[sizeof(infoText) - 1] = 0;
  infoDirty = true;
  return (int)strlen(infoText);
}

static void serviceInfo(uint32_t now) {         // called from loop()
  if (!infoText[0]) {                           // Linux has not told us yet
    if (now - infoLast >= INFO_EVERY_MS) { infoLast = now; if (Monitor) Monitor.println("QHome: waiting for the Linux side..."); }
    return;
  }
  bool due = now - infoLast >= INFO_EVERY_MS;   // the only reason to ask while nobody ever attached
  if (Monitor.is_connected()) {                 // cached answer: costs nothing
    if (now - monPoll >= 500) {                 // any key typed in the monitor asks for the banner
      monPoll = now;
      while (Monitor.available() > 0) { Monitor.read(); due = true; }
    }
    if (infoDirty) due = true;                  // new text: print it at once
  }
  if (!due) return;                             // infoDirty stays set until the text was printed
  infoLast = now;
  if (Monitor) {                                // at most one RPC per INFO_EVERY_MS (see above)
    infoDirty = false;
    Monitor.println();
    Monitor.println("=== QHome ===");
    Monitor.println(infoText);
    Monitor.println("(press any key to show this again)");
  }
}

// ---------------- setup / loop ----------------

void setup() {
  analogReadResolution(14);
  analogWriteResolution(12);
  for (int p = 0; p < NPIN; p++) { P[p].mode = M_OFF; CNT[p] = 0; }
  for (int i = 0; i < NLINK; i++) { L[i].kind = L_NONE; L[i].len = 0; }

  pinMode(LED3_R, OUTPUT); pinMode(LED3_G, OUTPUT); pinMode(LED3_B, OUTPUT);
  pinMode(LED4_R, OUTPUT); pinMode(LED4_G, OUTPUT); pinMode(LED4_B, OUTPUT);
  q_rgb(3, 0);
  q_rgb(4, 0);

  matrix.begin();
  matrix.setGrayscaleBits(3);
  for (int i = 0; i < 104; i++) frame[i] = 0;
  matrix.draw(frame);

  Bridge.begin();
  Monitor.begin();                     // never use Monitor inside a Bridge handler (it makes Bridge calls)
  Bridge.provide_safe("q_ver", q_ver);
  Bridge.provide_safe("q_cfg", q_cfg);
  Bridge.provide_safe("q_dw", q_dw);
  Bridge.provide_safe("q_aw", q_aw);
  Bridge.provide_safe("q_rd", q_rd);
  Bridge.provide_safe("q_rgb", q_rgb);
  Bridge.provide_safe("q_mx", q_mx);
  Bridge.provide_safe("q_reset", q_reset);
  Bridge.provide_safe("q_lopen", q_lopen);
  Bridge.provide_safe("q_lclose", q_lclose);
  Bridge.provide_safe("q_ltx", q_ltx);
  Bridge.provide_safe("q_info", q_info);

  // Tell Linux "I restarted": it sends the whole setup again.
  Bridge.notify("q_boot", QH_VERSION);
}

void loop() {
  uint32_t now = millis();
  for (int p = 0; p < NPIN; p++) {
    PinState &s = P[p];
    if (s.mode == M_OFF || s.mode == M_DOUT || s.mode == M_PWM || s.mode == M_DAC) continue;
    int hp = hwPin(p);
    switch (s.mode) {
      case M_DIN: case M_DIN_PU: case M_DIN_PD: {
        int v = digitalRead(hp);
        if (v != s.pending) { s.pending = v; s.pendSince = now; }
        if (s.pending != s.last && (now - s.pendSince) >= s.debounce) {
          s.last = s.pending;
          Bridge.notify("q_ev", p, (int)s.last);
        }
        break;
      }
      case M_ADC:
        if (now - s.lastReport >= s.interval) {
          s.lastReport = now;
          Bridge.notify("q_ev", p, analogRead(hp));
        }
        break;
      case M_CNT:
        if (now - s.lastReport >= s.interval) {
          s.lastReport = now;
          Bridge.notify("q_ev", p, (int)CNT[p]);
        }
        break;
      default: break;
    }
  }
  serviceLinks(now);
  serviceInfo(now);
  delay(2);
}
