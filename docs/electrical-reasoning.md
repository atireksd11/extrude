# Whole-design electrical reasoning — draft, November 10, 2026

This draft adds a revision-pinned electrical layer to workspace audits. It reads
all hardware inputs at the selected head, even when the change map is empty.
The GitHub change map, configured firmware checks, existing ERC/DRC and evidence
links remain available. No merge or deployment is included.

## Net graph and operating-limit sources

`electrical_graph.py` parses native `.kicad_sch` files with the existing pinned
`kicad-tools` package. Embedded library pins supply pin numbers, functions, units,
coordinates and electrical types. Rotation and mirroring precede connectivity.
Wire endpoints, junctions, labels, global power symbols and hierarchical ports
form a union-find graph. A wire crossing without a junction does not connect.
Independent board variants are isolated. This requires neither `kicad-cli` nor
an installed KiCad symbol library. Repository code and firmware are never run.

Repeated sheet instances are excluded with explicit coverage rather than having
their references/connections conflated. Other sheets remain analyzable. Legacy
`.sch`, missing embedded symbols, external library model variables, absent child
sheets and ambiguous BOM scope get **Not checked** coverage. Resource bounds are
10,000 inventory entries, 256 input files, 8 MiB per blob, 64 MiB total, 4,096
symbols, 12,000 connection points, 20 million geometry comparisons, 500 findings.
All inputs are regular Git blobs at the requested SHA; model existence uses
case-sensitive regular-file paths, not working-tree files or symlink targets.

Limits come from evidence, not a chip catalogue:

- Resistor values support numeric and embedded multipliers, including `5k6`,
  `10kR 1%` and `22k1R 1%`. Divider math uses nominal resistor values.
- ADC bounds use named reference/supply pins and explicit `ADCReferenceVoltage`
  or `PinMaxVoltage` properties. A nominal supply/reference comparison is not an
  independently verified silicon absolute maximum. USB VBUS uses 5 V nominal
  and 5.25 V for the USB default-voltage divider bound; PD rails require explicit
  operating limits. Piantor evaluates to 5.25 × 10/(5.6+10) = 3.365 V.
- Capacitor ratings come from the value or Voltage/VoltageRating/RatedVoltage
  fields; named rail potentials establish bias. The requested limit is 70%.
- USB CC termination follows the sink Rd requirement; data routing is checked
  against embedded pin functions. Protection absence remains a review suggestion.
- Regulator consistency compares fitted values, symbol identity, explicitly
  described output voltage and named output nets. Input maximums are not output
  voltages. The layer does not invent capabilities from an MPN suffix.
- Reset/strap internal pull-ups require documentation before a defect verdict.
  An optional DNF crystal load is not automatically a defect: integrated load
  capacitance may be valid. Excluded crystal assemblies and missing paired-PCB
  crystal footprints are separately identified.
- Shunt-reference polarity uses an explicit reference threshold, healthy/low
  battery levels and enable intent (`ReferenceVoltage`, `HealthyVoltage`,
  `LowVoltage`, `EnableActiveHigh`). With missing limits it reports Not checked.
  It does not guess the cutoff voltage from a familiar part number.

Findings carry file/reference/pin evidence, why, a proposed fix, and
`present_at_head` lifecycle. Suggestions preserve uncertainty. Coverage never
labels a design "passed". The rule version increments to invalidate old audits.

## Pinned acceptance rerun

Run from the repository using its installed dependencies:

```sh
python -m eval.electrical_gate --repos-dir work/acceptance --output work/gate.json
```

Clone each repository listed in `eval/electrical_manifest.json` into
`work/acceptance/<repository basename>` first. Every SHA is checked and all
analysis reads that commit's blobs. The evaluator calls the production
`electrical_reasoning.collect` entry point, supplying a local Git-directory
adapter only. No acceptance fixtures or repository names appear in runtime rules.

Measured result: **11/13**, **Shashvat 4/4**, **zero false flags on 66 Correct
items**. There are **no separate PASS-group repositories**. The PASS group is the
user's per-repo Correct lists inside the same seven repositories at the same
pinned revisions. `electrical_correct_items.json` preserves those lists and the
review of emitted claims against them. Unreviewed additional findings fail this
conservative false-flag gate until reviewed. These review patterns are evaluator
metadata, never runtime suppressions.

