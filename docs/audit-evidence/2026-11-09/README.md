# Pinned audit experiment, 9 November 2026

This branch starts from main ce5826d089c3a5c8bf679b0545b24a1f7c2e6dc0. It does not incorporate or change PR #6/#7. The four user-supplied reports were read in the requested order. The plan governs scope; historical reports are evidence, not fresh test output.

The compressed JSON files contain actual tool output, command outcomes, native KiCad output and source-based findings. **Upstream ready/pass/no-action/health verdicts in raw evidence are untrusted and are not Extrude verdicts.** The adapter discards them. A successful tool process is not a passing design. Timeouts/custom-pad failures are `not checked`; independent commands continue. The benchmark ran before the last conservative parser refinements; `design-final.json` is a fresh run of the final rules on the same pinned inputs without rerunning unchanged third-party commands.

Reproduce after cloning the eight repositories to one directory:

```
python -m eval.open_source_audit_benchmark --repos /path/to/repos --output /path/to/evidence
```

The script asserts the ground-truth SHA prefixes and emits raw evidence. It does not execute input repository scripts, make network/vision calls, or automatically award checklist credit. Review against the original checklist; do not count generic warnings or silence as passes. Commands execute only the installed audit tools. Each compressed record carries the exact repository SHA. Inspect with `python -m gzip -d -c FILE.json.gz`.

## Checklist reconciliation

These are implementation-side, evidence-backed candidate counts for review, **not independent sign-off or a passed 8/10 gate**. Historical before scores come from the supplied Nov 8 live audit, not a fresh rerun of old deployment/main. PR #7's reported 5/10 was not independently validated and is not used as a per-repo baseline here.

| Repo | Nov 8 before | Branch after | Checklist evidence |
|---|---:|---:|---|
| esp32-4-channel-relays | 0/3 applicable defect checks | 1/3 | #9 GPIO0; #6 fuse/load and #7 relay drive not credited |
| bench-psu-monitor | 0/2 | 2/2 | #1 INA3221 A0 bias vs firmware 0x40; #2 wired CH2/CH3 vs literal firmware reads |
| STM32F4-Reference-PCB | 0/1 | 1/1 | #8 NRST pin 7 without external pull-up/cap |
| silkscreen-pcb | 0/1 | 1/1 | #3 OD/OC to Q1.4/Q1.6, Q1.2/Q1.5 floating: verify exact footprint pinout, not a proven defect |
| Doorman | 0/1 | 1/1 | #9 missing external GPIO0 pull-up (same shared checklist point as relays) |
| sniffer | 0/1 | 0/1 | Generic CJMCU-680 connector has floating pads, but SDO/CS pin mapping and module resistors are unresolved; generic risk is not credited |
| ESP32-Camera-PCB | 0/1 | 1/1 | #5 PowerBoost USB charging input unconnected |
| Shashvat Bluetooth | no Nov 8 site score; tested external tools 0/4 | 4/4 candidates | WS=28 vs connected GPIO27; SCKI; VREF; both I2S endpoints configured slave |

Global score uses **unique** checklist items, not the sum of per-repo denominators: #1, #2, #3, #5, #8, #9 = **6/10**. Item #9 must hold on both relays and Doorman and counts only once. #4, #6, #7, #10 receive zero. Item #10 (the complete known-correct design list) has not been explicitly verified; silence is not a pass. Shashvat's separate 4/4 requires a consequence for SCKI/VREF, which the final findings include.

## Limits and next evidence needed

