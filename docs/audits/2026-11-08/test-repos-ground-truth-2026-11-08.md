# Extrude test repos — independent ground-truth audit

Date: 2026-11-08. Auditor: Muse (subagent). Purpose: ground truth for testing the live
Extrude site. Extrude was NOT run on any of these repos; no PRs opened, no repo changed.

## Method (read this before trusting a finding)

- Each repo was cloned and the KiCad schematic (`.kicad_sch`) and PCB (`.kicad_pcb`) were
  parsed directly (S-expression parse, pad-to-net maps, symbol pin tables, firmware text).
- **No KiCad is installed in this VM, so no ERC / DRC / netlist run was possible.**
  Anything that needs a real ERC/DRC run, a Gerber viewer, or a footprint library is
  marked **not checked**.
- A single-pad net is NOT automatically a bug. Unused GPIOs, NC pins, card-detect pins,
  and deliberately unpopulated options are normal. A finding is listed as a bug only
  when the pin/function is actually needed for the board to work.
- Severity: **BUG** = board will not work as intended as built / as shipped.
  **RISK** = works in the common case, fails or degrades at an edge, or is out of spec.
  **WEAKNESS** = poor practice, works because of an internal pull-up / module default.
  **SUSPECT** = strong evidence of a bug, but one piece of proof is missing (named).
- Shashvat's repo (`shashvat1333/Bluetooth-Audio-Transmiter`) was excluded — already audited.

## Repo list

| # | Repo | Branch | SHA checked | Stars | Files |
|---|------|--------|-------------|-------|-------|
| 1 | https://github.com/leomanangka/esp32-4-channel-relays | main | `3c7d3b1eb80e781737f5ec5bed8cc10faca1ca0c` (2023-03-27) | 70 | sch, pcb, Gerbers |
| 2 | https://github.com/fixthepixel/bench-psu-monitor | main | `cd87301f7cb41831cc9ac8a3b7a62158e6dcd979` (2026-09-15) | 6 | sch, pcb, `.ino`, iBOM, Gerbers |
| 3 | https://github.com/pms67/STM32F4-Reference-PCB | master | `e0d1d8de53d43a6b82d834afdee54867cc44e89b` (2020-10-27) | 195 | pcb only, BOM CSV, Gerbers |
| 4 | https://github.com/iandchasse/silkscreen-pcb | master | `4530931d932cf760c8afc065327d88db94a18671` (2026-11-02) | 591 | sch, pcb, BOM |
| 5 | https://github.com/AzonInc/Doorman | master | `fdec5c030e77bb8e0219d745cc0282139c96836c` (2026-01-22) | 253 | sch, pcb, BOM, ESPHome, `docs/en/reference/gpio.md` |
| 6 | https://github.com/kylemanna/sniffer | master | `037c8c2bc562e95e62fe757d1dfc7d8d68e9aca9` (2026-07-16) | 166 | pcb only, Gerbers |
| 7 | https://github.com/UnsignedArduino/ESP32-Camera-PCB | main | `d467da91f7a4d41bf72a31ffbbc49c9d9091792f` (2023-02-03) | 8 | sch, pcb |

Coverage of the required mix: ESP32 boards (1, 2, 4, 5, 7), STM32 board (3),
simple breakout/sensor board (6, and 7 is a breakout carrier), boards likely to have
real bugs (2, 4, 6).

---

## 1. esp32-4-channel-relays — ESP32-WROOM-32, 4-channel relay board

- URL: https://github.com/leomanangka/esp32-4-channel-relays
- Branch: `main`. SHA: `3c7d3b1eb80e781737f5ec5bed8cc10faca1ca0c` (2023-03-27). 70 stars.
- Files: `esp32-4-channel-relays.kicad_sch`, `esp32-4-channel-relays.kicad_pcb`,
  Gerbers. No firmware, no BOM file in repo.
