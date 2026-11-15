# Hardware audit trust blockers — November 15, 2026

These generic rules extend PR #10 at `20d66bb`. Findings keep schema version 4;
rule version 7 invalidates cached audits. No repository, device, component or net
names from the acceptance board occur in production rules.

- Compare the root schematic hierarchy with its same-name PCB, never a backup.
  Each fitted, on-board symbol without a footprint gets an assembly warning
  naming the component and assembly/function consequence. Electrical footprints
  without symbols also warn; padless graphics are excluded. DNP/off-board symbols
  are not accused. Reverse parity and driver-absence claims require a complete
  graph/hierarchy. A scoped BOM can identify additional missing components.
  Explicit firmware mappings also warn when their expected component is absent
  from the paired board; arbitrary identifiers in source are not designators.
- Pull-up findings require net/protocol or open-drain evidence. A pin name alone
  does not establish I2C. SPI/SCK/MOSI/MISO net semantics override ambiguous
  SCL/SDA pin names.
- A new board with the same complete supported footprint inventory as an existing
  board at base or head produces one `pcb.board_copy_added` observation. Match
  references, library, placement, layer, properties/values and pad nets, ignoring
  UUIDs. Changed placement, value or net assignment prevents collapse. Tracks,
  zones, stackup and unsupported geometry are explicitly outside this comparison;
  this is a footprint inventory verdict, not whole-board equivalence.
- Nets with only input loads and no driver warn with net and load identities.
  Trace series resistors, and distinguish supply/ground bias from protocol drive.
  Single named bus control/data inputs are checked; generic isolated inputs need
  design intent. Passive connectors and bidirectional pins are possible external
  sources, so absence of a driver is not asserted there. Static resistor-biased
  enable/strap/divider nets are not accused. Incomplete graphs cannot prove an
  absent master.

## Pinned Astra acceptance

Original audit: `aadbbd68b22a718427d9cd3ff2402d0f40353e0789ca7b828ae5965f9e1a9cc3`.
The expectations JSON records the full base/head commits and expected evidence;
it is evaluator metadata, never runtime input.

```sh
python -m eval.workspace_gate \
  --repo-dir work/acceptance/astra-companion \
  --base e0751c92 --head 0c8afb27 \
  --expectations eval/astra_trust_expectations.json \
  --output work/astra-final.json
```

The runner calls the production workspace descriptor/collector with local Git
storage and isolated local state, without fetching or executing repository code.
All normal audit adapters run; native unavailability remains explicit coverage.

Measured result: **all assertions pass**, 30 findings:

- SW1/SW3/SW6, R36/R37/R38, C32/C33/C34, U13 and UE1 each have one assembly
  **warning** naming the missing footprint and consequence, with main-board
  inventory evidence.
- No DS2 pull-up finding.
- One backup summary: **107 footprints**, no 107 individual additions.
- SPI_CLK, SPI_MOSI, TFT_DC, TFT1_CS and TFT2_CS each warn as undriven, naming
  their input loads. Pull bias on SPI_MOSI is not treated as a bus master.
- Assembly inventory coverage is `ran`. Overall audit is `partial` because other
  adapters and operating-limit checks retain their existing limitations.

Full evidence: `docs/evidence/astra-trust-2026-11-15.json`.

## Deep-test-2 and regression verification

```sh
python -m eval.electrical_gate --repos-dir work/acceptance --output work/gate-final.json
```

**11/13**, Shashvat **4/4**, **zero false flags across 66 Correct items** at the
same pinned revisions as PR #10. The Correct-item lists and reviewed patterns
are unchanged. Full findings/reviews: `docs/evidence/electrical-gate-2026-11-15.json`.

```text
python -m pytest tests/test_trust_blockers.py tests/test_electrical_reasoning.py \
  tests/test_kicad_pcb.py tests/test_workspace_phase3.py -q
75 passed

python -m pytest tests -m atlas -q
3 failed, 114 passed, 284 deselected, 1 warning

node tests/ui/github_workspace.test.cjs
PASS review races, evidence routing, saved coverage, sync selection,
review tabs, counts, import disclosure
```

The three failures are `test_real_native_phase2_gate`,
`test_native_hierarchical_sheet_evidence`, and `test_native_workspace_api_gate`.
All three also fail on a detached, unmodified `20d66bb` worktree using its own
imports (`RULE_VERSION=6`): **3 failed, 18 deselected**. The installed KiCad's
DRC/ERC JSON is rejected by the existing native adapter. This change does not
modify that adapter. The broader suite includes all 15 new trust regressions.

The implementation was made locally on `codex/general-electrical-reasoning`.
Only a separate review branch is published, with a draft PR stacked against that
branch, to avoid advancing the branch used by Render. No merge or deployment;
PR #9 and its security branch are untouched.
