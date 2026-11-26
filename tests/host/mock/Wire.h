// I2C slave stand-in: link bytes from stdin arrive as master writes; the "master" polls
// 32 bytes on every loop pass and prints the non-zero ones to stdout.
#pragma once
#include "Arduino.h"
struct MockWire {
  void (*onRx)(int) = nullptr;
  void (*onReq)() = nullptr;
  std::string in, out;
  void begin(int) {}
  void onReceive(void (*f)(int)) { onRx = f; }
  void onRequest(void (*f)()) { onReq = f; }
  int available() { return (int)in.size(); }
  int read() { if (in.empty()) return -1; char c = in[0]; in.erase(0, 1); return (uint8_t)c; }
  void write(const uint8_t *b, int n) { out.assign((const char *)b, n); }
  void service() {
    mockPump();
    while (!mockRx.empty()) {                    // master writes at most 30 bytes per transfer
      in = mockRx.substr(0, 30); mockRx.erase(0, in.size());
      if (onRx) onRx((int)in.size());
    }
    if (onReq) { out.clear(); onReq(); for (char c : out) if (c) putchar(c); fflush(stdout); }
  }
};
inline MockWire Wire;
