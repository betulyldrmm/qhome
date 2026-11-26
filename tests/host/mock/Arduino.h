// Minimal stand-in for the Arduino core so the sketches can be compiled and exercised on
// a PC (tests/test_firmware.py). stdin carries the serial link; lines starting with '~'
// are test controls:  "~d <pin> <0|1>" input level, "~a <pin> <value>" ADC value,
// "~i <pin> <count>" fire the pin's interrupt, "~w <0|1>" Wi-Fi up / lost, "~q" quit.
// Output writes are reported on stderr:  PM pinMode, DW digitalWrite, AW analogWrite,
// DA dacWrite, DD dacDisable, WB WiFi.begin, and "XX ..." when the sketch touches a pin that
// would crash the real chip (flash pins of the ESP boards).
//
// The board is chosen by -D flags only, as the Arduino cores do it:
//   (none) UNO R3            -DMOCK_NANO Nano               -D__AVR_ATmega2560__ Mega
//   -DARDUINO_UNOR4_MINIMA / -DARDUINO_UNOR4_WIFI           UNO R4
//   -DARDUINO_NANO_R4 -DARDUINO_UNOR4_MINIMA -DMOCK_NANO    Nano R4
//   -DARDUINO_ARCH_ESP32 -DCONFIG_IDF_TARGET_ESP32=1        ESP32 DevKit
//   -DARDUINO_ARCH_ESP32 -DCONFIG_IDF_TARGET_ESP32C3=1 [-DARDUINO_USB_CDC_ON_BOOT=1]   ESP32-C3
//   -DARDUINO_ARCH_ESP8266                                  ESP8266 NodeMCU
// The ESP32 builds stand in for the esp32 core 3.x; add -DESP_ARDUINO_VERSION_MAJOR=2 for core
// 2.x, whose PWM differs: ledcSetup / ledcAttachPin / ledcWrite(channel) / ledcDetachPin exist,
// pinMode() takes a pin away from its LEDC channel, and analogWrite() must not be used at all
// (it never frees a channel). LS ledcSetup, LA ledcAttachPin, LD ledcDetachPin; a duty that
// reaches a pin is reported as AW on both cores.
// Calls that exist only on some cores (dacWrite, analogReadMilliVolts, analogWriteRange,
// analogWriteResolution, Serial0, Serial2 ...) are declared only for those targets, so using
// one on the wrong board fails to compile here as it would in the IDE.
#pragma once
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <string>
#include <unistd.h>

typedef uint8_t byte;
#define HIGH 1
#define LOW 0
#define INPUT 0
#define OUTPUT 1
#define INPUT_PULLUP 2
#define FALLING 2
#define NOT_AN_INTERRUPT -1
#if defined(ARDUINO_ARCH_ESP32)
  #define MOCK_ESP 1
  #define INPUT_PULLDOWN 9
#elif defined(ARDUINO_ARCH_ESP8266)
  #define MOCK_ESP 1                 // no INPUT_PULLDOWN on this core (only INPUT_PULLDOWN_16)
#elif defined(ARDUINO_UNOR4_WIFI) || defined(ARDUINO_UNOR4_MINIMA) || defined(MOCK_UNOQ)
  #define INPUT_PULLDOWN 3           // (an enum, not a macro, in the real Renesas core)
#else
  #define __AVR__ 1
#endif
#if defined(ARDUINO_ARCH_ESP32) && CONFIG_IDF_TARGET_ESP32C3
  #define A0 0
  #define SDA 8
  #define SCL 9
  #define NUM_ANALOG_INPUTS 6
  #define digitalPinHasPWM(p) ((p) < 22)
  #define digitalPinToInterrupt(p) (p)
  #define MOCK_FORBIDDEN(p) ((p) >= 11 && (p) <= 19)       // supply, flash, USB
#elif defined(ARDUINO_ARCH_ESP32)
  #define A0 36
  #define SDA 21
  #define SCL 22
  #define NUM_ANALOG_INPUTS 16
  #define digitalPinHasPWM(p) ((p) < 34)
  #define digitalPinToInterrupt(p) (p)
  #define MOCK_FORBIDDEN(p) ((p) >= 6 && (p) <= 11)        // SPI flash
#elif defined(ARDUINO_ARCH_ESP8266)
  #define A0 17
  #define SDA 4
  #define SCL 5
  #define NUM_ANALOG_INPUTS 1
  #define digitalPinHasPWM(p) ((p) < 16)
  #define digitalPinToInterrupt(p) (p)
  #define MOCK_FORBIDDEN(p) (((p) >= 6 && (p) <= 11) || (p) == 17)   // SPI flash; A0 is not a GPIO
#elif defined(__AVR_ATmega2560__)
  #define A0 54
  #define SDA 20
  #define SCL 21
  #define NUM_ANALOG_INPUTS 16
  #define digitalPinHasPWM(p) (((p) >= 2 && (p) <= 13) || ((p) >= 44 && (p) <= 46))
  #define digitalPinToInterrupt(p) ((p) == 2 ? 0 : ((p) == 3 ? 1 : ((p) >= 18 && (p) <= 21 ? 23 - (p) : NOT_AN_INTERRUPT)))
