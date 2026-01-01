# Serial Transports

**Directory:** `sdk/adapter/lib/transport/serial/`
**Use Case:** Communication via serial ports (UART, USB-to-serial)
**Platforms:** Linux, macOS, embedded Linux (Raspberry Pi, Jetson)

Serial transports enable communication over UART/RS-232 interfaces, commonly used for embedded development, USB-to-serial adapters, and devices without network connectivity.

---

## Overview

| Transport | File | Latency | Throughput | Use When... |
|-----------|------|---------|------------|-------------|
| **UART POSIX** | `uart_posix.c` | ~10ms @ 115200 | 11 KB/s @ 115200 | USB-to-serial development, embedded Linux without networking, legacy serial devices |

---

## UART POSIX Transport

**File:** `uart_posix.c` (264 lines)
**Mechanism:** POSIX `termios` API for serial port configuration
**Latency:** ~10ms @ 115200 baud, ~1.8ms @ 921600 baud
**Throughput:** ~11 KB/s @ 115200, ~44 KB/s @ 460800, ~88 KB/s @ 921600

### Purpose

The UART POSIX transport provides **serial port communication** using standard POSIX termios interfaces. It's the primary transport for devices without network connectivity or when direct serial connection is preferred.

**Use it for:**
- Development with USB-to-serial adapters (FTDI, CH340, CP2102)
- Embedded Linux devices without Ethernet (serial-only boot, debug console)
- Raspberry Pi UART pins (GPIO14/15)
- Legacy industrial equipment with RS-232 ports
- Initial bring-up of custom hardware (before network stack is working)

**Do NOT use for:**
- High-throughput applications (network transports are 1000× faster)
- Production deployments (network is more reliable and flexible)
- Same-machine testing (use local transports instead)

### How It Works

```
┌──────────────┐                         ┌──────────────┐
│   Harness    │                         │   Adapter    │
│              │                         │              │
│  UART TX     ├────── Serial Cable ────►│  UART RX     │
│  UART RX     ◄─────────────────────────┤  UART TX     │
│              │   (RS-232, LVTTL, etc)  │              │
└──────────────┘                         └──────────────┘
    /dev/ttyUSB0                            /dev/ttyS0
```

**Physical Layer:**
- **RS-232:** ±12V signaling (DB9 connector, common on PCs)
- **LVTTL:** 3.3V/5V logic levels (Raspberry Pi, Arduino)
- **USB-to-Serial:** FTDI/CH340 chip converts USB to TTL/RS-232

**Configuration (8N1 - Standard):**
- **8 data bits:** Each byte sent as 8 bits
- **N**o parity: No error-checking bit
- **1 stop bit:** Single stop bit after data

**Key Properties:**
- **Asynchronous:** No shared clock (both sides must use same baud rate)
- **Full-duplex:** Simultaneous transmit and receive on separate wires
- **Simple:** Minimal hardware requirements (just TX/RX/GND)
- **Slow:** Limited by baud rate (typically 9600-921600 bps)
- **Unreliable:** No error correction (noisy lines cause corruption)

### API

#### cortex_transport_uart_posix_create()

```c
cortex_transport_t* cortex_transport_uart_posix_create(
    const char *device,
    uint32_t baud_rate
);
```

Opens a serial port and configures it for CORTEX protocol communication.

**Parameters:**
- `device`: Device path (e.g., `"/dev/ttyUSB0"`, `"/dev/cu.usbserial-A50285BI"`)
- `baud_rate`: Communication speed in bits per second (e.g., `115200`, `460800`, `921600`)

**Returns:**
- Non-NULL: Successfully opened and configured transport
- NULL: Failed to open device or configure port (check `errno`)