| Item | Evidence named by the new layer | Result |
| --- | --- | --- |
| 1 | Y1 excluded from BOM; C12/C13 DNP | caught |
| 2 | U1001 PB6/PB7, BMC-side DDC/I2C nets lack external pull-ups | caught |
| 3 | J903/J1101/U802/J1007 STEP references do not resolve | caught |
| 4 | C7 6.3 V rating on 5 V, 79.4% | caught |
| 5 | J3/J5 omitted; SW1/SW2 are present in the pinned BOM | partial, **no credit** |
| 6 | U2 1.2 V symbol, HT7550-1 fitted value and 5 V output net disagree | caught |
| 7 | J1 TRRS assigned a resistor footprint | caught |
| 8 | U2 GPIO28_ADC2, R1/R2 produce 3.37 V at 5.25 V VBUS | caught |
| 9 | U2 cutoff polarity: reference/enable limits not sourced | **open** |
| 10 | J4 shield floating and no identifiable D+/D− ESD | caught |
| 11 | J3 D+/D− to U3 UART GPIO43/44 | caught |
| 12 | J3 CC1/CC2 tied to GPIO0/BOOT without independent Rd | caught |
| 13 | Q1 grounded base and GPIO14-driven emitter | caught |

Shashvat: U4 LRCK→U3 IO27 versus firmware WS GPIO28, floating U4 SCKI,
floating U4 VREF, and BCK/LRCK with slave firmware and no established clock master.
The latter stays a suggestion because bidirectional pin metadata cannot establish
all chip modes. Specific part/pin/problem evidence qualifies it for this checklist.

Correct-list review found no accusations against connector-side R405/R406,
optional RTC DNF loads, ESP32 I2C/CC pull resistors, permitted NC/unused pins,
on-module pull-ups, valid firmware maps, direct keyswitch wiring, normal transistor
power paths, or regulator dissipation. A J5 **BOM omission** does not accuse its
expansion wiring; a Q1 **transistor inversion** does not accuse IR_PIN GPIO14's
firmware mapping; U2 **symbol/voltage inconsistency** does not accuse thermal
power dissipation. The evidence report retains all emitted claims for review.

## Verification and still open

The evidence JSON contains the pinned SHAs, measured checklist, every finding,
coverage and Correct-list reviews. Synthetic tests also exercise corrected
circuits, mirrors/rotations, unjoined crossings, hierarchy scope, optional loads,
limits, positive reference polarity and whole-design audit integration.

Item 5 remains partial: at `8b607d55b22a3b87fba569c61781188e9781fece`,
`hardware/bom/bom.csv` explicitly lists RESET/SW1 and BOOT/SW2. It would be false
to claim all four are omitted. Item 9 remains open because the necessary sourced
operating limits and downstream enable transfer function are absent from the
parsed metadata. Repeated sheet placements, firmware preprocessing/ambiguous
configurations, integrated protection and missing datasheet operating limits
remain explicit coverage limitations. Passing the measured checklist does not
verify arbitrary electronics or replace KiCad ERC/DRC.

Final local test output:

```text
python -m pytest tests/test_electrical_reasoning.py -q
36 passed in 0.69s

python -m pytest tests -m atlas -q
3 failed, 99 passed, 284 deselected, 1 warning in 18.68s

node tests/ui/github_workspace.test.cjs
PASS review races, evidence routing, saved coverage, sync selection,
review tabs, counts, import disclosure

python -m eval.electrical_gate --repos-dir work/acceptance --output work/gate.json
New repos: 11/13
Shashvat: 4/4
Correct-list false flags: 0 across 66 Correct items
```

The three Atlas failures are `test_real_native_phase2_gate`,
`test_native_hierarchical_sheet_evidence`, and `test_native_workspace_api_gate`
in `tests/test_kicad_audit.py`. All three were rerun on an untouched detached
worktree of base `ce5826d089c3a5c8bf679b0545b24a1f7c2e6dc0` and failed there too:
`3 failed, 1 warning in 5.27s`. KiCad 9.0.2 returns DRC/ERC JSON rejected by the
existing native coverage adapter. This draft leaves that separate native adapter
unchanged. The electrical evaluator does not invoke it. Formatting and
`git diff --check` also succeed.
