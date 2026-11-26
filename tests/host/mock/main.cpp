#include "Arduino.h"
#ifdef MOCK_I2C
#include "Wire.h"
#endif
int main() {
  mockPump();
  setup();
  for (;;) {
#ifdef MOCK_I2C
    Wire.service();
#else
    mockPump();
#endif
    loop();
    usleep(300);
  }
}