**Supported Baud Rates:**
| Baud Rate | Availability | Throughput | Use Case |
|-----------|--------------|------------|----------|
| 9600 | Universal | 960 B/s | Legacy devices, debugging |
| 19200 | Universal | 1.9 KB/s | Legacy devices |
| 38400 | Universal | 3.8 KB/s | Legacy devices |
| 57600 | Most platforms | 5.7 KB/s | Modern devices |
| 115200 | Most platforms | 11 KB/s | **Standard default** |
| 230400 | Some platforms | 22 KB/s | High-speed USB-to-serial |
| 460800 | Linux/some macOS | 44 KB/s | USB-to-serial with FTDI chip |
| 921600 | Linux/some macOS | 88 KB/s | Maximum for most USB-to-serial |

**Platform Compatibility:**
- **Linux:** All baud rates supported (kernel handles any rate)
- **macOS:** 9600-115200 universal, higher rates depend on USB driver
- **Unsupported rates:** Function selects closest lower rate (e.g., 1000000 → 921600)

**Port Configuration:**
The transport configures the port with these settings:
- **8N1:** 8 data bits, no parity, 1 stop bit
- **Raw mode:** No line processing (`cfmakeraw()`)
- **No flow control:** RTS/CTS disabled (hardware flow control off)
- **No canonical mode:** Characters available immediately (no line buffering)
- **Non-blocking I/O:** Uses `select()` for timeout support

**Example (Harness Side):**
```c
/* Connect to USB-to-serial adapter at 115200 baud */
cortex_transport_t *transport = cortex_transport_uart_posix_create(
    "/dev/ttyUSB0",  /* Linux: USB-to-serial adapter */
    115200           /* Standard baud rate */
);

if (!transport) {
    perror("Failed to open serial port");
    fprintf(stderr, "Check:\n");
    fprintf(stderr, "  1. Device exists: ls -l /dev/ttyUSB*\n");
    fprintf(stderr, "  2. You have permissions: sudo usermod -a -G dialout $USER\n");
    fprintf(stderr, "  3. Device is not in use: lsof | grep ttyUSB0\n");
    return -1;
}

/* Use with protocol layer */
cortex_protocol_handshake(transport, CORTEX_ABI_VERSION, 5000);

transport->close(transport->ctx);
free(transport);
```

**Example (Adapter Side - Raspberry Pi):**
```c
/* Adapter running on Raspberry Pi using built-in UART (GPIO14/15) */
cortex_transport_t *transport = cortex_transport_uart_posix_create(
    "/dev/ttyAMA0",  /* Raspberry Pi hardware UART */
    115200
);

if (!transport) {
    perror("Failed to open UART");
    return -1;
}

/* Run adapter loop */
cortex_protocol_recv_frame(transport, &msg_type, buf, sizeof(buf), 5000);
```

**macOS Device Paths:**
```c
/* macOS uses /dev/cu.* for USB-to-serial devices */
cortex_transport_t *transport = cortex_transport_uart_posix_create(
    "/dev/cu.usbserial-A50285BI",  /* FTDI USB-to-serial */
    115200
);
```

---

### Implementation Details

**Port Opening:**
```c
cortex_transport_t *cortex_transport_uart_posix_create(const char *device, uint32_t baud_rate)
{
    /* Open device with non-blocking flag */
    uart->fd = open(device, O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (uart->fd < 0) {
        free(uart);
        return NULL;
    }

    /* Get current port settings */
    struct termios options;
    if (tcgetattr(uart->fd, &options) < 0) {
        close(uart->fd);
        free(uart);
        return NULL;
    }

    /* Configure baud rate */
    speed_t speed = speed_from_baud(baud_rate);
    cfsetispeed(&options, speed);
    cfsetospeed(&options, speed);

    /* 8N1 configuration */
    options.c_cflag &= ~PARENB;   /* No parity */
    options.c_cflag &= ~CSTOPB;   /* 1 stop bit */
    options.c_cflag &= ~CSIZE;    /* Clear size bits */
    options.c_cflag |= CS8;       /* 8 data bits */

    /* Disable flow control */
#ifdef CRTSCTS
    options.c_cflag &= ~CRTSCTS;  /* No hardware flow control (Linux) */
#elif defined(CNEW_RTSCTS)
    options.c_cflag &= ~CNEW_RTSCTS;  /* No hardware flow control (BSD) */
#endif

    /* Enable receiver, ignore modem control lines */
    options.c_cflag |= (CLOCAL | CREAD);

    /* Raw mode (no processing) */
    cfmakeraw(&options);

    /* Apply settings */
    tcsetattr(uart->fd, TCSANOW, &options);

    return transport;
}
```