- Parsed: 63 schematic instances, 63 PCB footprints, 91 nets.
- Design: USB-C → F1 500 mA polyfuse → AMS1117-3.3 → ESP32-WROOM-32 (U4) + CH340C (U2).
  Relays K1–K4 (SRD-05VDC-SL-C) driven by BC547A (Q2–Q5) via PC817 optocouplers (U5–U8),
  flyback diodes D3/D5/D7/D9 (1N4007), contacts to screw terminals J1–J4.

### Findings

1. **RISK — F1 500 mA polyfuse is at the load limit.** Worst case: 4 relay coils
   ~71 mA each = ~284 mA, plus ESP32 peak (~160–240 mA at 3.3 V through the LDO,
   ≈110–160 mA at 5 V), plus CH340C and LEDs. Total ≈ 450–500 mA against a 500 mA
   fuse, before inrush. All four relays on + Wi-Fi transmit can nuisance-trip the fuse.
   Evidence: `+5V` net in PCB contains F1.2, K1–K4.A1, U1.3, U2.16, R9/R11/R13/R15.2.
2. **RISK — Relay drive chain has thin margin.** Optocoupler LED current is only
   ~3 mA: +5 V → R9/R11/R13/R15 1 kΩ → PC817 LED → series diode D2/D4/D6/D8 →
   ESP32 GPIO pulled low. PC817 CTR at 3 mA is ~40–80%, so BC547 base current is
   ~1.2–2.4 mA against ~0.7–1.4 mA needed to saturate at the 71 mA coil current.
   BC547A absolute max Ic is 100 mA vs 71 mA coil — works, ~30% margin, but a
   low-CTR optocoupler or a hot board can leave a relay half-driven.
   Evidence: `/IO_5` net = D8.1 + U4.29; `Net-(D8-A)` = U8.2 + D8.2;
   `Net-(R15-Pad1)` = U8.1 + R15.1; `Net-(Q5-B)` = Q5.2 + R16.2.
3. **WEAKNESS — GPIO0 (`/IO_0`) has no external pull-up.** The net contains only
   SW2.1, U4.25, C9.2, Q1.6 — no resistor to +3.3 V. Boot strapping relies on the
   ESP32's weak internal pull-up. It boots in practice, but it is the one strapping
   pin with no external pull-up on this board.
4. **Correct (Extrude should NOT flag these):**
   - EN (`/RESET` net): R8 10 k pull-up to +3.3 V, C8/C5, SW1 reset button to GND,
     Q1 (MBT3904DW1) auto-reset from CH340 DTR/RTS via R6/R7 10 k. Correct.
   - USB-C: CC1/CC2 pulled down with R2/R3 5.1 k (nets `Net-(USB1-CC1)` /
     `Net-(USB1-CC2)`), D+/D− 22 Ω series R4/R5, PRTR5V0U2X ESD (U3), VBUS through
     F1. Correct. SBU1/SBU2 unconnected is normal.
   - AMS1117: C1/C2 22 µF on input/output. Correct.
   - Flyback diodes D3/D5/D7/D9: cathode to +5 V, anode to coil low side. Correct.
     D1 is the power LED (anode via R1 2 k to +5 V, cathode to GND, ~1.5 mA — dim
     but working). D2/D4/D6/D8 series diodes are deliberate: they stop the 5 V opto
     LED from partially turning on when the 3.3 V GPIO is high.
   - Relay contacts: K1–K4 COM/NO/NC all routed to J1–J4 screw terminals.
   - Unconnected U4 pads (IO2, IO12, IO15, IO32–IO35, etc.) are unused GPIOs — not bugs.

### Not checked
- No ERC/DRC run (no KiCad in VM). No firmware to cross-check GPIO usage. Relay coil
  current assumed 71 mA from SRD-05VDC-SL-C datasheet — not measured. Copper/track
  widths and clearances not checked.

---

## 2. bench-psu-monitor — ESP32 + INA3221 3-channel PSU monitor (strongest bug set)

