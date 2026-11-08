# Extrude live-site test — full audit

Date: 2026-11-08
Live site: https://extrude.onrender.com (Render Free, draft PR #5, commit c387978, unmerged)
Tester: Muse, browser task 2:29–3:15 PM EST (45 min, runtime-measured)
Ground truth: `test-repos-ground-truth-2026-11-08.md` — 7 repos, independently audited by parsing KiCad files, pad-to-net maps, symbol pin tables, and firmware text. No KiCad was installed in the ground-truth VM, so no ERC/DRC was run there; anything needing ERC/DRC, a Gerber viewer, or footprint libraries was marked "not checked" in ground truth.

## Headline verdict

Extrude imports real hardware repos and describes what changed between commits. It does not audit electrical design.

- **0 of 10 ground-truth checks caught.** None of the 2 proven bugs, none of the 4 risks, none of the 2 weaknesses, and not the 1 suspect was detected, surfaced, or even mentioned as a check.
- **Native KiCad DRC / ERC / parity failed in 12 of 12 audits run.** Every audit ended "Partial audit saved. See coverage for what still needs checking." No audit ever completed fully. Nothing was ever marked "passed".
- **All 660 findings on hardware commits were descriptive diff observations** — footprint added/moved, symbol added, value changed, pad-net changed — with no severity, warning, or judgement. The audit never concluded anything was wrong, including a "TBD" inductor value and an unspecified "D_Zener".
- **AI review was unavailable in every audit:** "Model provider unavailable. All audit findings and connections remain usable." (gpt-4.1-mini, no credentials on the Render Free instance — expected on this deployment, not a code bug by itself.)
- **No false positives on the correct-design list, but also no passes.** Extrude did not flag the things ground truth says are correct (buck dividers, USB-C CC resistors, I2C pull-ups, SSR drive, SPI wiring). It also never said they passed — it said "unavailable", "failed", or nothing. That is honest, and it is not a passing audit.

This is consistent with, and worse in scope than, the Nov 8 Codex audit of main: the false-pass bug is still live in the code, but in this live run the DRC/ERC/parity path failed loudly instead of passing silently. The user-facing result is the same: a builder gets no electrical verdict.

## Scorecard — ground-truth checklist vs Extrude

| # | Check | Expected | Extrude | Repo |
|---|-------|----------|---------|------|
| 1 | INA3221 A0 floats as built; firmware assumes 0x40, `begin()` hangs | BUG | Missed — A0 never mentioned; JP1/JP2 listed only as neutral added jumpers, no address decoding; firmware checks "unavailable" | 2 bench-psu-monitor |
| 2 | Firmware uses only CH1 of 3 hardware channels; CH2/CH3 never read, latent 10x-low current | BUG | Missed — firmware file never analysed; CH1/CH2/CH3 listed as plain symbol additions | 2 |
| 3 | DW01A OD/OC to FS8205A pads 4/6, pads 2/5 floating | FLAG "verify footprint pinout" (suspect) | Missed — DW01A appears only as a BOM row-shift artefact; FS8205A never mentioned; filter value changes listed neutrally | 4 silkscreen-pcb |
| 4 | BME680 SDO/CS float; I2C address/mode undefined | RISK | Missed — J1 CJMCU-680 is a plain "Footprint added"; no schematic symbol analysis, no connectivity check | 6 sniffer |
| 5 | PowerBoost 500 USB charge input unconnected; LiPo can never charge on-board | RISK / surface it | Missed — B7 listed only as "Footprint added" / "symbol added"; no finding mentions its USB/charge pins | 7 ESP32-Camera-PCB |
| 6 | F1 500 mA polyfuse vs ~450–500 mA worst-case load | RISK | Missed — no load / fuse analysis at all | 1 esp32-4-channel-relays |
| 7 | Relay drive chain: ~3 mA opto LED, CTR-limited base, 30% margin | RISK | Missed — no drive-current analysis | 1 |
| 8 | NRST no pull-up or cap | WEAKNESS | Missed — no schematic analysis (PCB-only repo, no adapter path) | 3 STM32F4-Reference-PCB |
| 9 | GPIO0 / IO0 no external pull-up (x2 boards) | WEAKNESS | Missed — no strapping-pin check | 1, 5 Doorman |
| 10 | Correct designs: SD/camera SPI, battery divider, buck FB/EN dividers, BOOT0, SWD, I2C pull-ups, USB-C CC, SSR drive, WS2812B | PASS — do not flag | Not flagged (good), but never passed either — "unavailable" / "failed" / silent | 1, 2, 3, 5, 7 |
| 11 | "Not checked" items (no ERC/DRC, no schematic for repos 3 & 6, no firmware for 1, 3, 4, 6, 7) | Must say "not checked", never "passed" | Passed this test — it said "Partial audit", "failed", "unavailable", never "passed" | all |

