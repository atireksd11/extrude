# Bluetooth Audio Transmitter — PCB audit, from the actual files
Repo: Shashvat1333/Bluetooth-Audio-Transmiter
Commit checked: f5c2b29347f9eaced1b67b3011b986baca8b7777
Date checked: Nov 7, 2026, by Muse (not ChatGPT)

Method: cloned the repo, read hardware/Bluetooth-Audio-Transmiter.kicad_pcb (KiCad 10.0, 2-layer, 1.6 mm), .kicad_sch, firmware.ino, and the repo's own Gerbers/DRC.rpt and ERC.rpt (Oct 11, 2026). No KiCad was installed here, so DRC/ERC were not re-run fresh — the repo's own reports were cross-checked against the .kicad_pcb file, and they match the pads/nets in the file.

Verdict: DO NOT ORDER YET. At least 3 blocking problems, plus 11 DRC errors.

## Blocking

### 1. I2S WS is wrong in firmware, and GPIO28 does not exist
- firmware.ino, lines 298-307: bck_io_num = 14, ws_io_num = 28, data_in_num = 34
- PCB / schematic, verified in the .kicad_pcb file:
  - U4 PCM1808 pad 7 LRCK -> Net-(U3-IO27) -> U3 pad 12
  - U4 pad 8 BCK -> Net-(U3-IO14) -> U3 pad 13
  - U4 pad 9 DOUT -> Net-(U3-IO34) -> U3 pad 6
- So BCK=14 and DATA_IN=34 match the board. WS does not: the board wires LRCK to IO27, firmware says 28.
- GPIO28 does not exist on ESP32-WROOM-32UE. Fix: change ws_io_num to 27, in firmware only, no PCB change needed for this one.

### 2. PCM1808 has no system clock, and no clock master
- U4 pad 6 SCKI: unconnected-(U4-SCKI-Pad6) in the .kicad_pcb file.
- U4 pad 1 VREF: unconnected-(U4-VREF-Pad1). VREF normally needs a capacitor to AGND.
- U4 pad 10 MD0 -> GND, pad 11 MD1 -> GND.
- Firmware: I2S_MODE_SLAVE | I2S_MODE_RX, sample_rate 44100, 32-bit. ESP32 is a clock slave.
- If PCM1808 is also a slave (MD0/MD1 grounded), neither device generates BCK/LRCK. With SCKI unconnected, there is no system clock at all.
- Fix: decide the clock master in the schematic, route SCKI, connect VREF with its capacitor, and make firmware match that choice. Do not order until BCK/LRCK/SCKI are all sourced by one device.

### 3. DRC: 11 solder-mask bridge errors, all on J3 USB-C
From Gerbers/DRC.rpt, all at J3, around x 219.435 mm, y 59.9-66.3 mm:
- Pads involved: A1_B12 GND, A4_B9 VBUS, A5 CC1, A6 DP1, A7 DN1, B5 CC2, B6 DP1, B7 DN1, B8 SBU2 (unconnected), B4_A9 VBUS (unconnected), B1_A12 GND.
- Rule: board setup solder mask min width.
- Setup in the .kicad_pcb file: pad_to_mask_clearance 0, allow_soldermask_bridges_in_footprints yes.
- Risk: solder bridging VBUS to GND, or DP to DN, during assembly — a short.
- Fix: give the USB-C footprint proper mask clearance, turn off soldermask bridges for this footprint, re-run DRC until 0.

### 4. DRC: 4 unconnected items — ESP32 ground and VBUS are broken
From Gerbers/DRC.rpt:
- Track Net-(J1-GND) at (147.65, 72.125) to Pad 1 [Net-(J1-GND)] of U3 at (153.24, 72.15)
- Pad 1 of U3 to Track Net-(J1-GND) at (161.5, 75.5)
- Pad 39 [Net-(J1-GND)] of U3 at (159.18, 66.3) to Pad 1 of U3
- Track Net-(J3-VBUS) at (208.5, 68.0) to Track Net-(J3-VBUS) at (146.35, 73.6)
- In plain terms: U3 GND pads 1 and 39 are not actually connected to the GND track, and the VBUS track is split in two with a gap.
- Fix: route GND to U3 pads 1 and 39, and join the VBUS segments. Re-run DRC.