#else
  #define A0 14
  #define SDA 18
  #define SCL 19
  #ifdef MOCK_NANO
    #define NUM_ANALOG_INPUTS 8
  #else
    #define NUM_ANALOG_INPUTS 6
  #endif
  #define digitalPinHasPWM(p) ((p) == 3 || (p) == 5 || (p) == 6 || (p) == 9 || (p) == 10 || (p) == 11)
  #define digitalPinToInterrupt(p) ((p) == 2 ? 0 : ((p) == 3 ? 1 : NOT_AN_INTERRUPT))
#endif
#ifndef MOCK_ESP
  #define A1 (A0 + 1)
  #define A2 (A0 + 2)
  #define A3 (A0 + 3)
  #define A4 (A0 + 4)
  #define A5 (A0 + 5)
  #define DAC A0
  #define MOCK_FORBIDDEN(p) 0
#endif
#define MOCK_NPIN 80
#if defined(ARDUINO_ARCH_ESP32) && !defined(ESP_ARDUINO_VERSION_MAJOR)
  #define ESP_ARDUINO_VERSION_MAJOR 3
#endif
#if defined(ARDUINO_ARCH_ESP32) && ESP_ARDUINO_VERSION_MAJOR < 3
  #if CONFIG_IDF_TARGET_ESP32C3
    #define MOCK_LEDC2 6             // LEDC channels of the chip
  #else
    #define MOCK_LEDC2 16
  #endif
inline int mockPinLedc[MOCK_NPIN];  // channel + 1 that drives the pin right now, 0 = none
#endif

inline int mockLevel[MOCK_NPIN], mockAnalog[MOCK_NPIN];
inline void (*mockIsr[MOCK_NPIN])();   // indexed by interrupt number (on ESP that is the GPIO number)
inline std::string mockRx;          // link bytes waiting for the sketch
inline int mockWifiLost;            // "~w 0": the access point is gone until the sketch joins again
inline void (*mockCtl)(const std::string &);   // extra '~' controls of a test harness
inline void mockBad(const char *what, int p) { if (MOCK_FORBIDDEN(p)) fprintf(stderr, "XX %s %d\n", what, p); }

inline uint32_t millis() {
  using namespace std::chrono;
  static auto t0 = steady_clock::now();
  return (uint32_t)duration_cast<milliseconds>(steady_clock::now() - t0).count();
}
inline uint32_t micros() { return millis() * 1000u; }
inline void delay(uint32_t ms) { usleep(ms * 1000); }
inline void pinMode(int p, int m) {
  mockBad("pinMode", p); fprintf(stderr, "PM %d %d\n", p, m);
  if (m == INPUT_PULLUP && p < MOCK_NPIN && mockLevel[p] < 0) mockLevel[p] = 1;
#ifdef MOCK_LEDC2
  if (p >= 0 && p < MOCK_NPIN) mockPinLedc[p] = 0;          // gpio_config() makes it a plain GPIO again
#endif
}
inline void digitalWrite(int p, int v) { mockBad("digitalWrite", p); fprintf(stderr, "DW %d %d\n", p, v); }
inline int digitalRead(int p) { return (p >= 0 && p < MOCK_NPIN && mockLevel[p] > 0) ? 1 : 0; }
inline int analogRead(int p) { return (p >= 0 && p < MOCK_NPIN) ? mockAnalog[p] : 0; }
#ifdef MOCK_LEDC2
// esp32 core 2.x. analogWrite() there keeps a pin's channel until reset and (2.0.0-2.0.8) does not
// attach a pin a second time, so a sketch that frees and re-uses PWM pins cannot rely on it.
inline void analogWrite(int p, int) { fprintf(stderr, "XX analogWrite %d (esp32 core 2.x never frees its channel)\n", p); }
inline uint32_t ledcSetup(uint8_t ch, uint32_t freq, uint8_t bits) {
  if (ch >= MOCK_LEDC2 || bits > 14) { fprintf(stderr, "XX ledcSetup %d\n", ch); return 0; }
  fprintf(stderr, "LS %d %u %d\n", ch, (unsigned)freq, bits);
  return freq;
}
inline void ledcAttachPin(uint8_t p, uint8_t ch) {
  mockBad("ledcAttachPin", p);
  if (ch >= MOCK_LEDC2 || p >= MOCK_NPIN) { fprintf(stderr, "XX ledcAttachPin %d %d\n", p, ch); return; }
  for (int i = 0; i < MOCK_NPIN; i++) if (mockPinLedc[i] == ch + 1) fprintf(stderr, "XX ledcAttachPin %d %d: the channel still drives pin %d\n", p, ch, i);
  mockPinLedc[p] = ch + 1;
  fprintf(stderr, "LA %d %d\n", p, ch);
}
inline void ledcDetachPin(uint8_t p) { if (p < MOCK_NPIN) mockPinLedc[p] = 0; fprintf(stderr, "LD %d\n", p); }
inline void ledcWrite(uint8_t ch, uint32_t duty) {
  for (int i = 0; i < MOCK_NPIN; i++) if (mockPinLedc[i] == ch + 1) { fprintf(stderr, "AW %d %u\n", i, (unsigned)duty); return; }
  fprintf(stderr, "XX ledcWrite %d: no pin is attached to this channel\n", ch);
}
#else
inline void analogWrite(int p, int v) { mockBad("analogWrite", p); fprintf(stderr, "AW %d %d\n", p, v); }
#endif
#ifndef MOCK_ESP
inline void analogReadResolution(int) {}
inline void analogWriteResolution(int) {}       // not on ESP: its signature differs between core versions
#endif
#if defined(ARDUINO_ARCH_ESP32)
#define IRAM_ATTR
#define SERIAL_8N1 0
inline uint32_t analogReadMilliVolts(int p) { return (p >= 0 && p < MOCK_NPIN) ? (uint32_t)mockAnalog[p] : 0; }
inline uint32_t esp_random() { return (uint32_t)rand() ^ ((uint32_t)getpid() << 7) ^ (uint32_t)std::chrono::steady_clock::now().time_since_epoch().count(); }
#if !CONFIG_IDF_TARGET_ESP32C3                  // only the original ESP32 has the two DAC pins
inline bool dacWrite(int p, int v) { fprintf(stderr, "DA %d %d\n", p, v); return true; }
inline bool dacDisable(int p) { fprintf(stderr, "DD %d\n", p); return true; }
#endif
#endif
#if defined(ARDUINO_ARCH_ESP8266)
#define IRAM_ATTR
#define RANDOM_REG32 ((uint32_t)rand() ^ ((uint32_t)getpid() << 7) ^ (uint32_t)std::chrono::steady_clock::now().time_since_epoch().count())
inline void analogWriteRange(int r) { fprintf(stderr, "AR %d\n", r); }
#endif
inline void attachInterrupt(int n, void (*fn)(), int) { if (n >= 0 && n < MOCK_NPIN) mockIsr[n] = fn; }
inline void detachInterrupt(int n) { if (n >= 0 && n < MOCK_NPIN) mockIsr[n] = nullptr; }
inline void noInterrupts() {}
inline void interrupts() {}

