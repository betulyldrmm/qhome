// QHome satellite firmware: turns an Arduino UNO R3, Nano, Mega 2560, UNO R4 Minima,
// UNO R4 WiFi, Nano R4, ESP32 DevKit V1, ESP32-C3 Super Mini or ESP8266 NodeMCU into remote
// pins for a QHome master (UNO Q or PC).
//
// Pin numbers are the Arduino pin numbers; on the ESP boards the GPIO numbers (NodeMCU: D1 is
// GPIO5 and so on, A0 is 17). Pins that would crash the chip (the flash pins of the ESP
// boards) are refused, whatever the master asks for.
//
// Upload once. The master decides what every pin does and changes it live; this sketch
// never needs editing again unless you change how the board is connected (config.h).
//
// QLink protocol: short text lines, newline terminated.
//   master -> board   H                      hello            -> h <proto> <model> <boot>
//                     P                      ping             -> p <boot>
//                     C <pin> <mode> <interval_ms> <debounce_ms>  -> c <pin> <mode or error>
//                     D <pin> <0|1>          digital write
//                     A <pin> <0..4095>      PWM / DAC write
//                     R                      release all pins -> r 1
//   board -> master   E <pin> <value>        input changed / periodic reading
//                     B <boot>               the board just started
// Modes: 0 off, 1 input, 2 input pull-up, 3 input pull-down (plain input where the chip has none),
//        4 output, 5 PWM, 6 analog input, 7 DAC, 8 pulse counter (interrupt pins only)
// Errors in the reply to C: -1 no such pin here (or it carries the link), -2 the pin cannot do
//        that, -3 no counter or PWM channel left

#include "config.h"

#define QL_PROTO 1
enum { M_OFF = 0, M_DIN = 1, M_DIN_PU = 2, M_DIN_PD = 3, M_DOUT = 4,
       M_PWM = 5, M_ADC = 6, M_DAC = 7, M_CNT = 8 };

// ---------------- board facts ----------------
#if defined(ARDUINO_ARCH_ESP8266)
  #define QL_MODEL "esp8266"
  #define QL_ESP 1
  #define QL_ESP8266 1
#elif defined(ARDUINO_ARCH_ESP32)
  #define QL_ESP 1
  #if CONFIG_IDF_TARGET_ESP32C3
    #define QL_MODEL "esp32c3"
    #define QL_ESP32C3 1
  #elif CONFIG_IDF_TARGET_ESP32
    #define QL_MODEL "esp32"
    #define QL_ESP32 1
  #else
    #error "QHome satellite: this ESP32 variant has no pin table yet"
  #endif
#elif defined(ARDUINO_NANO_R4) || defined(ARDUINO_NANOR4)   // the core also defines ARDUINO_UNOR4_MINIMA: test first
  #define QL_MODEL "nanor4"
  #define QL_R4 1
#elif defined(ARDUINO_UNOR4_WIFI)
  #define QL_MODEL "r4w"
  #define QL_R4 1
#elif defined(ARDUINO_UNOR4_MINIMA)
  #define QL_MODEL "r4m"
  #define QL_R4 1
#elif defined(__AVR_ATmega2560__)
  #define QL_MODEL "mega"
#elif defined(NUM_ANALOG_INPUTS) && (NUM_ANALOG_INPUTS > 6)
  #define QL_MODEL "nano"
#else
  #define QL_MODEL "uno"
#endif

#if QL_LINK == QL_I2C && defined(QL_ESP)
  #error "I2C link is not supported on ESP boards; use USB, UART or Wi-Fi"
#endif
#if QL_LINK == QL_WIFI && !defined(QL_ESP) && !defined(ARDUINO_UNOR4_WIFI)
  #error "This board has no Wi-Fi; pick another QL_LINK"
#endif

#ifndef IRAM_ATTR                      // ESP interrupt handlers must live in RAM
  #if defined(ICACHE_RAM_ATTR)         // ESP8266 core 2.x name
    #define IRAM_ATTR ICACHE_RAM_ATTR
  #else
    #define IRAM_ATTR
  #endif
#endif
#ifndef NOT_AN_INTERRUPT
  #define NOT_AN_INTERRUPT -1
