# Extrude — technical plan for Codex (from the live-site test, Nov 8 2026)

Source audit: `extrude-live-test-audit-2026-11-08.md`
Ground truth: `test-repos-ground-truth-2026-11-08.md`
Earlier deep plan: `extrude-deep-plan-2026-11-08.md` — **Phase A (false-pass fix) is still open and still comes first.** This plan does not replace it. It is the next layer: make the verdict path actually run, then add whole-design + firmware + rule checks, proven against the 7-repo test set.

Scope for Codex: draft PR scope only, not merged. No sending, no posting, no live-deploy change without Atirek's go-ahead. No new features, no billing, no hosted collaboration, no autonomous repairs.

## The test set (regression suite — do not break, do make pass)

Use exactly these repos at these SHAs. Every phase below must be verified against them; a phase is not done until its acceptance checks pass on this set.

| # | Repo | SHA | What it proves |
|---|------|-----|----------------|
| 1 | leomanangka/esp32-4-channel-relays | 3c7d3b1 | Fuse-at-limit, relay drive, GPIO0, board-translation grouping |
| 2 | fixthepixel/bench-psu-monitor | cd87301 | INA3221 A0 vs firmware 0x40 (BUG), CH1-only firmware (BUG) |
| 3 | pms67/STM32F4-Reference-PCB | e0d1d8d | Legacy .sch, PCB-only, NRST weakness, BOM matching |
| 4 | iandchasse/silkscreen-pcb | 4530931 | DW01A pinout verify, BOM line-shift false findings, DRC timeout |
| 5 | AzonInc/Doorman | fdec5c0 | IO0 weakness, "TBD"/"D_Zener" flagging, multi-project repo |
| 6 | kylemanna/sniffer | 037c8c2 | Case-colliding paths, BME680 SDO/CS risk, PCB-only |
| 7 | UnsignedArduino/ESP32-Camera-PCB | d467da9 | PowerBoost USB charge unconnected, breakout-carrier handling |

Scoring rule for the suite: a check counts as caught only if Extrude surfaces it with the right severity class (BUG / RISK / WEAKNESS / "verify") and the right part/pin/value/source. A neutral diff observation does not count. A false flag on a ground-truth "correct — do not flag" item fails the suite. "Not checked" must be said as "not checked", never "passed".

Current score on this suite: **0/10 checks caught, DRC/ERC/parity 0/12 successful, AI review 0/12 available.**

## Phase 0 — prerequisite (already assigned, do first)

Phase A from the deep plan: fix the empty-netlist false-pass in `extrude/copilot/api.py` (`_audit`) and `extrude/project_map.py` (`_check_file`), add tests covering both entry points, then the buck gate (reject empty/incomplete topology, fail ripple above the frozen limit in `eval/proxy_tasks/buck/task.json`). Do not start Phase 1 until Phase A lands, because a green verdict layer built on a false-pass path is untrustworthy.

## Phase 1 — make DRC / ERC / parity actually run

Goal: on the 7-repo set, DRC/ERC/parity produce a real result (pass, fail with named violations, or a named "not checked" with reason) instead of failing in 12/12 audits.

Tasks:
1. **Diagnose each failure mode separately, with a repro per repo.** (a) "KiCad DRC/ERC/PARITY JSON is invalid or lacks required check coverage" — repos 1, 3, 5, 7. Find whether the JSON is malformed, empty, or missing expected keys; log the raw output (truncated) and the KiCad version in the audit record. (b) "failed (exit 3)" — repo 2. Capture stderr, saved input, and tool version; exit 3 must map to a named cause, not a generic message. (c) "KiCad DRC timed out after 40s" — repo 4. Profile where the time goes; raise the timeout for large boards and/or run DRC asynchronously with progress, never silently drop it. (d) Snapshot failure on case-colliding paths — repo 6 (`lib/TTGO-T-DISPLAY.dcm` vs `lib/TTGO-T-Display.dcm`). Make snapshot materialisation case-collision-tolerant: keep both paths distinct (or skip the colliding duplicate with a named warning) instead of failing the whole snapshot and suppressing ERC/parity rows.
2. **Every native check must emit one of three states, always:** `ran` (with violations or clean), `failed` (named cause + evidence pointer), `not checked` (named reason, e.g. legacy format, no schematic). Never emit a fourth, silent state. Never mark a check "passed" when its input was incomplete.
3. **Pin the KiCad version.** Declare and test one KiCad version for the container (Dockerfile already pins KiCad 9.x — verify the running version matches, record it in the audit, and add a version-mismatch warning if the repo was authored in KiCad 5.1/6/7).
4. **STEP inspection timeout.** Raise the 30s STEP timeout or make STEP checks async/batched; a timeout must say which files were unverified, not fail the whole geometry check silently. Repos 3, 4, 5 lost all STEP verification to this.
5. **Regression test:** a fixture repo per failure mode (a–d) in CI, asserting the check reaches `ran` or a named `failed`/`not checked` — never the current generic messages.

