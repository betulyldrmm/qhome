// Stand-ins for the UNO Q libraries used by sketch/sketch.ino. Enough to compile the sketch
// and, with master_main.cpp, to run its Serial Monitor banner (q_info) on a PC.
#pragma once
#define MOCK_UNOQ 1
#include "Arduino.h"
#include <type_traits>
struct String {
  std::string s;
  String() {}
  String(const char *c) : s(c) {}
  int length() const { return (int)s.size(); }
  char charAt(int i) const { return s[i]; }
  const char *c_str() const { return s.c_str(); }
};
struct TwoWire {
  void begin() {}
  void beginTransmission(uint8_t) {}
  size_t write(uint8_t) { return 1; }
  int endTransmission() { return 0; }
  int requestFrom(int, int) { return 0; }
  int available() { return 0; }
  int read() { return -1; }
};
inline TwoWire Wire, Wire1;
struct UartStub { void begin(long) {} void end() {} int available() { return 0; } int read() { return -1; } void print(const String &) {} };
#define Serial1 Serial1Stub
inline UartStub Serial1Stub;
struct BridgeStub {
  void begin() {}
  template <typename F> bool provide_safe(const char *, F) { return true; }
  template <typename... A> void notify(const char *, A...) {}
};
inline BridgeStub Bridge;
// Monitor of Arduino_RouterBridge, with its real quirks (src/monitor.h): "connected" is cached
// once true; until then every `if (Monitor)` and every print is one blocking RPC to the router
// (mon/connected), counted here in mockMonRpc; nothing is printed while no monitor has ever been
// attached.
inline bool mockMonAttached;         // a Serial Monitor window is open (test control "~m 1")
inline std::string mockMonRx;        // keys typed in it (test control "~k <text>")
inline long mockMonRpc;              // mon/connected calls made so far (test control "~c")
struct MonitorStub {
  bool conn = false;
  bool begin(unsigned long = 0) { return (bool)*this; }
  bool is_connected() { return conn; }
  explicit operator bool() { if (!conn) { mockMonRpc++; conn = mockMonAttached; } return conn; }
  int available() { return (int)mockMonRx.size(); }
  int read() { if (mockMonRx.empty()) return -1; char c = mockMonRx[0]; mockMonRx.erase(0, 1); return (uint8_t)c; }
  template <typename T> size_t print(T v) {
    if (!*this) return 0;
    std::string t;
    if constexpr (std::is_arithmetic_v<T>) t = std::to_string(v); else t = v;
    fputs(t.c_str(), stdout); fflush(stdout);
    return t.size();
  }
  template <typename T> size_t println(T v) { size_t n = print(v); return n + (*this ? print("\n") : 0); }
  size_t println() { return print("\n"); }
};
inline MonitorStub Monitor;
struct Arduino_LED_Matrix { void begin() {} void setGrayscaleBits(int) {} void draw(uint8_t *) {} };
enum { LED3_R = 50, LED3_G, LED3_B, LED4_R, LED4_G, LED4_B };
#define DAC0 14
#define DAC1 15