#endif

// Per model: number of pin slots, pulse counters, and what each pin can do.
//   QL_VALID    the pin exists on the header and is safe to touch
//   QL_HAS_ADC  analog input          QL_HAS_PWM  PWM output       QL_HAS_INT  pulse counter
//   QL_CAN_OUT  can drive a level     QL_HAS_PULL has an internal pull resistor
//   QL_ADC_ONLY not a GPIO at all     QL_PWM_MAX  PWM pins at the same time (0 = no limit)
#define QB(n) (1ULL << (n))
#if defined(QL_ESP32)
  // GPIO 0 is the BOOT button, 6-11 the flash, 20/24/28-31/37/38 are not on the module.
  // 34, 35, 36 (VP), 39 (VN) are inputs only, without pull resistors. Analog only on ADC1
  // (32-39): the other ADC pins stop working while Wi-Fi is on.
  #define NPIN 40
  #define NCNT 6
  #define QL_PINMASK (QB(1) | QB(2) | QB(3) | QB(4) | QB(5) | QB(12) | QB(13) | QB(14) | QB(15) | \
                      QB(16) | QB(17) | QB(18) | QB(19) | QB(21) | QB(22) | QB(23) | QB(25) | QB(26) | \
                      QB(27) | QB(32) | QB(33) | QB(34) | QB(35) | QB(36) | QB(39))
  #if QL_PINMASK != 0x0000009F0EEFF03EULL
    #error "ESP32 pin list and its check value differ"
  #endif
  #define QL_VALID(p)    ((QL_PINMASK >> (p)) & 1ULL)
  #define QL_HAS_ADC(p)  ((p) >= 32)
  #define QL_CAN_OUT(p)  ((p) < 34)
  #define QL_HAS_PULL(p) ((p) < 34)
  #define QL_HAS_PWM(p)  ((p) < 34)
  #define QL_HAS_INT(p)  ((p) < 34)
  #define QL_ADC_ONLY(p) 0
  #define QL_PWM_MAX 16
#elif defined(QL_ESP32C3)
  // GPIO 11 is a supply pin, 12-17 the flash, 18/19 the USB port.
  #define NPIN 22
  #define NCNT 6
  #define QL_PINMASK (QB(0) | QB(1) | QB(2) | QB(3) | QB(4) | QB(5) | QB(6) | QB(7) | QB(8) | QB(9) | \
                      QB(10) | QB(20) | QB(21))
  #if QL_PINMASK != 0x3007FFULL
    #error "ESP32-C3 pin list and its check value differ"
  #endif
  #define QL_VALID(p)    ((QL_PINMASK >> (p)) & 1ULL)
  #define QL_HAS_ADC(p)  ((p) <= 4)
  #define QL_CAN_OUT(p)  1
  #define QL_HAS_PULL(p) 1
  #define QL_HAS_PWM(p)  1
  #define QL_HAS_INT(p)  1
  #define QL_ADC_ONLY(p) 0
  #define QL_PWM_MAX 6
#elif defined(QL_ESP8266)
  // GPIO 6-11 are the flash. 16 (D0) has no pull-up, interrupt or PWM. 17 is A0: analog only.
  #define NPIN 18
  #define NCNT 6
  #define QL_PINMASK (QB(0) | QB(1) | QB(2) | QB(3) | QB(4) | QB(5) | QB(12) | QB(13) | QB(14) | QB(15) | \
                      QB(16) | QB(17))
  #if QL_PINMASK != 0x3F03FULL
    #error "ESP8266 pin list and its check value differ"
  #endif
  #define QL_VALID(p)    ((QL_PINMASK >> (p)) & 1ULL)
  #define QL_HAS_ADC(p)  ((p) == 17)
  #define QL_CAN_OUT(p)  ((p) != 17)
  #define QL_HAS_PULL(p) ((p) < 16)
  #define QL_HAS_PWM(p)  ((p) < 16)
  #define QL_HAS_INT(p)  ((p) < 16)
  #define QL_ADC_ONLY(p) ((p) == 17)
  #define QL_PWM_MAX 0