- URL: https://github.com/fixthepixel/bench-psu-monitor
- Branch: `main`. SHA: `cd87301f7cb41831cc9ac8a3b7a62158e6dcd979` (2026-09-15). 6 stars.
- Files: `bench-psu-monitor.kicad_sch`, `bench-psu-monitor.kicad_pcb`,
  `bench-psu-monitor.ino`, `ibom.html`, Gerbers. No BOM CSV.
- Parsed: 37 schematic instances, 41 PCB footprints, 46 nets.
- Design: ESP32 DevKit (U2, 30-pin) + INA3221 (U1) measuring 3 rails through
  RS1/RS2/RS3 0.01 Ω shunts, I2C SDA GPIO21 / SCL GPIO22, CAL button GPIO0,
  Wi-Fi button GPIO23 (CTLSW), PWR LED GPIO2.

### Findings

1. **BUG — INA3221 A0 address pin floats as built; firmware assumes address 0x40.**
   The `/ADDR` net contains only U1.5, JP1.1, JP2.1. JP1 and JP2 are
   `SolderJumper_2_Open` parts: JP1 bridges A0 to +3.3 V via R16 100 Ω
   (`Net-(JP1-B)` = JP1.2 + R16.1), JP2 bridges A0 to GND via R17 100 Ω
   (`Net-(JP2-B)` = R17.1 + JP2.2). Both jumpers are open by default, so A0 is
   floating and the INA3221 I2C address is undefined. Firmware
   (`bench-psu-monitor.ino:15`) defines `INA3221_ADDR 0x40` and calls
   `ina3221.begin(INA3221_ADDR, &Wire)` at line 111 — 0x40 requires A0 = GND,
   i.e. JP2 bridged. As built with both jumpers open, `begin()` fails and the
   board hangs in setup. Fix: bridge JP2 (or add a pull-down).
2. **BUG — Firmware only uses channel 1 of a 3-channel monitor.** Firmware calls
   `setShuntResistance(CH1, 0.01)` and reads CH1 only (line 44:
   `zeroOffset_mA = ina3221.getCurrentAmps(CH1) * 1000.0`). The hardware has three
   shunts (RS1/RS2/RS3 0.01 Ω) and three IN± pairs wired to U1 (pins 1/2, 11/12,
   14/15), but CH2/CH3 are never measured. Latent second bug: the Adafruit
   library defaults to a 0.1 Ω shunt, so any later CH2/CH3 read would report
   current 10× too low unless configured.
3. **Correct (Extrude should NOT flag these):**
   - I2C: SDA = J6.2 + U1.7 + U2.26 (GPIO21) + R10.2; SCL = J6.4 + U1.6 + U2.29
     (GPIO22) + R9.2; R9/R10 are 10 k pull-ups to +3.3 V. Correct, matches firmware
     `Wire.begin(I2C_SDA, I2C_SCL)`.
   - INA3221 VPU (pin 16) tied to +3.3 V — correct for the alert pull-up supply.
     WARNING/CRITICAL/PV/TC pins (8–10, 13) wired. VS (pin 4) +3.3 V.
   - CTLSW: R8 10 k pull-up to +3.3 V + C7 0.1 µF debounce cap to GND + J4 button
     to U2.30 (GPIO23). Correct.
   - PWRLED: GPIO2 (U2.19) → R15 330 Ω → J5.1, J5.2 to GND. Correct.
   - U2 EN (pad 15) unconnected in the PCB — the DevKit module has its own EN
     pull-up on-module, so this is fine.
   - J6 header pins expose spare GPIOs (VIN, GPIO14/27/26/25, +3.3 V, GND) — not bugs.

### Not checked
- No ERC/DRC run. Shunt power rating (0.01 Ω at full rail current — package size
  not verified from the footprint). Whether the iBOM/Gerbers match the PCB file.
  INA3221 alert-pin pull-ups (WARNING/CRITICAL nets) not traced to a resistor value.