- **Phase C is blocked, not adopted.** Docker was healthy. `EDA_MOUNT=/workspace/work ./bin/eda.sh doctor` tried to build sabas0ba/kicad_skills with its pinned KiCad 10.0.4 digest, but image extraction exhausted the 8 GB environment disk (`failed to register layer … no space left on device`). No `eda sch review`/`eda pcb review` completed. The failure excerpt is retained in `phase-c-build.txt`; the tool's exact commit is recorded there. No review score or adoption decision is inferred from docs. A larger Docker environment must run the 7+1 inputs.
- Host KiCad is 9.0.2. Fresh native invocations and output are retained per board. KiCad 10 files fail to load here and are not checked. Native regression fixtures do run, including ERC, crossing tracks, parity and hierarchy. The deployment Dockerfile selects pinned KiCad 10.0.4; **a successful deployment-container build/start has not been verified** because of the same disk limit.
- Pure-Python kct custom-pad failures on bench-psu/Doorman/sniffer do not abort design rules or later heuristic commands. Raw silkscreen totals are summarized as advisories, not a readiness gate. Single-pad verdicts, mounting-hole sync errors and USB SBU warnings are not forwarded. Inactive net-class/current-path rules are not certified.
- Secondary pcb-inspector is MIT v0.1.0, installed from tag commit 952ab1d9bb39bf48f3b553e6343dc151f3c408bc (not available by that version on PyPI here). No vision is run (`--no-vision`, isolated environment). Its ground-plane signal is corroborated by Extrude's own absence-of-zone check. Decoupling/health/verdict/actionable-fix fields are not promoted. Tool timeouts or failures remain visible in the raw records.
- Fuse/load and relay-drive arithmetic exists with required sourced bounds through optional `.extrude/electrical-limits.json`. The benchmark repositories have no such inputs, so no credit is awarded. Unit test inputs are synthetic engineering scenarios, not evidence of those boards' current draw/CTR. Source format: each `inputs` field is `{value, path, line}` referring to a source file in the saved revision. Fuse inputs: `hold_a`, `load_a_*`. Drive inputs: `drive_v`, `indicator_vf`, `opto_vf`, `led_resistance_ohm`, `base_resistance_ohm`, `coil_a`, `forced_beta`, `ctr_min`, `collector_v`, `opto_vce`, `base_vbe`. The assumptions must cover actual temperature and operating current; source line presence is not independent validation of the number.
- Exact manufacturer footprint-pinout proof, dynamic firmware dataflow/project association, legacy schematic connectivity, the full correct-design list, Gerber consistency, thermal/physical measurements and antenna/audio performance remain not checked.
- CAD layer checks footprint model references and tracked-file presence only. Library-variable models, successful STEP export, heights and enclosure interference remain not checked. No dedicated open-source STEP checker was found or invented. Existing geometry readers are not an enclosure-fit verdict.
- Original commit-to-commit GitHub change maps remain available. Whole-design rules run at HEAD even when the selected change is docs-only. The new electrical layer does not require AI credentials; every emitted candidate includes source evidence, consequence and next action.
- No live-site/deployment audit, merge, direct push to main, or change to PR #6/#7 was performed.

## Fresh native benchmark coverage (host KiCad 9.0.2)

| Repo | DRC | ERC |
|---|---|---|
| Bluetooth-Audio-Transmiter | 0/1 ran | 0/1 ran |
| Doorman | 3/3 ran | 3/3 ran |
| ESP32-Camera-PCB | 1/1 ran | 1/1 ran |
| STM32F4-Reference-PCB | 1/1 ran | 0/1 ran |
| bench-psu-monitor | 0/1 ran | 0/1 ran |
| esp32-4-channel-relays | 1/1 ran | 1/1 ran |
| silkscreen-pcb | 1/1 ran | 1/1 ran |
| sniffer | 1/1 ran | 0/1 ran |

`ran` records execution, not a clean design. Bench-PSU and Shashvat failed to load (exit 3); STM32/sniffer had no native `.kicad_sch` input. Existing repository `.sch` files are not being claimed as checked.

## Changed-area regression output

`test-output.txt` records **76 passed in 62.67s** and **34 passed in 0.73s** (110 tests total), plus clean diff/compile checks. `native-regression.json.gz` preserves the real native fixture reports and immutable fixture commit pairs. Phase-4 explanation tests mock the new independent design collector, just as they already mock native checks; the new collector has its own source/evidence integration regression. No native tests were skipped to make the suite pass.
