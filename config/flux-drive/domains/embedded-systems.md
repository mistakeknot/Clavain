# Embedded Systems Domain Profile

## Detection Signals

Primary signals (strong indicators):
- Directories: `firmware/`, `hal/`, `drivers/`, `bsp/`, `rtos/`
- Files: `*.c`, `*.h`, `Makefile`, `CMakeLists.txt`, `*.ld`, `*.s`, `platformio.ini`, `*.dts`
- Frameworks: FreeRTOS, Zephyr, Embassy, Arduino, ESP-IDF, STM32, nRF SDK, Mbed
- Keywords: `interrupt`, `ISR`, `DMA`, `GPIO`, `SPI`, `I2C`, `UART`, `volatile`, `register`, `peripheral`, `watchdog`

Secondary signals (supporting):
- Directories: `board/`, `arch/`, `test/`, `tools/`, `bootloader/`
- Files: `*.svd`, `*.cfg` (OpenOCD), `Kconfig`, `defconfig`, `*.overlay`
- Keywords: `firmware`, `bootloader`, `flash`, `SRAM`, `stack_size`, `heap`, `MPU`, `power_mode`, `sleep`

## Injection Criteria

When `embedded-systems` is detected, inject these domain-specific review bullets into each core agent's prompt.

### fd-architecture

- Check that hardware abstraction layers (HAL) fully decouple application logic from specific MCU registers and peripherals
- Verify that ISR handlers are minimal — set flags or enqueue work, don't do processing in interrupt context
- Flag missing separation between board support package (BSP) and application code (portability to new hardware)
- Check that memory layout (linker script) allocates separate sections for stack, heap, static data, and DMA buffers
- Verify that driver interfaces are testable on the host (mock hardware registers for unit tests without physical hardware)

### fd-safety

- Check that all external inputs (UART, SPI, I2C, ADC) are validated before use — untrusted peripherals exist
- Verify that firmware update mechanisms validate image integrity (CRC/signature) before flashing (bricked device risk)
- Flag missing watchdog timer configuration — a hung system should reset, not stay stuck silently
- Check that stack overflow detection is enabled (MPU guard regions or canary values) — stack overflow = silent corruption
- Verify that debug interfaces (JTAG, SWD) are disabled or locked in production builds

### fd-correctness

- Check for volatile correctness — variables shared between ISRs and main loop must be volatile (compiler optimization can hide updates)
- Verify that multi-byte register accesses are atomic or protected (reading a 32-bit timer on an 8-bit bus mid-update)
- Flag missing critical section protection around shared data structures accessed from multiple interrupt priorities
- Check that DMA buffer alignment and cache coherency are handled correctly (stale cache = wrong data after DMA transfer)
- Verify that peripheral initialization order respects hardware dependencies (clock enable before peripheral config)

### fd-quality

- Check that register magic numbers are replaced with named defines from vendor headers or SVD-generated constants
- Verify consistent error handling strategy — every HAL function should return status, not silently fail
- Flag duplicated peripheral configuration code — use a configuration table pattern, not copy-paste per instance
- Check that interrupt priority assignments are documented and follow a clear scheme (not arbitrary numbers)
- Verify that pin assignments and peripheral mappings are centralized in a board configuration file

### fd-performance

- Check that ISR latency is bounded — measure worst-case time from interrupt trigger to handler completion
- Flag busy-wait loops (`while(!flag)`) when interrupt-driven or DMA approaches would free the CPU
- Verify that power-sensitive paths use sleep modes between events (don't spin-wait polling sensors)
- Check that DMA is used for bulk data transfers (SPI, UART, ADC arrays) instead of byte-by-byte interrupt handling
- Flag stack allocation of large buffers — embedded stacks are small (typically 1-8KB), use static or heap allocation

### fd-user-product

- Check that device status is observable — LEDs, serial output, or diagnostic commands for field debugging
- Verify that firmware update is recoverable — a failed update shouldn't brick the device (dual-bank or recovery partition)
- Flag missing hardware self-test on startup (peripherals, sensors, communication links verified before entering operational mode)
- Check that error conditions produce distinct indicators (not just "red LED" for all failures)
- Verify that configuration can be changed without reflashing (persistent config in flash/EEPROM with factory defaults)

## Agent Specifications

These are domain-specific agents that `/flux-gen` can generate for embedded systems projects. They complement (not replace) the core fd-* agents.

### fd-hardware-interface

Focus: Register-level correctness, peripheral configuration, timing constraints, electrical interface compliance.

Persona: You are a hardware interface reviewer — you verify that software respects timing constraints, register protocols, and electrical reality.

Decision lens: Prefer fixes that respect hardware timing constraints over fixes that simplify the software abstraction. The hardware doesn't negotiate.

Key review areas:
- Check register read-modify-write sequences are atomic where required by concurrency or interrupt behavior.
- Verify clock tree and peripheral gating settings match datasheet requirements for all enabled peripherals.
- Validate configured timings (setup, hold, baud) stay within component tolerance across target frequencies.
- Confirm pin mux selections and alternate functions match board schematics and avoid conflicting assignments.
- Ensure power domains and voltage levels are configured for each peripheral operating range before activation.

### fd-rtos-patterns

Focus: Task design, synchronization primitives, memory management, deadline analysis.

Persona: You are an RTOS and resource-constrained systems reviewer — you count bytes, measure cycles, and treat every allocation as a potential failure point.

Decision lens: Prefer fixes that reduce worst-case resource usage over fixes that improve average-case performance. In embedded, the worst case is the only case that matters.

Key review areas:
- Check task priorities reflect deadline criticality and include mitigation for priority inversion (inheritance or ceiling).
- Verify synchronization primitive choice matches ownership and signaling semantics for each shared resource.
- Validate per-task stack sizing with runtime high-water marks and overflow detection enabled.
- Confirm periodic-task worst-case execution time and jitter stay within declared deadlines.
- Ensure memory pools are used for real-time paths, and dynamic allocation is bounded or excluded where nondeterministic.