---

## 3. STM32F4-Reference-PCB — STM32F405RGT6 + MP2359 buck (PCB-only)

- URL: https://github.com/pms67/STM32F4-Reference-PCB
- Branch: `master`. SHA: `e0d1d8de53d43a6b82d834afdee54867cc44e89b` (2020-10-27). 195 stars.
- Files: `STM32F4-Reference-PCB.kicad_pcb` (KiCad 5.1, `module` not `footprint`),
  BOM CSV, Gerbers. **No schematic in the repo, no firmware.**
- Parsed: 54 PCB footprints, 79 nets.
- Design: U2 STM32F405RGT6 (LQFP-64) + U1 MP2359DJ buck (5 V → 3.3 V), Y1 16 MHz
  crystal, USB via U3 USBLC6, SWD on J2 (2×05, 1.27 mm).

### Findings

1. **WEAKNESS — NRST has no pull-up resistor or capacitor.** The `NRST` net contains
   only J2.10 and U2.7. The board relies on the STM32's weak internal pull-up and
   on the debugger driving reset. ST recommends an external pull-up + 100 nF cap;
   without them the reset line is noise-sensitive when running standalone.
2. **Correct (Extrude should NOT flag these):**
   - Buck FB divider: R3 47 k / R4 15 k on `BUCK_FB` (R3.2 + R4.1 + U1.3).
     Vout = 0.81 × (1 + 47/15) ≈ 3.35 V — correct for a 3.3 V rail.
   - Buck EN divider: R1 100 k / R2 68 k on `BUCK_EN`, R1.1 on `BUCK_IN` (5 V).
     EN ≈ 5 × 68/168 ≈ 2.0 V, above the MP2359 EN threshold (~1.2 V). Correct.
   - Buck input: `BUCK_IN` = C1.1 + FB1.1 + R1.1 + U1.5 (ferrite bead + 10 µF).
     SW node: `BUCK_SW` = C4.1 + D2.1 (B5819W) + L1.1 (10 µH) + U1.6. Correct.
   - BOOT0: SW1 SPDT selects +3.3 V or GND through R7 10 k (`Net-(R7-Pad1)` =
     SW1.2 + R7.1; SW1.1 on +3V3, SW1.3 on GND). Correct.
   - SWD: SWDIO (J2.2 + U2.46), SWCLK (J2.4 + U2.49), SWO (J2.6 + U2.55),
     NRST (J2.10 + U2.7) all routed to J2. J2 pads 7/8 are single-pad nets, but
     pins 7/8 are NC on a standard 10-pin SWD connector — not bugs.
   - USB: D+/D− (U2.45/44) to U3.4/6 (USBLC6 ESD). Correct.
   - VDDA: `+3.3VA` = C11.1 + C12.1 + L2.2 + U2.13 (ferrite + 1 µF + 10 nF). Correct.
   - VCAP: C13/C14 2.2 µF on U2 pads 31/47. Correct per STM32F4 datasheet.
   - HSE: Y1 16 MHz + C15/C16 12 pF; BOOT0, HSE_IN/OUT (pads 5/6), I2C1
     SCL/SDA (pads 58/59), USART3 TX/RX (pads 29/30) all present.
   - Decoupling: C2/C3/C5–C10 100 nF across the 3.3 V rail; C6–C10 on U2 VDD pins.

### Not checked
- **No schematic exists, so no schematic-vs-PCB check is possible at all.** No ERC/DRC
  run. USB DP pull-up value and USB series resistors not resolved from the PCB nets
  (R8 47 Ω and R9 1.5 k could not be tied to the USB nets with certainty — do not
  claim them as the USB pull-up/series). Crystal load-capacitor value vs the crystal's
  CL (CL not in BOM). No firmware to cross-check pin use.

---

## 4. silkscreen-pcb — ESP32-S3 e-paper reader (largest, most complex board)