Acceptance: DRC/ERC/parity reach a real result on at least 6 of 7 repos; repo 6 reaches a real result or a named case-collision warning with ERC/parity still attempted on the non-colliding files; no audit in the suite reports the four generic failure strings above.

## Phase 2 — whole-design audit mode (not just diff)

Goal: the default audit answers "is this design sound as it stands?", not only "what changed?".

Tasks:
1. Add a whole-design audit that runs the parsers, native checks, and rule layer over the current commit's full design, independent of the diff. Keep the diff view as a separate tab/section — do not mix diff observations with design verdicts in one list.
2. **Default commit selection:** when HEAD touches no hardware files (README/overlay/docs-only — repos 1, 2, 3, 4, 6 all did this), the audit must not return 0 findings and stop. Default to the latest commit that touched a hardware file (`.kicad_sch`, `.kicad_pcb`, `.sch`, firmware, BOM), and say plainly which commit was audited and why. Keep "Change commit" as a manual override.
3. **Separate finding kinds in the UI and the data model:** `change` (diff observation, no judgement), `verdict` (rule/native-check result with severity), `not checked` (named gap). A "TBD" value, an unspecified part value, or a changed filter value must never appear as a bare `change` — it is a `verdict` candidate (see Phase 4).
4. **Grouping:** collapse a uniform board translation into one finding ("All 63 footprints moved by (-21.6, +16.6) mm — board translated", repo 1), and collapse identical repeated observations by pattern. Keep the per-part list expandable underneath, not as 63 top-level findings.

Acceptance: auditing HEAD of each of the 7 repos returns design verdicts (or named "not checked") without manual commit-picking; a docs-only HEAD no longer yields a 0-finding audit; repo 1's translation is 1 finding, not 63.

## Phase 3 — firmware analysis + firmware-to-pin cross-checks

Goal: firmware is analysed in every audit where firmware exists, and cross-checked against the schematic/PCB. This is the phase that catches both repo-2 bugs.

Tasks:
1. Add a firmware adapter: parse `.ino`, `.py`, `.c/.h`, `.cpp`, and ESPHome YAML at minimum. Extract: I2C addresses used, pins/GPIOs referenced, peripherals/channels used, and constants (shunt values, addresses).
2. Cross-checks (first set, each a named rule with evidence):
   - I2C address in firmware vs address-strap pins in schematic (jumpers, pull-up/down, floating). Repo 2: firmware 0x40 requires A0=GND (JP2 bridged); A0 floats as built → **BUG**, with the fix (bridge JP2 / add pull-down).
   - Channels/peripherals used in firmware vs channels wired in hardware. Repo 2: hardware has 3 shunts/channels, firmware reads CH1 only → **BUG**; also flag the latent library-default shunt mismatch (0.1 ohm default vs 0.01 ohm hardware → 10x-low current if CH2/CH3 are later read).
   - GPIO numbers in firmware vs schematic net names (mismatch = finding, not silent).
   - Firmware file present but never analysed must be listed under "not checked" with the reason, not omitted.
3. **Project setup auto-detection (fixes the placeholder-defaults bug):** on import, detect the board file(s), the MCU part, and the firmware entry point from the repo and populate Project check setup from them. The placeholder defaults (BOARD_FILE `hardware/main.kicad_pcb`, Motor A, GPIO 12:14, 13:16, M3) must never ship as the setup for a repo that does not contain them. If detection fails, setup is "not configured — mapping checks not checked", named as such.

Acceptance: repo 2 yields both BUGs with part/pin/file:line evidence; firmware checks are no longer "unavailable" on repos 2 and 5; setup is auto-detected or explicitly unconfigured on all 7 repos.

## Phase 4 — rule layer on parsed nets (first 10 rules)

Goal: parsed nets produce verdicts. Implement the 10 ground-truth checks as the first rule suite, each with severity, evidence (part/value/net/source), and a plain-English explanation (what it is, why it matters, what to do).