#else
  #if defined(__AVR_ATmega2560__)
    #define NPIN 70
    #define NCNT 6
  #else
    #define NPIN 22
    #define NCNT 2
  #endif
  #define QL_VALID(p)    1
  #define QL_HAS_ADC(p)  ((p) >= A0)
  #define QL_CAN_OUT(p)  1
  #define QL_HAS_PULL(p) 1
  #define QL_ADC_ONLY(p) 0
  #define QL_PWM_MAX 0
  #if defined(QL_R4)
    #define QL_HAS_PWM(p) ((p) == 3 || (p) == 5 || (p) == 6 || (p) == 9 || (p) == 10 || (p) == 11)
    #define QL_HAS_INT(p) ((p) == 2 || (p) == 3)
  #else
    #define QL_HAS_PWM(p) digitalPinHasPWM(p)
    #define QL_HAS_INT(p) (digitalPinToInterrupt(p) != NOT_AN_INTERRUPT)
  #endif
#endif

// The serial port that carries the link, how to start it, and the two pins it occupies
// (-1 = none: the USB port of that board has no header pins).
#if QL_LINK == QL_USB || QL_LINK == QL_UART
  #if defined(QL_ESP32)
    #if QL_LINK == QL_UART
      #define LINK_SERIAL Serial2                // RX2/TX2
      #define LINK_BEGIN() Serial2.begin(QL_BAUD, SERIAL_8N1, 16, 17)
      #define LINK_RX 16
      #define LINK_TX 17
    #else
      #define LINK_SERIAL Serial                 // the USB bridge sits on GPIO3/GPIO1
      #define LINK_RX 3
      #define LINK_TX 1
    #endif
  #elif defined(QL_ESP32C3)
    #if QL_LINK == QL_UART
      #if defined(ARDUINO_USB_CDC_ON_BOOT) && ARDUINO_USB_CDC_ON_BOOT == 1
        #define LINK_SERIAL Serial0              // Serial is the USB port, Serial0 the pins
      #else
        #define LINK_SERIAL Serial
      #endif
      #define LINK_BEGIN() LINK_SERIAL.begin(QL_BAUD, SERIAL_8N1, 20, 21)
      #define LINK_RX 20
      #define LINK_TX 21
    #else
      #if !defined(ARDUINO_USB_CDC_ON_BOOT) || ARDUINO_USB_CDC_ON_BOOT != 1
        #error "Tools > USB CDC On Boot must be Enabled for a USB link"
      #endif
      #define LINK_SERIAL Serial                 // native USB: no header pin is used
      #define LINK_RX -1
      #define LINK_TX -1
    #endif
  #elif defined(QL_ESP8266)
    #define LINK_SERIAL Serial                   // USB and the RX/TX pins are the same UART
    #define LINK_RX 3
    #define LINK_TX 1
  #elif defined(QL_R4)
    #if QL_LINK == QL_UART
      #define LINK_SERIAL Serial1                // R4: D0/D1 are a separate UART
      #define LINK_RX 0
      #define LINK_TX 1
    #else
      #define LINK_SERIAL Serial                 // native USB
      #define LINK_RX -1
      #define LINK_TX -1
    #endif
  #else
    #define LINK_SERIAL Serial                   // classic boards: USB shares D0/D1
    #define LINK_RX 0
    #define LINK_TX 1
  #endif
  #ifndef LINK_BEGIN
    #define LINK_BEGIN() LINK_SERIAL.begin(QL_BAUD)
  #endif
#endif
#if QL_LINK == QL_I2C
  #include <Wire.h>
#endif
#if QL_LINK == QL_WIFI
  #if defined(ARDUINO_ARCH_ESP32)
    #include <WiFi.h>
  #elif defined(ARDUINO_ARCH_ESP8266)
    #include <ESP8266WiFi.h>
  #else
    #include <WiFiS3.h>
  #endif
#endif
#if defined(ARDUINO_ARCH_ESP32) && defined(__has_include)
  #if __has_include(<esp_random.h>)
    #include <esp_random.h>                      // esp_random() moved here in newer cores
  #elif __has_include(<esp_system.h>)
    #include <esp_system.h>
  #endif
