// QHome satellite settings. Pick how this board reaches the master, then upload.
// The Boards tab of the QHome web UI shows the exact values to use for each board.

#define QL_USB   1   // USB cable to the master (classic UNO/Nano/Mega, ESP32 DevKit and NodeMCU: the same
                     // UART as RX/TX)
#define QL_UART  2   // TX/RX wires to the master's D0/D1 (ESP32: RX2/TX2 = GPIO16/17,
                     // ESP32-C3: GPIO20/21, NodeMCU: RX/TX), RS-485 or HC-05/HC-12 modules
#define QL_I2C   3   // I2C slave on the master's SDA/SCL or Qwiic bus (not on ESP boards)
#define QL_WIFI  4   // Wi-Fi + MQTT (UNO R4 WiFi, ESP32, ESP32-C3, ESP8266)

#define QL_LINK  QL_USB

// --- USB / UART ---
#define QL_BAUD  115200

// --- I2C ---
#define QL_I2C_ADDRESS  0x10   // 8..119, unique per satellite on the bus
#define QL_I2C_PULLUPS  0      // 0 = keep the AVR's 5 V pull-ups off (the UNO Q bus is 3.3 V)

// --- Wi-Fi + MQTT (UNO R4 WiFi, ESP32, ESP32-C3, ESP8266) ---
#define QL_WIFI_SSID    "your-wifi"
#define QL_WIFI_PASS    "your-password"
#define QL_BOARD_ID     "kitchen"        // the board id you typed in the Boards tab
#define QL_MASTER_HOST  "192.168.1.50"   // IP address of the master UNO Q (or your MQTT broker)
#define QL_MASTER_PORT  1883
#define QL_MQTT_USER    ""               // only if the broker asks for a login
#define QL_MQTT_PASS    ""