Score: **0 caught, 0 false-flagged correct designs, 0 passed.** The "not checked" language is the one part that behaved correctly in this run.

## Per-repo results (live site)

All 7 imports succeeded, no errors, no sign-in required, no code changed. Site was already awake on arrival.

### 1. leomanangka/esp32-4-channel-relays — main, 3c7d3b1, 70 stars, 26 files
- HEAD ("Update README.md", 1 changed path): 0 findings.
- "Add schematic" (schematic.pdf added): 0 findings; PDF has no audit adapter.
- "Design rules check and lock components" (.kicad_pcb modified): **63 findings, all "Footprint moved — Observed change"**. Every footprint shifted by the same offset (-21.608329, +16.632817 mm) — a single board translation reported as 63 separate findings.
- Coverage: DRC failed ("KiCad DRC JSON is invalid or lacks required check coverage"), parity failed (same), ERC failed (same), heuristics unavailable, mapping unavailable x3, cross-file relationships unavailable ("Netlist repeats a physical pad; connectivity is ambiguous").
- Missed: fuse-at-limit risk, relay-drive margin, GPIO0 pull-up. No ERC/DRC output at all.

### 2. fixthepixel/bench-psu-monitor — main, cd87301, 6 stars, 29 files (strongest bug set)
- HEAD ("Add overlay and bridge", overlay .py/.html): 0 findings.
- "Add kicad files with ibom and gerber files" (20 changed): **98 findings** — 41 "Footprint added" + 57 "symbol added". U1 INA3221, JP1 ADDR1, JP2 ADDR2, RS1/RS2/RS3 0.01 ohm, J1/J2/J3 CH1/CH2/CH3, U2 ESP32-WROOM-32E, U3 TLV76033, U4 USB-C, BT1 CR1220 all listed neutrally.
- Coverage: DRC failed (exit 3), parity failed (exit 3), ERC failed (exit 3), cross-file relationships unavailable ("KiCad could not export a bounded netlist for this schematic"), firmware checks unavailable.
- Missed: **both bugs** — INA3221 A0 floating vs firmware 0x40, and firmware using only CH1 of 3 channels. This is the sharpest miss in the whole test: the two parts and the firmware file were all in the import, and the audit connected none of them.

### 3. pms67/STM32F4-Reference-PCB — master, e0d1d8d, 195 stars, 31 files, PCB-only
- HEAD ("Update README.md"): 0 findings.
- "Initial commit." (28 changed): **54 findings, all "Footprint added"** (U2 STM32F407, J5 USB Micro-B, U1/U3 SOT-23-6, Y1 crystal, etc.).
- Coverage: DRC failed ("KiCad DRC JSON is invalid or lacks required check coverage. No project settings saved; KiCad defaults used"), parity **unavailable** ("No unambiguous root schematic with the same directory and basename"), **no ERC row at all** — schematic is legacy KiCad `.sch`, not `.kicad_sch`, and there is no adapter for it. BOM comparison unsupported ("No shared item/reference/part identifier column… 36 rows could not be matched"). 3 STEP files failed ("STEP inspection timed out after 30s").
- Missed: everything electrical — no schematic symbol analysis at all, no ERC, no DRC. NRST weakness not surfaced.