## ERC: 3 errors, 1 warning (from Gerbers/ERC.rpt)
- [power_pin_not_driven] U1 AP2112K-3.3, Pin 2 GND, power input not driven.
- [pin_not_connected] U3 Pin 7 IO35, input, not connected.
- [pin_not_driven] U3 Pin 7 IO35, input pin not driven.
- [lib_symbol_mismatch] J2 SJ-3523-SMT-TR symbol does not match the library copy.
- IO35 is unconnected in the PCB too: unconnected-(U3-IO35-Pad7). If IO35 is unused, mark it no-connect in the schematic. Do not leave it as an ERC error.

## Power / layout, verified in the .kicad_pcb file
- 20 footprints, 257 track segments, all 0.2 mm wide. 233 on F.Cu, 24 on B.Cu. 16 vias, 0.6 mm / 0.3 mm drill.
- No copper zone / ground plane was found in the .kicad_pcb file (no top-level zone). GND is routed as 87 separate 0.2 mm tracks.
- VBUS: 28 segments at 0.2 mm. U1-VOUT (3.3 V): 21 segments at 0.2 mm.
- 0.2 mm is thin for VBUS, 3.3 V, and GND on a board with an ESP32 that has large current peaks during Bluetooth TX. Risk: voltage drop and brownout.
- Fix: widen power and GND tracks, add a GND zone, ideally on B.Cu.
- USB-C B4 VBUS: unconnected-(J3-VBUS__1-PadB4_A9), while A4_B9 is VBUS. Only one VBUS pin is routed. If the cable is flipped, power may be on the unrouted B4 pin. Tie A4 and B4 VBUS together. SBU1/SBU2 unconnected is normal for USB 2.0 only.
- Decoupling distance, measured from footprint positions in the file: C3 0.1 uF is at (161.5, 75.5), U3 is at (161.65, 63.4) — about 12 mm away. That is far for ESP32 decoupling. Move a 0.1 uF cap close to U3 3V3/GND pins.

## Firmware, verified in firmware.ino
- GPIO28 error, see Blocking 1. Fix to 27.
- Lines 310-312: i2s_driver_install() and i2s_set_pin() return values are not checked. If I2S fails, the code continues to Bluetooth init. Check both, stop with a diagnostic on failure.
- I2S is slave/RX, 44100 Hz, 32-bit. That only works if PCM1808 is master and supplies BCK/LRCK/SCKI — see Blocking 2.

## BOM, verified in BOM*.csv / BOM.md
- Ceramic capacitor assortment kit and resistor kit: no exact values, tolerances, or voltage ratings. Order exact parts, not kits, for a board you will manufacture.
- BC817 x2: no circuit reference or purpose documented in the BOM.
- Mini optical audio adapter: does not belong in the AUX analog path. README says USB-C powered AUX transmitter, BOM includes an AUX-to-Toslink adapter that does not do that conversion by itself. Remove it.
- Total in BOM.csv: $52.25 parts + $12 tax/shipping = $64.25.

## What ChatGPT got right, and what it could not do
- ChatGPT correctly found the GPIO28 bug, the missing error checking, and the BOM problems, from README/firmware text.
- ChatGPT admitted it could not access the .kicad_pcb file, could not inspect PCB/schematic/Gerbers, and asked for an upload / GitHub connection. Its PCB section was a generic "I would check" list, not findings.
- This audit is the opposite: it is from the .kicad_pcb, .kicad_sch, DRC.rpt, and ERC.rpt in the repo. The GPIO27 correction, SCKI/VREF unconnected, the 11 J3 mask errors, the 4 unconnected DRC items, and the 0.2 mm / no-ground-plane finding are all from those files.

## Not checked
- Antenna keepout: U3 is ESP32-WROOM-32UE with an external U.FL antenna, so there is no on-board antenna keepout to check in the same way. Copper under the module was not measured here.
- Clearance/shorts beyond the repo DRC.rpt: no fresh KiCad DRC run was done here. Re-run DRC/ERC in KiCad after fixing the items above.
- Audio quality, Bluetooth pairing, and power measurements: need the physical board and a scope, not files.