- URL: https://github.com/iandchasse/silkscreen-pcb
- Branch: `master`. SHA: `4530931d932cf760c8afc065327d88db94a18671` (2026-11-02). 591 stars.
- Files: `silkscreen_pcb.kicad_sch`, `silkscreen_pcb.kicad_pcb`, `BOM.md`.
  No firmware, no Gerbers in repo.
- Parsed: 185 schematic instances, 189 PCB footprints, 136 nets.
- Design: U4 ESP32-S3-WROOM-1 + e-paper FFC (J2, 24-pin) + TPS2116 power mux (U2)
  + TLV75533 LDO (U3) + DW01A/FS8205A Li-ion protection (U5/Q1) + DS3231MZ (U13)
  and RV-8263-C7 (U14) RTCs + TPD4E1U06 ESD (U8).

### Findings

1. **SUSPECT — DW01A battery-protection FET gates may be floating (needs footprint
   proof).** DW01A OD (pin 1) → Q1 pad 6, OC (pin 3) → Q1 pad 4
   (`Net-(U5-OD)` = Q1.6 + U5.1; `Net-(U5-OC)` = Q1.4 + U5.3), while Q1 pads 2
   and 5 are unconnected. Per the standard FS8205A pinout (1=S1, 2=G1, 3=S2,
   4=D2, 5=G2, 6=D1), pads 2/5 are the FET gates — so the DW01A would be driving
   the drains, the gates would float, and the protection could never cut the
   battery off. The schematic symbol in the repo carries no pin names, so this
   is **not proven**: if the repo's footprint numbers the part differently, the
   wiring is fine. Extrude should flag this as "verify footprint pinout", not as
   a certain bug.
2. **Observation, not a bug — two RTCs on one I2C bus.** U13 DS3231MZ and U14
   RV-8263-C7 both sit on I2C_SDA/SCL (U13.7/8, U14.7/8). Addresses differ
   (0x68 vs 0x51), so no conflict. DS3231 VBAT (pin 6) is tied to 3V3, so it has
   no battery backup — the RV-8263 is presumably the backed-up one. Unusual,
   not wrong.
3. **Correct (Extrude should NOT flag these):**
   - Power path: TPS2116 (U2) VIN1 = USB_VBUS, VIN2 = P+ (battery), VOUT → LDO_IN
     → TLV75533 (U3, EN tied to VIN = always on) → 3V3.
   - I2C: 2.2 k pull-ups R47/R48, 0 Ω series R45/R46, ESD via U8 TPD4E1U06
     (U8.3/4 on SCL/SDA). Correct.
   - E-paper: EPD_BUSY/CS/DC/RST routed through 33 Ω series R31–R34 to J2;
     EPD_RST has a 10 k pull-up (R5). Correct.
   - U13 32KHZ/INT/RST unconnected and U14 CLKOUT/INT unconnected — alarms and
     clock-out unused. Not bugs. U14 pin 1 is NC.
   - J2 pads 1/4/6/7 and J3 pads 3/4 unconnected — FFC connector spare pins;
     the symbols carry numbers only, no pin names, so whether they are NC is
     **not checked**, but unconnected FFC spares are normal.

### Not checked
- No ERC/DRC run. TPS2116 current-limit resistor value (R38 300 k / R51 100 k)
  not verified against the datasheet formula. Whether J2/J3 unconnected FFC pins
  are NC (pin names not in the symbol). The FS8205A footprint pinout — the one
  thing finding 1 hinges on. No firmware to cross-check GPIO use. E-paper panel
  pin mapping against the actual panel datasheet.

---

## 5. Doorman — ESP32-S3 intercom gateway (best-documented repo)

