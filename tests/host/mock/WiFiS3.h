// Wi-Fi stand-in: WiFiClient is a real TCP socket, so the sketch's MQTT code talks to a real broker.
#pragma once
#include "Arduino.h"
#include <arpa/inet.h>
#include <netdb.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#define WL_CONNECTED 3
#define WIFI_STA 1
struct MockWiFi {
  int st = 0;
  int status() { if (mockWifiLost) st = 0; return st; }          // "~w 0" drops the network
  void begin(const char *, const char *) { fprintf(stderr, "WB\n"); mockWifiLost = 0; st = WL_CONNECTED; }
#ifdef MOCK_ESP
  bool mode(int) { return true; }
  bool setAutoReconnect(bool) { return true; }
  void persistent(bool) {}
#endif
#if defined(ARDUINO_ARCH_ESP32)
  bool setSleep(bool) { return true; }
#endif
};
inline MockWiFi WiFi;
struct WiFiClient {
  int fd = -1;
  bool connect(const char *host, uint16_t port) {
    stop();
    addrinfo hints{}, *res = nullptr;
    hints.ai_family = AF_INET; hints.ai_socktype = SOCK_STREAM;
    if (getaddrinfo(host, std::to_string(port).c_str(), &hints, &res) != 0) return false;
    fd = socket(AF_INET, SOCK_STREAM, 0);
    bool ok = ::connect(fd, res->ai_addr, res->ai_addrlen) == 0;
    freeaddrinfo(res);
    if (!ok) stop();
    return ok;
  }
  void stop() { if (fd >= 0) close(fd); fd = -1; }
#ifdef MOCK_ESP
  bool nodelay = false;
  void setNoDelay(bool on) { nodelay = on; fprintf(stderr, "ND %d\n", on ? 1 : 0); }
#endif
  bool connected() {
    if (fd < 0) return false;
    char c;
    ssize_t n = recv(fd, &c, 1, MSG_PEEK | MSG_DONTWAIT);
    if (n == 0) { stop(); return false; }
    return true;
  }
  int available() { int n = 0; if (fd >= 0) ioctl(fd, FIONREAD, &n); return n; }
  int read() { uint8_t c; return (fd >= 0 && recv(fd, &c, 1, 0) == 1) ? c : -1; }
  size_t write(const uint8_t *b, size_t n) { return fd >= 0 ? (size_t)send(fd, b, n, MSG_NOSIGNAL) : 0; }
};