#endif

struct PinState {
  uint8_t  mode;
  uint8_t  last;       // last reported level (2 = not reported yet)
  uint8_t  pending;
  uint8_t  slot;       // counter slot; PWM on an ESP32 core 2.x: LEDC channel
  uint16_t interval;
  uint16_t debounce;
  uint32_t t;          // debounce start or last report time
};
static PinState P[NPIN];
static volatile uint32_t CNT[NCNT];
static int8_t cntPin[NCNT];
static uint8_t pwmCount;               // pins in PWM mode right now

// PWM on ESP32 / ESP32-C3 goes through the chip's LEDC channels (16 / 6 of them: QL_PWM_MAX).
// Core 3.x: analogWrite() takes a channel when a pin needs one and pinMode() gives it back, so the
// plain Arduino calls are right. Core 2.x does neither: its analogWrite() keeps a pin's channel
// until reset (after 16 / 6 different pins no pin gets PWM any more) and, up to 2.0.8, does not
// connect the pin again once pinMode() was called on it. On those cores this sketch therefore
// owns the channels itself: one per PWM pin, attached in configure() and given back in releasePin().
#if defined(ARDUINO_ARCH_ESP32) && (!defined(ESP_ARDUINO_VERSION_MAJOR) || ESP_ARDUINO_VERSION_MAJOR < 3)
  #define QL_LEDC2 1
static uint16_t ledcBusy;              // bit n: LEDC channel n drives a pin (PinState.slot = n)
#endif
static uint16_t bootId;

static void IRAM_ATTR isr0() { CNT[0]++; }
static void IRAM_ATTR isr1() { CNT[1]++; }
#if NCNT > 2
static void IRAM_ATTR isr2() { CNT[2]++; }
static void IRAM_ATTR isr3() { CNT[3]++; }
static void IRAM_ATTR isr4() { CNT[4]++; }
static void IRAM_ATTR isr5() { CNT[5]++; }
static void (*const ISRS[NCNT])() = { isr0, isr1, isr2, isr3, isr4, isr5 };
#else
static void (*const ISRS[NCNT])() = { isr0, isr1 };
#endif

// ---------------- output: one line to the master ----------------
#if QL_LINK == QL_I2C
// The master polls us: it reads 32 bytes at a time out of this ring (zero = nothing).
#define TXN 128
#define RXN 64
static volatile uint8_t txBuf[TXN], rxBuf[RXN];
static volatile uint8_t txHead, txTail, rxHead, rxTail;

static void i2cReceive(int n) {
  while (Wire.available()) {
    uint8_t c = Wire.read(), nx = (rxHead + 1) % RXN;
    if (nx != rxTail) { rxBuf[rxHead] = c; rxHead = nx; }
  }
}
static void i2cRequest() {
  uint8_t out[32];
  for (uint8_t i = 0; i < 32; i++) {
    if (txTail != txHead) { out[i] = txBuf[txTail]; txTail = (txTail + 1) % TXN; }
    else out[i] = 0;
  }
  Wire.write(out, 32);
}
static void outLine(const char *s) {
  noInterrupts();
  uint8_t used = (uint8_t)((txHead + TXN - txTail) % TXN);
  uint8_t need = (uint8_t)strlen(s) + 1;
  if (need < TXN - used) {                       // drop the line if the ring is full
    for (const char *p = s; *p; p++) { txBuf[txHead] = *p; txHead = (txHead + 1) % TXN; }
    txBuf[txHead] = '\n'; txHead = (txHead + 1) % TXN;
  }
  interrupts();
}
#elif QL_LINK == QL_WIFI
static void mqttPublish(const char *topic, const char *payload, bool retain);
static char topicUp[48], topicDown[48], topicStatus[48];
static void outLine(const char *s) { mqttPublish(topicUp, s, false); }
#else
static void outLine(const char *s) { LINK_SERIAL.println(s); }
#endif

static void out2(char k, long a, long b) {
  char buf[32];
  snprintf(buf, sizeof(buf), "%c %ld %ld", k, a, b);
  outLine(buf);
}
static void outBoot(char k) {
  char buf[32];
  if (k == 'h') snprintf(buf, sizeof(buf), "h %d %s %04x", QL_PROTO, QL_MODEL, bootId);
  else snprintf(buf, sizeof(buf), "%c %04x", k, bootId);
  outLine(buf);
}