- URL: https://github.com/AzonInc/Doorman
- Branch: `master`. SHA: `fdec5c030e77bb8e0219d745cc0282139c96836c` (2026-01-22). 253 stars.
- Files: `doorman.kicad_sch`, `doorman.kicad_pcb`, BOM, ESPHome firmware,
  `docs/en/reference/gpio.md` (rev 1.6 GPIO map). No Gerbers in repo.
- Parsed: 41 schematic instances, 44 PCB footprints, 60 nets.
- Design: U1 ESP32-S3-WROOM-1 + AP63203WU buck (U2) + USB-C + GAQY252G3S
  solid-state relay (U3) for the doorbell + WS2812B RGB LED (D3) + bus interface
  (BUS_TX via Q1 BC817, BUS_RX via ADC divider on GPIO9).

### Findings

1. **WEAKNESS — IO0 (`/FLASH`) has no external pull-up.** The net contains only
   SW2.1 and U1.27. Boot strapping relies on the ESP32-S3 internal pull-up.
   Same class as repo 1, finding 3.
2. **Correct (Extrude should NOT flag these):**
   - EN (`/EN`): R1 10 k pull-up + C1 100 nF + SW1 reset button. Correct.
   - SSR: GAQY252G3S pin 1 from GPIO42 (`SSR` net = U3.1 + U1.35), pin 2 via
     R9 150 Ω to GND → LED current ≈ (3.3 − 1.2)/150 ≈ 14 mA, within rating.
     Output pins 3/4 → RELAY_WIRE1/2 (J2.9/8). Correct.
   - WS2812B: VDD on +3.3 V, DIN from GPIO38 (`LED_RGB` = D3.4 + U1.38),
     DOUT unconnected (it is the only LED in the chain). Correct.
   - Bus TX: GPIO8 → R2 1 k → Q1 BC817 base (`Net-(Q1-B)` = Q1.1 + R2.1),
     emitter to GND, collector pulls the bus low. Correct.
   - Bus RX: ADC_IN (GPIO9, U1.7) via divider R5 1 M + R6 147 K per
     `docs/en/reference/gpio.md` — 24 V bus → ~3.07 V at the ADC, just under
     3.3 V. Correct per the project's own doc.
   - Buck AP63203: EN (pin 2) tied to IN (pin 3) on `Net-(D1-K)` = always on;
     BST cap C5 100 nF between SW (pin 5) and BST (pin 6); L1 3.9 µH;
     C3 470 µF + C4 10 µF output. Correct.
   - USB-C CC pull-downs R3/R4 5.1 k. Correct.
   - IO40/IO41 routed to J2.6/7 (spare terminal pins). Not bugs.

### Not checked
- No ERC/DRC run. AP63203 FB divider values (output voltage) not verified
  numerically from the PCB nets. ESP32-S3 strapping pins IO3/IO45/IO46
  (module-internal handling assumed, not verified). ESPHome YAML not fully
  cross-checked against every GPIO in `gpio.md`. The exact ADC divider tap
  resistors on the PCB net could not be fully resolved (refs R8/R11 10 k also
  appear on the ADC_IN net in the parse) — the 1 M + 147 K values are per the
  project's gpio.md, not independently proven from the PCB.

---

## 6. sniffer — ESP32 air-quality sensor (PCB-only, no schematic, no firmware)