Rules (severity from ground truth):
1. Floating address/config strap pin that firmware depends on → BUG (repo 2, INA3221 A0).
2. Hardware channel wired but never used in firmware → BUG (repo 2, CH2/CH3).
3. Protection-FET gate wiring that does not match the standard footprint pinout → "verify footprint pinout" (SUSPECT, never a certain bug without footprint proof) (repo 4, DW01A/FS8205A).
4. Floating mode/address select pin on a sensor breakout (SDO/CS) with no schematic/firmware to resolve it → RISK (repo 6, BME680).
5. Charge/power input pin of a module unconnected where the design implies on-board charging → RISK, surfaced with the alternative (external charging) stated (repo 7, PowerBoost USB).
6. Fuse rating vs worst-case load (sum the loads on the fused rail from the netlist + datasheet coil currents) → RISK when within ~10% of rating or over (repo 1, F1 500 mA vs ~450–500 mA).
7. Drive-chain margin (opto LED current, CTR range, base current vs saturation need, transistor max Ic vs coil current) → RISK when margin is thin (repo 1, relay drive).
8. Reset pin with no pull-up or cap → WEAKNESS (repo 3, NRST).
9. Boot-strapping pin with no external pull-up → WEAKNESS (repos 1 and 5, GPIO0/IO0).
10. Placeholder / unspecified values → WEAKNESS at minimum, never neutral: value "TBD", value "D_Zener", or any part with no value → flag with the part reference (repo 5, L1 "TBD", D2 "D_Zener").

Also, as part of this phase:
- **BOM matching by reference/designator, never by line number.** Repo 4's false "Part Number changed DW01A → TLV75533PDBVR" findings must disappear; inserted rows must appear as added rows.
- **Legacy `.sch` support:** parse legacy KiCad schematics or convert them (document the chosen approach) so repos 3 and 6 get symbol analysis, ERC, and parity — or a named "not checked: legacy schematic, no adapter" that is tracked as a gap, not silent. Prefer parsing/converting; the gap is too common to leave.
- **"Correct — do not flag" regression list:** the ground-truth correct items (buck FB/EN dividers, BOOT0, SWD, I2C pull-ups, USB-C CC, SSR drive, WS2812B, SD/camera SPI, battery divider) must not be flagged by any new rule. Add them as negative tests.

Acceptance: suite score goes from 0/10 to at least 8/10 caught with correct severity class; 0 false flags on the "do not flag" list; repo 4 BOM false findings gone; repos 3 and 6 either analysed or explicitly "not checked: legacy schematic".

## Phase 5 — AI review + deployment honesty

Goal: the explanation layer works on the live deployment, or its absence is explicit.

Tasks:
1. Provision a model for the Render deployment (credentials via the deployment's secret store, never in the repo) *or* decide explicitly that the free pilot has no model — and if the latter, the UI must say so up front ("AI explanations unavailable on this free pilot — findings and connections are still shown") instead of failing per-audit with "Model provider unavailable".
2. When a model *is* present, the explanation must be grounded in verified parser/ERC/DRC/firmware-pin data, with unverified items marked "not checked" — never speculated, never a repeat of the finding text. (Lesson from the Nov 7 Shashvat-repo test.)
3. Audit runtime: show progress per check (which check is running, elapsed time) for the 90 s–8 min audits; consider capping the default audit to the changed design + whole-design rules and deferring STEP/geometry to a background pass.

Acceptance: on the live site, AI review either works on all 7 repos or is explicitly declared unavailable before the audit starts; no audit ends with a surprise "Model provider unavailable".

## Phase 6 — verification + ship gate

1. Re-run the full 7-repo suite on the live site after Phases 1–5, using the same SHAs, and record the new score in the audit file (append, do not overwrite the Nov 8 baseline).
2. Ship gate for any pilot link shared with friends: suite score ≥ 8/10, DRC/ERC/parity real results on ≥ 6/7 repos, 0 false flags on the "do not flag" list, and Phase A (false-pass fix) merged. Until then, the live link stays throwaway-public-projects-only, with the false-pass warning in front of any friend test.
3. Keep the Nov 8 baseline (0/10, 12/12 native-check failures) in the repo as the regression baseline — do not delete the failing evidence when it starts passing.

## Out of scope (do not build in this plan)

Billing/refunds, hosted collaboration, webhooks, Onshape sync, autonomous repairs, Apollo/Klaviyo/Make, Instagram launch, new hardware features. No PRs merged without Atirek's go-ahead; draft PRs only.