// ---------------- pins ----------------
static bool linkPin(int p) {
#if QL_LINK == QL_I2C
  return p == SDA || p == SCL;
#elif QL_LINK == QL_WIFI
  return false;
#else
  return p == LINK_RX || p == LINK_TX;
#endif
}

// PWM with 8-bit duty (every board but the R4s, which write 12 bit through analogWrite()).
static int pwmStart(int p) {             // 0 = running at duty 0, -3 = the chip has no channel left
#if QL_PWM_MAX
  if (pwmCount >= QL_PWM_MAX) return -3;
#endif
  pinMode(p, OUTPUT);
#if defined(QL_LEDC2)
  uint8_t ch = 0;
  while (ch < QL_PWM_MAX && (ledcBusy & (1u << ch))) ch++;
  if (ch >= QL_PWM_MAX || ledcSetup(ch, 1000, 8) == 0) { pinMode(p, INPUT); return -3; }
  ledcAttachPin(p, ch);                  // after pinMode(): that call hands the pin back to plain GPIO
  ledcWrite(ch, 0);
  ledcBusy |= (uint16_t)(1u << ch);
  P[p].slot = ch;
#else
  analogWrite(p, 0);
#endif
  pwmCount++;
  return 0;
}
static void pwmWrite(int p, int duty) {  // duty 0..255
#if defined(QL_LEDC2)
  ledcWrite(P[p].slot, (uint32_t)duty);
#else
  analogWrite(p, duty);
#endif
}
static void pwmStop(int p) {             // the caller drives the pin LOW and makes it an input
#if defined(QL_LEDC2)
  ledcWrite(P[p].slot, 0);
  ledcDetachPin(p);
  ledcBusy &= (uint16_t)~(1u << P[p].slot);
#endif
  if (pwmCount > 0) pwmCount--;
}

static void releasePin(int p) {
  PinState &s = P[p];
  if (s.mode == M_OFF) return;
  if (s.mode == M_CNT) { detachInterrupt(digitalPinToInterrupt(p)); cntPin[s.slot] = -1; }
  if (s.mode == M_PWM) pwmStop(p);
  if (s.mode == M_DOUT || s.mode == M_PWM) digitalWrite(p, LOW);
#if defined(QL_ESP32)
  if (s.mode == M_DAC) dacDisable(p);
#endif
  if (s.mode != M_ADC) pinMode(p, INPUT);
  s.mode = M_OFF;
}

static int configure(int p, int mode, long interval, long debounce) {
  if (p < 0 || p >= NPIN || !QL_VALID(p) || linkPin(p)) return -1;   // also keeps pinMode() off the flash pins
  releasePin(p);
  PinState &s = P[p];
  s.interval = interval < 20 ? 20 : (interval > 60000 ? 60000 : (uint16_t)interval);
  s.debounce = debounce < 0 ? 0 : (debounce > 60000 ? 60000 : (uint16_t)debounce);
  s.last = 2; s.pending = 2; s.t = 0;
  if (mode == M_OFF) return 0;
  if (QL_ADC_ONLY(p) && mode != M_ADC) return -2;
  if (!QL_CAN_OUT(p) && (mode == M_DOUT || mode == M_PWM || mode == M_DAC || mode == M_CNT)) return -2;
  switch (mode) {
    case M_DIN: pinMode(p, INPUT); break;
    case M_DIN_PU:
      if (QL_HAS_PULL(p)) pinMode(p, INPUT_PULLUP);
      else { pinMode(p, INPUT); mode = M_DIN; }  // no resistor in the chip on this pin: use an external one
      break;
    case M_DIN_PD:
#if defined(INPUT_PULLDOWN)
      if (QL_HAS_PULL(p)) { pinMode(p, INPUT_PULLDOWN); break; }
#endif
      pinMode(p, INPUT); mode = M_DIN;           // no pull-down in the chip: use an external resistor
      break;
    case M_DOUT: pinMode(p, OUTPUT); digitalWrite(p, LOW); break;
    case M_PWM:
      if (!QL_HAS_PWM(p)) return -2;
      if (pwmStart(p) < 0) return -3;                            // the chip has no PWM channel left
      break;
    case M_ADC:
      if (!QL_HAS_ADC(p)) return -2;
      break;
    case M_DAC:
#if defined(QL_R4)
      if (p != DAC) return -2;
      analogWrite(DAC, 0); break;
#elif defined(QL_ESP32)
      if (p != 25 && p != 26) return -2;
      dacWrite(p, 0); break;
#else
      return -2;
#endif
    case M_CNT: {
      if (!QL_HAS_INT(p)) return -2;
      int slot = -1;
      for (int i = 0; i < NCNT; i++) if (cntPin[i] < 0) { slot = i; break; }
      if (slot < 0) return -3;
      cntPin[slot] = p; s.slot = slot;
      noInterrupts(); CNT[slot] = 0; interrupts();
      pinMode(p, INPUT_PULLUP);
      attachInterrupt(digitalPinToInterrupt(p), ISRS[slot], FALLING);
      break;
    }
    default: return -2;
  }
  s.mode = mode;
  return mode;
}