**recv() Implementation:**
```c
static ssize_t uart_posix_recv(void *ctx, void *buf, size_t len, uint32_t timeout_ms)
{
    uart_posix_ctx_t *uart = (uart_posix_ctx_t *)ctx;

    /* Wait for data with timeout using select() */
    fd_set read_fds;
    FD_ZERO(&read_fds);
    FD_SET(uart->fd, &read_fds);

    struct timeval timeout;
    timeout.tv_sec = timeout_ms / 1000;
    timeout.tv_usec = (timeout_ms % 1000) * 1000;

    int sel_ret = select(uart->fd + 1, &read_fds, NULL, NULL, &timeout);

    if (sel_ret == 0) {
        return CORTEX_ETIMEDOUT;  /* Timeout */
    } else if (sel_ret < 0) {
        return -errno;  /* Error */
    }

    /* Read available data */
    ssize_t n = read(uart->fd, buf, len);

    if (n == 0) {
        return CORTEX_ECONNRESET;  /* EOF (device disconnected) */
    } else if (n < 0) {
        return -errno;
    }

    return n;
}
```

**Key behaviors:**
- Uses `select()` for timeout support (portable)
- Returns `CORTEX_ETIMEDOUT` if no data within timeout
- May return partial reads (protocol layer handles reassembly)
- Returns `CORTEX_ECONNRESET` if device disconnected

**send() Implementation:**
```c
static ssize_t uart_posix_send(void *ctx, const void *buf, size_t len)
{
    uart_posix_ctx_t *uart = (uart_posix_ctx_t *)ctx;

    ssize_t n = write(uart->fd, buf, len);

    if (n < 0) {
        if (errno == EIO || errno == ENXIO) {
            return CORTEX_ECONNRESET;  /* Device disconnected */
        }
        return -errno;
    }

    return n;
}
```

**close() Implementation:**
```c
static void uart_posix_close(void *ctx)
{
    uart_posix_ctx_t *uart = (uart_posix_ctx_t *)ctx;

    if (uart->fd >= 0) {
        /* Drain output buffer before closing */
        tcdrain(uart->fd);
        close(uart->fd);
    }

    free(uart);
}
```

**Baud Rate Conversion:**
```c
static speed_t speed_from_baud(uint32_t baud)
{
    switch (baud) {
        case 9600:   return B9600;
        case 19200:  return B19200;
        case 38400:  return B38400;

#ifdef B57600
        case 57600:  return B57600;
#endif

#ifdef B115200
        case 115200: return B115200;
#endif

#ifdef B230400
        case 230400: return B230400;
#endif

#ifdef B460800
        case 460800: return B460800;
#endif

#ifdef B921600
        case 921600: return B921600;
#endif

        default:
            /* Unsupported rate - default to 38400 */
            fprintf(stderr, "Warning: Unsupported baud rate %u, using 38400\n", baud);
            return B38400;
    }
}
```

**Platform guards** ensure code compiles even if high baud rates aren't defined.

---

### Performance

Measured with **FTDI FT232R USB-to-serial adapter** on macOS:

| Baud Rate | Theoretical | Real-world | Latency (P50) | Use Case |
|-----------|-------------|------------|---------------|----------|
| 9600 | 960 B/s | 900 B/s | 120ms | Debugging only |
| 19200 | 1.9 KB/s | 1.8 KB/s | 60ms | Legacy devices |
| 38400 | 3.8 KB/s | 3.6 KB/s | 30ms | Legacy devices |
| 57600 | 5.7 KB/s | 5.4 KB/s | 20ms | Modern low-speed |
| **115200** | **11 KB/s** | **10.5 KB/s** | **10ms** | **Standard** |
| 230400 | 22 KB/s | 21 KB/s | 5ms | High-speed |
| 460800 | 44 KB/s | 42 KB/s | 2.5ms | USB-to-serial max |
| 921600 | 88 KB/s | 84 KB/s | 1.8ms | Absolute maximum |

**Why "real-world" < theoretical:**
- **Protocol overhead:** Start bit, stop bit, parity (10-11 bits per 8-bit byte)
- **USB polling:** USB host polls adapter every 1ms (adds latency)
- **Buffer overhead:** Kernel buffers introduce copying delays
- **CPU scheduling:** Non-realtime OS introduces jitter

**Latency breakdown (115200 baud):**
1. **Serialization delay:** Time to transmit bits over wire (~870µs for 100-byte frame)
2. **USB polling:** Host polls adapter every 1ms (~500µs average)
3. **Kernel processing:** Copy from USB buffer to userspace (~200µs)
4. **Application wakeup:** `select()` wakes recv thread (~50µs)
5. **Total:** ~1.6ms minimum, ~10ms P50 (due to buffering/scheduling)

**Bottlenecks:**
- **Baud rate:** Fundamental limit (921600 is max for most USB-to-serial chips)
- **USB latency:** 1ms polling interval adds significant overhead
- **Byte-at-a-time transfer:** No DMA or burst optimization in many USB-to-serial chips

---

### Platform Notes

#### Linux

**Device Paths:**
- `/dev/ttyUSB0`, `/dev/ttyUSB1`, ... — USB-to-serial adapters
- `/dev/ttyACM0`, `/dev/ttyACM1`, ... — USB CDC-ACM devices (Arduino)
- `/dev/ttyS0`, `/dev/ttyS1`, ... — Hardware serial ports (motherboard COM ports)
- `/dev/ttyAMA0` — Raspberry Pi hardware UART (GPIO14/15)

**Permissions:**
- Serial devices are owned by `dialout` group (Ubuntu/Debian) or `uucp` (Arch)
- Add user to group: `sudo usermod -a -G dialout $USER`
- Log out and back in for group change to take effect
- Or use `sudo` (not recommended for production)

**Checking Permissions:**
```bash
$ ls -l /dev/ttyUSB0
crw-rw---- 1 root dialout 188, 0 Dec 29 10:15 /dev/ttyUSB0

$ groups
user dialout sudo
# If "dialout" is missing, run: sudo usermod -a -G dialout $USER
```

**Finding Devices:**
```bash
# List all serial devices
ls -l /dev/tty{USB,ACM,S}*

# Watch for new devices when plugging in USB-to-serial
dmesg -w
# Plug in device, look for lines like:
# [12345.678] usb 1-1.2: FTDI USB Serial Device converter now attached to ttyUSB0
```

**Baud Rate Support:**
- Linux kernel supports any baud rate (not limited to standard values)
- Use `stty -F /dev/ttyUSB0 115200` to verify configuration

#### macOS

**Device Paths:**
- `/dev/cu.usbserial-*` — FTDI USB-to-serial adapters
- `/dev/cu.usbmodem*` — USB CDC-ACM devices (Arduino)
- `/dev/cu.SLAB_USBtoUART` — Silicon Labs CP2102 adapters
- `/dev/cu.wchusbserial*` — CH340 chipset adapters

**Note:** Use `/dev/cu.*` (callout), NOT `/dev/tty.*` (dialin) for outgoing connections.

**Permissions:**
- macOS grants access to current user automatically
- No group membership required