### 4. iandchasse/silkscreen-pcb — master, 4530931, 591 stars, 309 files (largest)
- HEAD (docs/.py/.json/.png only, 39 changed): 0 findings; audit took ~4 min.
- "Final-review revision: DW01A filters, J6 fuse, alternate RTC…" (57 changed): **230 findings, ~6 min**, all neutral: footprint moved, pad-net changed (J6/CR3 P+ → /P+_FUSE, C7 P+ → Net-(U5-VCC)), footprint added (H6, F2 fuse, R83, C34, U14 RTC), value changed (R17 150k→2M, R57 1M→10M, C23 2.2n→0.1u, R67 56k→510k, R70 100k→1M, etc.), rotation changed, symbol added, BOM cell changes.
- BOM false findings: pcbway_bom.csv "185 changed cells" are largely line-number-shift artefacts after rows were inserted — "line 61 Part Number changed DW01A → TLV75533PDBVR" and "line 63 TP4056-42-ESOP8 → DW01A" are renumbering, not real part swaps.
- Coverage: DRC timed out after 40s ("this check is unverified"), parity failed (same timeout), ERC failed (invalid/lacks coverage), STEP files timed out after 30s, cross-file relationships "ran" but produced zero findings (Connections 185).
- Missed: DW01A/FS8205A pinout suspect — DW01A appears only as a BOM row-shift artefact, FS8205A never mentioned, filter value changes reported with no assessment of correctness.

### 5. AzonInc/Doorman — master, fdec5c0, 253 stars, 583 files
- HEAD ("Merge PR #70", 92 changed): **144 findings, ~8 min** — 37 footprint added + 67 symbol added for doorman_slot, 13 + 27 for pcb_slot_programmer. Includes U3 ESP32-PICO-MINI-02, U2 XC6210B332MR LDO, Q1 BC817, **L1 value "TBD"**, **D2 value "D_Zener"**, U1 RTL8703CF, USB3.2A parts, TYPE-C 32P.
- Coverage: DRC/ERC/parity failed (invalid/lacks coverage) for all three .kicad_pcb/.kicad_sch files, STEP files timed out after 30s (x8), mapping unavailable x3, cross-file relationships "ran" with zero findings (Connections 90).
- Missed: "TBD" inductor and unspecified "D_Zener" listed as neutral observations, not flagged. IO0 pull-up weakness not surfaced. No electrical findings at all.

### 6. kylemanna/sniffer — master, 037c8c2, 166 stars, 41 files, PCB-only
- HEAD (esphome YAML, 1 changed): 0 findings.
- "sync: First pass complete" (17 changed): **18 findings, all "Footprint added"** (J2 PMSA003, U1 TTGO-T-DISPLAY, J1 CJMCU-680 BME680 breakout, C1–C3, JP1–JP8, Q1–Q2, R1–R2).
- Coverage: DRC failed ("Snapshot inputs incomplete: kicad/lib/TTGO-T-Display.dcm: Case-colliding repository paths cannot be materialized" — the commit adds both `lib/TTGO-T-DISPLAY.dcm` and `lib/TTGO-T-Display.dcm`). **No ERC and no parity rows at all** — the broken snapshot suppresses them. Cross-file relationships unavailable ("KiCad snapshot dependencies are incomplete").
- Missed: BME680 SDO/CS floating not assessed. Legacy sniffer.sch has no symbol analysis. Also noted from ground truth (not in Extrude output): `esphome/README.md` tells builders to copy a `sniffer.template.yaml` that is not in the repo, while the main README ticks "Upload ESPHome YAML file" as done.