// One analog reading in the counts the master expects (qh_boards: adc_max at vref).
static long readAnalog(int p) {
#if defined(ARDUINO_ARCH_ESP32)
  long v = (long)analogReadMilliVolts(p) * 4095L / 3300;         // factory calibrated; 4095 = 3.3 V
  return v > 4095 ? 4095 : v;
#elif defined(QL_ESP8266)
  long v = analogRead(A0);                                       // the core can return 1024
  return v > 1023 ? 1023 : v;
#else
  return analogRead(p);
#endif
}

static void handleLine(char *line) {
  char k = line[0];
  char *q = line + 1;
  long a[4] = { 0, 0, 0, 0 };
  for (int i = 0; i < 4; i++) a[i] = strtol(q, &q, 10);
  switch (k) {
    case 'H': outBoot('h'); break;
    case 'P': outBoot('p'); break;
    case 'C': out2('c', a[0], configure((int)a[0], (int)a[1], a[2], a[3])); break;
    case 'D':
      if (a[0] >= 0 && a[0] < NPIN && P[a[0]].mode == M_DOUT) digitalWrite((int)a[0], a[1] ? HIGH : LOW);
      break;
    case 'A': {
      if (a[0] < 0 || a[0] >= NPIN) break;
      long v = a[1] < 0 ? 0 : (a[1] > 4095 ? 4095 : a[1]);
      uint8_t m = P[a[0]].mode;
#if defined(QL_R4)
      if (m == M_PWM || m == M_DAC) analogWrite((int)a[0], (int)v);       // 12-bit set in setup()
#else
      if (m == M_PWM) pwmWrite((int)a[0], (int)(v >> 4));                 // 8 bit on AVR and ESP
  #if defined(QL_ESP32)
      if (m == M_DAC) dacWrite((int)a[0], (int)(v >> 4));                 // 8-bit DAC on GPIO25/26
  #endif
#endif
      break;
    }
    case 'R':
      for (int p = 0; p < NPIN; p++) releasePin(p);
      outLine("r 1");
      break;
    default: break;                              // unknown or noise: ignore
  }
}

static char inBuf[40];
static uint8_t inLen;
static void feedChar(char c) {
  if (c == '\r') return;
  if (c == '\n') {
    inBuf[inLen] = 0;
    if (inLen > 0) handleLine(inBuf);
    inLen = 0;
    return;
  }
  if (inLen < sizeof(inBuf) - 1) inBuf[inLen++] = c;
  else inLen = 0;                                // too long for us (for example a matrix frame)
}

// ---------------- Wi-Fi + minimal MQTT 3.1.1 client (UNO R4 WiFi, ESP32, ESP32-C3, ESP8266) ----------------
#if QL_LINK == QL_WIFI
static WiFiClient net;
static bool mqttUp;
static uint32_t lastPing, lastTry;
#if defined(QL_ESP)
static uint32_t wifiSeen;              // last time Wi-Fi was up, or the last WiFi.begin()
  #ifndef QL_WIFI_REJOIN_MS
    #define QL_WIFI_REJOIN_MS 20000UL  // the ESP cores rejoin by themselves; begin() again only after this
  #endif
