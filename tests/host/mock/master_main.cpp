// Runs sketch/sketch.ino on a PC far enough to exercise its Serial Monitor banner.
// stdin controls:  "~m <0|1>"  a Serial Monitor is attached      "~k <text>"  keys typed in it
//                  "~I <text>" Linux calls q_info(text), '|' stands for a newline; prints "i <result>"
//                  "~v"        prints "v <q_ver()>"
//                  "~c"        prints "r <mon/connected RPCs the sketch has made so far>"
// stdout carries what the sketch prints on Monitor.
#include "unoq_stubs.h"
int q_info(String t);
int q_ver();

static void control(const std::string &line) {
  std::string arg = line.size() > 3 ? line.substr(3) : "";
  while (!arg.empty() && (arg.back() == '\n' || arg.back() == '\r')) arg.pop_back();
  switch (line[1]) {
    case 'm': mockMonAttached = arg == "1"; break;
    case 'k': mockMonRx += arg.empty() ? "x" : arg; break;
    case 'I':
      for (char &c : arg) if (c == '|') c = '\n';
      printf("i %d\n", q_info(String(arg.c_str()))); fflush(stdout);
      break;
    case 'v': printf("v %d\n", q_ver()); fflush(stdout); break;
    case 'c': printf("r %ld\n", mockMonRpc); fflush(stdout); break;
    default: break;
  }
}

int main() {
  mockCtl = control;
  mockPump();
  setup();
  for (;;) {
    mockPump();
    mockRx.clear();                  // the master has no serial link of its own
    loop();
  }
}