**Finding Devices:**
```bash
# List all USB-to-serial devices
ls -l /dev/cu.usb*

# Detailed USB device info
system_profiler SPUSBDataType | grep -A 10 "Serial"
```

**Driver Installation:**
- **FTDI:** Built-in driver (no installation needed)
- **CH340:** May require driver from manufacturer
- **Silicon Labs CP210x:** Built-in on modern macOS (10.13+)

#### Raspberry Pi

**Hardware UART (GPIO14/15):**
- Device: `/dev/ttyAMA0` (older Pi) or `/dev/ttyS0` (Pi 3+)
- Pins: GPIO14 (TXD), GPIO15 (RXD), GND
- **3.3V LOGIC LEVELS** (not RS-232 compatible - use level shifter for ±12V devices)

**Enabling UART:**
```bash
# Edit /boot/config.txt (requires sudo)
sudo nano /boot/config.txt

# Add these lines:
enable_uart=1
dtoverlay=disable-bt  # Disable Bluetooth to free up UART (Pi 3/4)

# Reboot
sudo reboot

# Test after reboot
ls -l /dev/ttyAMA0
```

**Disable Serial Console:**
Raspberry Pi uses UART for console by default - disable to use for CORTEX:
```bash
sudo raspi-config
# Interface Options → Serial Port
# "Would you like a login shell accessible over serial?" → No
# "Would you like the serial port hardware enabled?" → Yes
```

**Wiring:**
```
Pi (3.3V TTL)         USB-to-Serial (3.3V mode)
-----------           -----------------------
GPIO14 (TXD) -------> RX
GPIO15 (RXD) <------- TX
GND          <------> GND

WARNING: Do NOT connect 5V USB-to-serial TX to Pi RX (will damage Pi)
Use 3.3V adapter or level shifter
```

---

### Troubleshooting

**"Permission denied" when opening device:**
- User not in `dialout` group (Linux)
  - Fix: `sudo usermod -a -G dialout $USER`, then log out/in
- Device in use by another process
  - Fix: `lsof | grep ttyUSB0` to find process, kill it
- Device permissions wrong
  - Fix: `sudo chmod 666 /dev/ttyUSB0` (temporary) or fix udev rules (permanent)

**"No such file or directory" when opening device:**
- Device not plugged in
  - Fix: Check physical connection
- Wrong device path
  - Fix: Run `ls /dev/tty*` to find correct path
- Driver not loaded (CH340, CP210x on macOS)
  - Fix: Install manufacturer driver

**recv() always times out (no data received):**
- TX/RX wires swapped
  - Fix: Swap connections (TX→RX, RX→TX)
- Wrong baud rate on remote side
  - Fix: Verify both sides use same baud rate (115200)
- Device not transmitting
  - Fix: Check device logs, verify it's sending data
- Ground not connected
  - Fix: Ensure GND wire connected between devices

**Garbled data / random characters:**
- Baud rate mismatch
  - Fix: Ensure both sides use same baud rate
- 3.3V vs 5V logic level mismatch
  - Fix: Use level shifter or configure adapter for correct voltage
- Noisy connection (long cable, no shielding)
  - Fix: Use shorter cable, add ferrite beads, lower baud rate

**Intermittent disconnections:**
- USB cable loose
  - Fix: Use higher-quality USB cable
- USB power issues
  - Fix: Use powered USB hub
- Driver stability (CH340 on macOS)
  - Fix: Try FTDI-based adapter instead

**recv() returns ECONNRESET:**
- USB device disconnected
  - Fix: Check physical connection
- Driver crashed (rare)
  - Fix: Unplug/replug device, check `dmesg` for errors

**High latency (>50ms at 115200):**
- Low baud rate
  - Fix: Increase to 460800 or 921600 if supported
- USB polling overhead
  - Expected: USB introduces 1ms latency minimum
- Kernel buffering
  - Try: Flush buffers with `tcflush()` before critical operations