#endif

static void putStr(uint8_t *b, int &n, const char *s) {
  int l = strlen(s);
  b[n++] = l >> 8; b[n++] = l & 0xFF;
  memcpy(b + n, s, l); n += l;
}
static void sendPacket(uint8_t head, const uint8_t *body, int n) {
  uint8_t h[3]; int hn = 0;
  h[hn++] = head;
  if (n > 127) { h[hn++] = (n & 0x7F) | 0x80; h[hn++] = n >> 7; } else h[hn++] = n;
  net.write(h, hn);
  net.write(body, n);
}
static void mqttPublish(const char *topic, const char *payload, bool retain) {
  if (!mqttUp) return;
  uint8_t b[160]; int n = 0;
  if (strlen(topic) + strlen(payload) + 2 > sizeof(b)) return;
  putStr(b, n, topic);
  int l = strlen(payload);
  memcpy(b + n, payload, l); n += l;
  sendPacket(0x30 | (retain ? 1 : 0), b, n);
}
static bool mqttConnect() {
  if (!net.connect(QL_MASTER_HOST, QL_MASTER_PORT)) return false;
#if defined(QL_ESP)
  net.setNoDelay(true);                          // every MQTT packet leaves at once
#endif
  uint8_t b[200]; int n = 0;
  uint8_t flags = 0x02 | 0x04 | 0x20;            // clean session, will, will retain
  if (strlen(QL_MQTT_USER)) flags |= 0x80;
  if (strlen(QL_MQTT_PASS)) flags |= 0x40;
  putStr(b, n, "MQTT");
  b[n++] = 4; b[n++] = flags; b[n++] = 0; b[n++] = 30;                    // keep-alive 30 s
  putStr(b, n, "qhome-" QL_BOARD_ID);
  putStr(b, n, topicStatus);
  putStr(b, n, "offline");
  if (flags & 0x80) putStr(b, n, QL_MQTT_USER);
  if (flags & 0x40) putStr(b, n, QL_MQTT_PASS);
  sendPacket(0x10, b, n);
  uint32_t t0 = millis();
  while (net.available() < 4 && millis() - t0 < 5000) delay(10);
  if (net.available() < 4) { net.stop(); return false; }
  uint8_t ack[4];
  for (int i = 0; i < 4; i++) ack[i] = net.read();
  if (ack[0] != 0x20 || ack[3] != 0) { net.stop(); return false; }
  n = 0;
  b[n++] = 0; b[n++] = 1;                        // packet id
  putStr(b, n, topicDown);
  b[n++] = 0;                                    // QoS 0
  sendPacket(0x82, b, n);
  mqttUp = true;
  lastPing = millis();
  mqttPublish(topicStatus, "online", true);
  outBoot('B');
  return true;
}
static void mqttLoop() {
  uint32_t now = millis();
  bool wifiUp = WiFi.status() == WL_CONNECTED;
#if defined(QL_ESP)
  if (wifiUp) wifiSeen = now;
#endif
  if (!wifiUp || !net.connected()) {
    if (mqttUp) { mqttUp = false; net.stop(); }  // start a fresh MQTT session once the network is back
    if (now - lastTry < 3000 && lastTry) return;
    lastTry = now;
    if (!wifiUp) {
#if defined(QL_ESP)
      // begin() returns at once on ESP and every call restarts the join: do not repeat it quickly
      if (now - wifiSeen >= QL_WIFI_REJOIN_MS) { wifiSeen = now; WiFi.begin(QL_WIFI_SSID, QL_WIFI_PASS); }
#else
      WiFi.begin(QL_WIFI_SSID, QL_WIFI_PASS);    // WiFiS3: blocks until joined or timed out
#endif
      return;
    }
    net.stop();
    mqttConnect();
    return;
  }
  while (net.available() >= 2) {
    uint8_t head = net.read();
    long len = 0; int shift = 0; uint8_t d;
    do { d = net.read(); len |= (long)(d & 0x7F) << shift; shift += 7; } while ((d & 0x80) && shift < 21);
    uint32_t t0 = millis();
    while (net.available() < len && millis() - t0 < 500) delay(1);
    if ((head & 0xF0) == 0x30 && len >= 2) {     // PUBLISH (QoS 0): topic, then our QLink lines
      int tl = (net.read() << 8) | net.read();
      len -= 2;
      while (tl-- > 0 && len-- > 0) net.read();
      while (len-- > 0) feedChar((char)net.read());
      feedChar('\n');
    } else {
      while (len-- > 0) net.read();              // SUBACK, PINGRESP
    }
  }
  if (now - lastPing > 15000) {
    lastPing = now;
    uint8_t none = 0;
    sendPacket(0xC0, &none, 0);
  }
}
#endif

