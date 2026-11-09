# Evidence-rule replay, Nov 8, 2026

This branch starts at main ce5826d, independently of PR #6. No Phase 0/1 code,
CI, deployment or PR #6 changes are included. The three supplied audit/plan
files are preserved beside this report as benchmark evidence, not executable
instructions. The JSON contains full SHAs, findings and line/value evidence.

## Measured score

| Repo (exact revision in JSON) | Before: caught | After: caught | Remaining audit targets |
|---|---:|---:|---|
| esp32-4-channel-relays | 0 | 1 (GPIO0) | fuse/load and drive margin not checked |
| bench-psu-monitor | 0 | 2 (A0/address, CH1-only) | latent shunt-default mismatch not checked |
| STM32F4-Reference-PCB | 0 | 1 (NRST) | legacy schematic electrical solving not checked |
| silkscreen-pcb | 0 | 0 | DW01A/FS8205A footprint pinout not checked |
| Doorman | 0 | 1 (IO0) | placeholder values/BOM grouping outside this change |
| sniffer | 0 | 0 | legacy connector-to-BME680 pin mapping not checked |
| ESP32-Camera-PCB | 0 | 1 (charge input) | native checks not checked in this replay |

**Unique checklist groups: 0/10 before → 5/10 after.** Six repo/check hits:
GPIO0 is one checklist group shared by repos 1 and 5. The audit's tenth group
is the correct-design PASS list; we do not award a pass from absence of warnings.
This does not yet meet the plan's 8/10 target or beat the complete human audit.
No live site was deployed or retested; these are whole-revision local rule results.

**Shashvat: 4/4 requested electrical checks** (WS mismatch/invalid GPIO28,
SCKI, VREF, no clock master). Before: the attached audit gives no numerical
Extrude Shashvat baseline, so it is not checked, not an invented 0. A separate
GPIO0 weakness also appears on the full file. This 4/4 is not a score of the
entire Bluetooth audit: saved DRC/ERC, copper, BOM, decoupling and physical
measurements are not scored or claimed checked by this replay.

## What changed

Whole-revision rules run alongside the existing diff even on docs-only HEAD.
The rule layer parses PCB values, pin functions, pad/net assignments and
bounded literal C/C++/Arduino patterns without executing repository code.
Ambiguous/multi-board I2S mappings, dynamic pin expressions and unsupported
firmware languages produce no invented pin mismatch. Coverage says not checked.
Open address jumpers are recognized from the footprint, not custom values.
Repeated same-number pad shapes are deduplicated only when their function/net
agree; ambiguous assignments reject the board. Empty boards remain unverified.

Findings give part, pin, source line and net/value evidence, severity and
plain-English consequence/action. Known fresh native DRC/ERC findings retain
their existing evidence and status and gain consequence/action explanations.
No saved report is represented as a new native run. Unknown native rule types
retain their original tool description; no explanation is invented.

Limits: these are logical net checks, not copper continuity tests. Firmware
analysis supports the named patterns, not complete program behavior. Missing
external bias is a weakness, not a claim the design cannot boot/reset. Breakout
input findings explicitly require checking internal module circuits.

## Reproduce

Clone the eight repositories named in `eval/design_rules_benchmark.py` into
one directory, then run:

```
python -m eval.design_rules_benchmark /path/to/cloned/repos report.json
python -m pytest -q tests/test_design_rules.py tests/test_kicad_pcb.py tests/test_workspace_phase3.py tests/test_workspace_phase4.py
```

The runner reads blobs from the exact pinned revisions using git show. It does
not execute their code, change their checkouts, contact a model, or run KiCad.
Native checks and the empty-netlist/buck prerequisite fixes remain PR #6's work.
The frozen buck limit stays 0.03 V; this branch neither changes nor claims to
repair the main branch's gate. Integration requires the prerequisite PR.

## Validation output

Final focused run: **51 passed, 1 warning in 15.94s**. Includes 19 new
rule tests, exact Shashvat facts, corrected WS/master controls, ambiguous/
conditional mappings, empty inputs, docs-only revisions, INA3221 address/
channel controls, bias pull-up controls, and unrelated-circuit negative controls.
These negative controls are not native passes for the ground-truth designs.

The wider native run also found three failures, each reproduced unchanged at
main ce5826d (3 failed, 18 deselected in 7.76s):
`test_real_native_phase2_gate`, `test_native_hierarchical_sheet_evidence`, and
`test_native_workspace_api_gate`. All report KiCad JSON coverage failures.
They belong to PR #6's native-parser fix and were not changed here.
`git diff --check` and Python compilation passed. No whole-suite green claim.