**Throughput much lower than expected:**
- Check actual baud rate: `stty -F /dev/ttyUSB0` (Linux)
- Verify 8N1 configuration (no parity, 1 stop bit)
- Monitor for errors: `stty -F /dev/ttyUSB0 -a | grep error`
- Try different USB port (some ports share bandwidth)

---

## Hardware Recommendations

### USB-to-Serial Adapters

**Recommended: FTDI FT232R**
- ✅ Excellent Linux/macOS driver support (built-in)
- ✅ Reliable operation up to 921600 baud
- ✅ 3.3V and 5V I/O voltage options
- ⚠️ More expensive ($15-25)
- ⚠️ Beware of counterfeit chips (buy from reputable vendors)

**Acceptable: Silicon Labs CP2102**
- ✅ Good driver support (built-in on modern systems)
- ✅ Works up to 921600 baud
- ✅ Lower cost ($5-10)
- ⚠️ Slightly higher latency than FTDI

**Avoid: CH340/CH341**
- ⚠️ Requires driver installation on macOS
- ⚠️ Unstable drivers (known to crash)
- ⚠️ Limited to 115200 baud on some systems
- ✅ Very cheap ($2-5)
- Use only for non-critical development

### Level Shifters

**When You Need One:**
- Connecting 3.3V device (Raspberry Pi) to 5V USB-to-serial
- Connecting UART to RS-232 device (±12V)

**Recommended: SparkFun BOB-12009**
- Bidirectional 3.3V ↔ 5V conversion
- Fast enough for 921600 baud
- 4 channels (TX, RX, CTS, RTS)

**For RS-232: MAX3232 Breakout Board**
- Converts ±12V (RS-232) to 3.3V/5V TTL
- Includes charge pump (no external power needed)
- Works with legacy PC serial ports

---

## Future Serial Transports

**Planned for Phase 2+:**

### UART HAL (STM32)
- **File:** `uart_hal.c` (planned)
- **Use Case:** STM32 microcontrollers (bare-metal, no OS)
- **API:** Uses STM32 HAL library
- **Performance:** ~500µs latency with DMA

### ESP-IDF UART
- **File:** `uart_esp.c` (planned)
- **Use Case:** ESP32 microcontrollers
- **API:** Uses ESP-IDF UART driver
- **Performance:** ~2ms latency

### SPI
- **File:** `spi.c` (planned)
- **Use Case:** High-speed inter-board communication
- **Performance:** ~50µs latency, 10 MB/s throughput
- **Full-duplex:** Simultaneous send/receive

---

## Comparison with Network Transports

| Feature | UART (115200) | TCP (LAN) | Shared Memory |
|---------|---------------|-----------|---------------|
| **Latency** | ~10ms | ~1ms | ~5µs |
| **Throughput** | 11 KB/s | 100 MB/s | 2 GB/s |
| **Setup Complexity** | Easy | Easy | Easy |
| **Cabling** | Serial cable | Ethernet | Same machine |
| **Distance** | <15m | <100m (Ethernet) | N/A |
| **Reliability** | Low (noise) | High (TCP retries) | High |

**When to choose UART:**
- ✅ Device has no network interface
- ✅ Initial hardware bring-up (before network stack works)
- ✅ Direct GPIO connection (Raspberry Pi UART pins)
- ✅ Legacy equipment with only RS-232 interface
- ❌ High throughput needed (use TCP instead)
- ❌ Long cable runs (use TCP over Ethernet)

---

## See Also

- **Transport Selection Guide:** [`../README.md`](../README.md)
- **Local Transports:** [`../local/README.md`](../local/README.md)
- **Network Transports:** [`../network/README.md`](../network/README.md)
- **Example Usage:** `primitives/adapters/v1/native/adapter.c`
- **Protocol Layer:** `../protocol/README.md`
- **Transport API:** `../../include/cortex_transport.h`