- URL: https://github.com/kylemanna/sniffer
- Branch: `master`. SHA: `037c8c2bc562e95e62fe757d1dfc7d8d68e9aca9` (2026-07-16). 166 stars.
- Files: `sniffer.kicad_pcb` (KiCad 5.1), Gerbers, `README.md`, `esphome/README.md`.
  **No schematic, no firmware in the repo.** Note: `esphome/README.md` tells the
  builder to copy a `sniffer.template.yaml` into ESPHome, but that template file
  is **not in the repo** at the checked SHA, and the main README's "Upload ESPHome
  YAML file" checkbox is ticked anyway. The author's README also claims the built
  unit "measures within 1% of 3x different PurpleAir sensors", i.e. the author's
  own build works — which suggests the CJMCU-680 module (or the author's wiring)
  resolves the floating SDO/CS in practice, but it is not proven from the repo files.
- Parsed: 22 PCB footprints, 32 nets.
- Design: U1 TTGO-T-Display (ESP32 + 1.14″ LCD) + J1 CJMCU-680 (BME680 breakout)
  + J2 PMSA003 (PMS5003) + Q1/Q2 Si2371EDS power switches + JP4–JP7 solder jumpers.

### Findings

1. **RISK — BME680 SDO and CS float (J1 pads 5/6 single-pad nets).** J1 is the
   CJMCU-680 breakout (VCC/GND/SCL/SDA/SDO/CS). SDO selects the I2C address
   (0x76 if GND, 0x77 if VDDIO) and CS selects I2C vs SPI mode; both float on
   this PCB. If the CJMCU-680 module has no on-board pull-ups, the sensor may
   not answer on I2C at all, or may answer at an unpredictable address. Whether
   the module pulls SDO/CS is **not checked** (module schematic not in repo), so
   this is a risk, not a proven bug.
2. **Correct / plausible (Extrude should NOT flag these):**
   - I2C: U1 SCL/SDA pads 22/21 to J1 — TTGO-T-Display I2C is GPIO21/22. Correct.
   - Power switches: Q1/Q2 gates driven from U1 pads 26/27 via JP5/JP6 jumpers,
     R1/R2 100 k gate pull-ups; PMS_PWR (U1 pad 12), BME_PWR (U1 pad 13). Plausible.
   - J2 PMSA003 pads 6/8 unconnected — the PMS5003 8-pin header has NC pins;
     exact pinout not verified (see below), most likely fine.
   - JP4–JP7 solder jumpers bridged (per README, they select the power-switch
     routing). C1–C3 10 µF sensor decoupling present.

### Not checked
- **No schematic and no firmware in the repo, so no schematic-vs-PCB check and no
  firmware-to-pin check is possible at all.** No ERC/DRC run. Whether the CJMCU-680
  module pulls SDO/CS (decides finding 1). Whether J2 pads 6/8 are NC on the
  PMS5003 pinout. Q1/Q2 Si2371EDS channel polarity (P vs N) not verified.
  I2C pull-up values not verifiable without a schematic.

---

## 7. ESP32-Camera-PCB — ESP32 camera (breakout carrier, not a discrete design)

- URL: https://github.com/UnsignedArduino/ESP32-Camera-PCB
- Branch: `main`. SHA: `d467da91f7a4d41bf72a31ffbbc49c9d9091792f` (2023-02-03). 8 stars.
- Files: `ESP32 Camera PCB.kicad_sch`, `ESP32 Camera PCB.kicad_pcb`. No firmware,
  no BOM, no Gerbers.
- Parsed: 17 schematic instances, 17 PCB footprints, 68 nets.
- Design: a carrier board for breakout modules — B2 ESP32 dev board, B5 ArduCam
  OV2640, B3 Adafruit MicroSD, B1 ST7735 TFT, B6 RTC, B4 I2C level shifter,
  B7 PowerBoost 500, SW1–SW5 buttons. Only discretes: R1/R2 100 k, C1 10 µF.

### Findings

1. **RISK — PowerBoost 500 USB charge input unconnected (B7 pad 8).** B7 pin 8 is
   the USB charging input of the PowerBoost 500; it is unconnected, so the LiPo
   can never be charged on-board — the battery must be removed and charged
   externally. LBO (low-battery output, B7 pad 3) is also unconnected, so there
   is no low-battery warning. If the builder intended USB charging, this is a
   missing connection; if they charge externally, it is a deliberate limitation.
   Either way Extrude should surface it.
2. **Correct (Extrude should NOT flag these):**
   - SD SPI is correct: B3 CS (pin 2) → B2 pad 29 = GPIO5; DI (pin 3) → B2 pad 21
     = GPIO23 (MOSI); DO (pin 4) → B2 pad 27 = GPIO19 (MISO); CLK (pin 5) → B2 pad
     28 = GPIO18 (SCK). Correct VSPI wiring. B3 pad 1 (CD) and pad 7 (3.3V_OUT)
     unconnected are fine — CD unused, 3.3V_OUT is an output.
   - Camera SPI is correct: B5 CS → GPIO15 (B2.35), MOSI → GPIO27 (B2.11),
     MISO → GPIO14 (B2.12), SCK → GPIO13 (B2.15); SDA/SCL go via the B4 level
     shifter to the B6 RTC.
   - Battery sense divider is correct: R1 100 k (BAT → GPIO36) + R2 100 k
     (GPIO36 → GND) = 2:1 divider, full-charge 4.2 V reads as 2.1 V at the ADC.
     (`Net-(B2-Pad3)` = R2.2 + R1.1 + B2.3; `Net-(B7-Pad6)` = B7.6 + R1.2.)
   - SW2 (SPDT power switch): B7.5 (EN) → SW2.2, SW2.3 → GND, SW2.1 unconnected.
     Sliding to GND disables the PowerBoost; the open position leaves EN floating
     (internal pull-up = enabled). Works as a power switch.
   - B6 RTC 32K/SQW unconnected — alarms unused, fine. B2 unconnected pads are
     unused ESP32 GPIOs — not bugs. C1 10 µF is the only bulk cap; the modules
     carry their own regulation/decoupling.

### Not checked
- No ERC/DRC run. No firmware in the repo, so the pin mapping was verified from
  schematic nets only, not against code. B8 header function not identified.
  Whether the builder intended on-board USB charging (decides finding 1 severity).

---

## What Extrude should catch (scoring checklist)

| Test | Expected Extrude verdict | Repo |
|------|--------------------------|------|
| INA3221 A0 floating vs firmware 0x40 | **BUG** — address undefined, `begin()` fails | 2 |
| Firmware uses only CH1 of 3 hardware channels | **BUG** — CH2/CH3 unmeasured | 2 |
| DW01A OC/OD to Q1 pads 4/6, pads 2/5 floating | **FLAG as "verify footprint pinout"** (suspect, not proven) | 4 |
| BME680 SDO/CS floating, no schematic/firmware | **RISK** — address/mode undefined | 6 |
| PowerBoost USB charge input unconnected | **RISK / surface it** | 7 |
| F1 500 mA vs ~450–500 mA worst-case load | **RISK** — fuse at limit | 1 |
| Relay drive chain (3 mA opto, CTR-limited base) | **RISK** — thin margin | 1 |
| NRST with no pull-up or cap | **WEAKNESS** | 3 |
| GPIO0 / IO0 with no external pull-up | **WEAKNESS** (×2 boards) | 1, 5 |
| SD SPI, camera SPI, battery divider, buck FB/EN dividers, BOOT0 switch, SWD routing, I2C pull-ups, USB-C CC resistors, SSR drive, WS2812B wiring | **PASS — do not flag** | 1, 2, 3, 5, 7 |
| "Not checked" items (no ERC/DRC, no schematic for repos 3 & 6, no firmware for 1, 3, 4, 6, 7) | **Must say "not checked", never "passed"** | all |

## Global not-checked list (applies to the whole audit)

- No KiCad installed in this VM: **no ERC and no DRC was run on any repo.** Any
  Extrude ERC/DRC claim cannot be compared against a ground-truth ERC/DRC here.
- No Gerber viewer check; Gerber-vs-PCB consistency not verified.
- Track widths, clearances, copper pours, and thermal reliefs not checked.
- Component datasheet values (relay coil current, crystal CL, shunt power rating,
  TPS2116 current limit) taken from part numbers, not measured.
- Repos 3 and 6 have no schematic; repos 1, 3, 4, 6, 7 have no firmware in-repo.