### 7. UnsignedArduino/ESP32-Camera-PCB — main, d467da9, 8 stars, 29 files, single commit
- Audit: **53 findings** — 17 footprint added + 36 symbol added. B7 PowerBoost 500, B5 ArduCam OV2640, B3 MicroSD, B1 ST7735 TFT, B2 ESP32 dev board, B4 level shifter, B6 RTC, B8/B9 camera pins, C1 10uF, R1/R2 100K, SW1–SW5, 13 #PWR symbols.
- Coverage: DRC/ERC/parity failed (invalid/lacks coverage), mapping unavailable x3, cross-file relationships "ran" with zero findings (Connections 17), 11 backup ZIPs and all libs/*.kicad_mod footprints unsupported ("no audit adapter yet").
- Missed: PowerBoost USB charge input unconnected not assessed — B7 is only a "Footprint added" / "symbol added" observation; no finding mentions its USB/charge pins.

## Systemic failures (ranked)

1. **DRC/ERC/parity never run successfully — 12/12 failed.** Four distinct failure modes, so this is not one bug: (a) "KiCad DRC/ERC/PARITY JSON is invalid or lacks required check coverage" (repos 1, 3, 5, 7); (b) "failed (exit 3). Inspect the saved input and tool version." (repo 2); (c) "KiCad DRC timed out after 40s" (repo 4); (d) snapshot failure from case-colliding paths (repo 6). The native-check path is the product's core claim and it produced zero usable output on real repos.
2. **The audit is a per-commit diff, not a design audit.** It reports what changed between two commits, with no judgement. A board's actual design is never validated — only its delta. A first commit (repos 3, 7) yields only "added" observations; a docs-only HEAD yields 0 findings; a reviewer must manually pick an older hardware commit via "Change commit" to get any hardware analysis at all.
3. **No firmware analysis ran on any repo.** Firmware checks were "unavailable" in every audit. That is what killed both repo-2 bugs: the INA3221 address lives in firmware, and the CH1-only bug *is* a firmware fact. Without firmware, Extrude cannot do firmware-to-pin cross-checks at all.
4. **No electrical reasoning exists downstream of the diff.** Values are reported, never evaluated: "TBD" inductor, "D_Zener", 150k→2M and 1M→10M filter changes, fuse values, pull-up presence/absence — all neutral. There is no rule layer that turns a parsed net into a verdict.
5. **Legacy KiCad `.sch` schematics are invisible.** Repos 3 and 6 got no schematic symbol analysis, no ERC, and (repo 3) no parity row. A large share of real KiCad repos on GitHub are still legacy-format or mixed.
6. **Project check setup is placeholder defaults from another project.** BOARD_FILE `hardware/main.kicad_pcb`, Motor A, U1, GPIO 12:14, 13:16, M3 mounting hole were never configured per repo, so CAD/firmware/BOM mapping checks were "unavailable" in every audit. Nothing auto-detects the board file, the MCU, or the firmware entry point from the import.
7. **BOM comparison matches rows by line number.** Inserted rows produce false "Part Number changed" findings (repo 4). BOM matching must be by reference/designator, never by line.
8. **Board translation is reported as N findings, not one.** A single uniform shift of all footprints (repo 1) became 63 "Footprint moved" findings. Diff output needs grouping: one translation, one entry.
9. **STEP inspection times out after 30s; DRC after 40s.** Repos 3, 4, 5 lost all STEP geometry verification; repo 4 lost DRC/parity to the timeout. Timeouts are reported as "unverified", which is honest, but the limits are too low for real boards (repo 4: 309 files, repo 5: 583 files).
10. **Snapshot is case-sensitive-fragile.** Repo 6 failed outright because the repo contains both `TTGO-T-DISPLAY.dcm` and `TTGO-T-Display.dcm`. Case-colliding paths must be handled (or skipped with a named warning), not fail the whole snapshot and suppress ERC/parity.
11. **AI review unavailable on the live deployment.** Every audit: "Model provider unavailable." That removes the only layer that could have explained findings in plain English. On Render Free this is a missing-credentials deployment fact, but the product must degrade clearly — and the Codex plan must not assume a model is present.
12. **Audit runtime is long and unexplained.** ~90 s for small commits, ~4 min (repo 4 HEAD), ~6 min (repo 4 DW01A commit), ~8 min (repo 5 HEAD). No progress detail was reported in the test; a builder waiting 8 minutes for "Partial audit" with zero verdicts will not come back.

## What worked (keep it)

- **Imports: 7/7, no errors.** GitHub import flow works on real public repos of 26–583 files, including legacy KiCad 5.1 PCBs and multi-project repos (Doorman: 3 KiCad projects).
- **Diff parsing is real.** Footprint/symbol/value/pad-net changes were extracted accurately — the 63-move translation, the 41+57 add counts, the J6/CR3 net rename were all correct observations, just unjudged.
- **"Partial audit" honesty.** Unlike the false-pass bug in the code path (Codex audit Nov 8), this live run never marked anything "passed" that was not checked. Keep that behaviour; fix the underlying checks, do not reintroduce silent passes.
- **Cross-file relationships ran in 3 repos** (4, 5, 7) and read pad/net agreement — but produced zero findings. The plumbing exists; the rules do not.
- **No crashes, no import errors.** The site stayed up through 12 audits.

## What to work on, in order

1. Make DRC/ERC/parity actually run on real repos (failure modes a–d above). Nothing else matters until this works — it is the verdict layer.
2. Add a whole-design audit mode alongside the diff: audit the current design as it stands, not only its delta. Default HEAD must produce a design verdict, not 0 findings on a README commit.
3. Add firmware analysis + firmware-to-pin cross-checks (I2C address vs strapping/jumpers, channels used vs channels wired, GPIO use vs schematic).
4. Add a small rule layer on parsed nets — the 10 ground-truth checks are the first test suite: floating address pins, unused channels, floating strapping pins, fuse-vs-load, drive-current margin, unconnected charge inputs, floating SDO/CS, NRST, DW01A pinout verify.
5. Auto-detect project setup from the import (board file, MCU, firmware entry) instead of placeholder defaults; mapping checks must not be "unavailable" by default.
6. Legacy `.sch` support (parse or convert), BOM matching by reference, diff grouping (one translation = one finding), case-collision-tolerant snapshots, longer/adjustable timeouts for DRC and STEP.
7. AI review: either provision a model on the deployment or make "unavailable" a first-class, explained state — never silently drop the explanation layer the pilot pitch depends on.

## Limits of this audit

- Ground truth had no KiCad installed, so no ERC/DRC ground truth exists to compare Extrude's (failed) ERC/DRC against. The comparison is on findings, not on native-check output.
- Track widths, clearances, copper pours, Gerber-vs-PCB consistency, and datasheet values (relay coil current, crystal load capacitance, shunt power rating, TPS2116 limit) were not checked in ground truth and are not scored here.
- The live site is a Render Free container with no AI credentials and no login; results may differ on a provisioned deployment. The DRC/ERC failures are in the app/container path, not Render itself, as far as this test can tell — the same failure modes appeared across repos and commits.
- Only the GitHub import + audit flow was tested. No PRs opened, no repos changed, no code changed.

## Files

- Ground truth: `workspace/goals/extrude-ai/files/test-repos-ground-truth-2026-11-08.md`
- Codex plan from this audit: `workspace/goals/extrude-ai/files/extrude-codex-plan-live-test-2026-11-08.md`
- Earlier Codex audit + deep plan (Nov 8): `workspace/goals/extrude-ai/files/extrude-deep-plan-2026-11-08.md` — Phase A (false-pass fix) is still open and still first; this audit does not replace it, it adds the live-test evidence that the verdict layer is broken end-to-end, not just in the false-pass path.