// ---------------- setup / loop ----------------
void setup() {
  for (int i = 0; i < NCNT; i++) cntPin[i] = -1;
#if defined(ARDUINO_ARCH_ESP32)
  bootId = (uint16_t)esp_random();
#elif defined(QL_ESP8266)
  bootId = (uint16_t)(RANDOM_REG32 ^ micros());
  analogWriteRange(255);                         // 8-bit PWM on every core version
#else
  bootId = (uint16_t)(analogRead(A0) * 31 + micros());
#endif
#if defined(QL_R4)
  analogReadResolution(14);
  analogWriteResolution(12);
#endif
#if QL_LINK == QL_I2C
  Wire.begin(QL_I2C_ADDRESS);
  #if !QL_I2C_PULLUPS && defined(__AVR__)
  digitalWrite(SDA, LOW);                        // Wire.begin() switched the 5 V pull-ups on
  digitalWrite(SCL, LOW);
  #endif
  Wire.onReceive(i2cReceive);
  Wire.onRequest(i2cRequest);
  outBoot('B');
#elif QL_LINK == QL_WIFI
  snprintf(topicUp, sizeof(topicUp), "qlink/%s/up", QL_BOARD_ID);
  snprintf(topicDown, sizeof(topicDown), "qlink/%s/down", QL_BOARD_ID);
  snprintf(topicStatus, sizeof(topicStatus), "qlink/%s/status", QL_BOARD_ID);
  #if defined(QL_ESP)
    #if defined(QL_ESP8266)
  WiFi.persistent(false);                        // do not wear the flash with the credentials
    #endif
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
    #if defined(ARDUINO_ARCH_ESP32)
  WiFi.setSleep(false);                          // lower command latency
    #endif
  WiFi.begin(QL_WIFI_SSID, QL_WIFI_PASS);        // once: the core keeps trying by itself
  wifiSeen = millis();
  #endif
#else
  LINK_BEGIN();
  outBoot('B');
#endif
}

void loop() {
#if QL_LINK == QL_I2C
  while (rxTail != rxHead) {
    noInterrupts();
    char c = (char)rxBuf[rxTail]; rxTail = (rxTail + 1) % RXN;
    interrupts();
    feedChar(c);
  }
#elif QL_LINK == QL_WIFI
  mqttLoop();
#else
  while (LINK_SERIAL.available()) feedChar((char)LINK_SERIAL.read());
#endif

  uint32_t now = millis();
  for (int p = 0; p < NPIN; p++) {
    PinState &s = P[p];
    switch (s.mode) {
      case M_DIN: case M_DIN_PU: case M_DIN_PD: {
        uint8_t v = digitalRead(p) ? 1 : 0;
        if (v != s.pending) { s.pending = v; s.t = now; }
        if (s.pending != s.last && (now - s.t) >= s.debounce) {
          s.last = s.pending;
          out2('E', p, s.last);
        }
        break;
      }
      case M_ADC:
        if (now - s.t >= s.interval) { s.t = now; out2('E', p, readAnalog(p)); }
        break;
      case M_CNT:
        if (now - s.t >= s.interval) {
          s.t = now;
          noInterrupts(); uint32_t c = CNT[s.slot]; interrupts();
          out2('E', p, (long)c);
        }
        break;
      default: break;
    }
  }
}