// Read stdin without blocking; split test controls from link bytes.
inline void mockPump() {
  static std::string line;
  static bool init = false;
  if (!init) { init = true; fcntl(0, F_SETFL, fcntl(0, F_GETFL) | O_NONBLOCK); for (int i = 0; i < MOCK_NPIN; i++) mockLevel[i] = -1; }
  char buf[256];
  ssize_t n;
  while ((n = read(0, buf, sizeof buf)) > 0) {
    for (ssize_t i = 0; i < n; i++) {
      line += buf[i];
      if (buf[i] != '\n') continue;
      if (line[0] == '~') {
        char k = line[1]; int p = 0; long v = 0;
        sscanf(line.c_str() + 2, "%d %ld", &p, &v);
        if (k == 'd' && p < MOCK_NPIN) mockLevel[p] = (int)v;
        if (k == 'a' && p < MOCK_NPIN) mockAnalog[p] = (int)v;
        if (k == 'i') { int irq = digitalPinToInterrupt(p); for (long c = 0; c < v; c++) if (irq >= 0 && irq < MOCK_NPIN && mockIsr[irq]) mockIsr[irq](); }
        if (k == 'w') mockWifiLost = (p == 0);
        if (k == 'q') exit(0);
        if (mockCtl) mockCtl(line);
      } else mockRx += line;
      line.clear();
    }
  }
  if (n == 0) exit(0);               // stdin closed: the test is over
}

struct MockSerial {
  void begin(long) {}
#if defined(ARDUINO_ARCH_ESP32)
  void begin(long, int, int rx, int tx) { fprintf(stderr, "SB %d %d\n", rx, tx); }   // baud, format, RX pin, TX pin
#endif
  void end() {}
  int available() { mockPump(); return (int)mockRx.size(); }
  int read() { if (mockRx.empty()) return -1; char c = mockRx[0]; mockRx.erase(0, 1); return (uint8_t)c; }
  void println(const char *s) { printf("%s\n", s); fflush(stdout); }
  void print(const char *s) { printf("%s", s); fflush(stdout); }
};
inline MockSerial Serial, Serial1;
#if defined(ARDUINO_ARCH_ESP32) && CONFIG_IDF_TARGET_ESP32C3
  #if ARDUINO_USB_CDC_ON_BOOT
inline MockSerial Serial0;           // the UART pins, while Serial is the USB port
  #endif
#elif defined(ARDUINO_ARCH_ESP32)
inline MockSerial Serial2;
#endif

void setup();
void loop();
void mockTick();
