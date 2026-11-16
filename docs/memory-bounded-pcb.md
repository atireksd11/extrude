# M1 memory-bounded PCB parse evidence

Base: PR #12 `08e1373fba8d75a3f5ffb45bb7a710dee21920df`.
Rule version 9; findings schema 4. Draft stack remains merge blocked pending M3.

## Profile before editing production code

Pinned `kata0510/Lily58@58c649797c185b7b32b9928d4546665153cfacfd`,
`Pro_V2/Pro_V2.kicad_pcb`: 8,892,279 bytes, 312 footprints,
SHA-256 `7cf6645dbc5ac7684f6a70af6690e9b64eef3b32c9e9be8cf89b57ff6c06a483`.
Python 3.12.14, kicad-tools 0.27.0, Linux ru_maxrss in KiB.

| Phase | Fresh untraced peak RSS (KiB) | MiB | Separate tracemalloc current / peak bytes |
| --- | ---: | ---: | ---: |
| Decode | 52,148 | 50.93 | 26,677,928 / 35,570,536 |
| Whole-tree parse_string | 309,884 | 302.62 | 268,957,903 / 268,958,117 |
| Board build | 310,268 | 303.00 | 269,262,567 / 269,264,135 |

The 303.0 MiB baseline reproduces 302.2 MiB within 0.3%, before any parser
change. The profile bypasses only the existing size refusal on this valid
pinned board. The whole tree is the load-bearing allocation; Board build adds
only about 0.3 MiB of tracked allocations. Tracemalloc raises RSS itself: the
separate traced process peaks at 52,136 / 661,760 / 662,528 KiB at these phases.
Its RSS is not used for the gate.

## Fresh minimal-process gate after the change

| Input | Bytes | Footprints | Peak RSS KiB | MiB |
| --- | ---: | ---: | ---: | ---: |
| Lily58 Pro_V2 | 8,892,279 | 312 | 57,848 | 56.49 |
| Padded clean phase2 board | 10,485,760 | 3 | 46,036 | 44.96 |
| Padded clean phase2 board, exact cap | 33,554,432 | 3 | 91,124 | 88.99 |

Each row was measured in a separate process importing only resource, sys, and
the production PCB parser, retaining raw bytes and the returned Board. All are
below 256,000,000 bytes, and below the 200 MB target. A repeat using the checked-in
profile command measured Lily58 at 57,944 KiB. The first implementation probe,
before enabling the production cap increase, measured 57,860 KiB.

Reproduce with:

```sh
.venv/bin/python tests/profile_pcb_memory.py PATH
.venv/bin/python tests/profile_pcb_memory.py PATH --whole-tree
.venv/bin/python tests/profile_pcb_memory.py PATH --whole-tree --trace
```

The manual whole-tree mode measures the valid-board PR #12 walk using the
unchanged extraction helpers; it does not expose that path to production.

## Compatibility and bounds

All 42 native PCBs fitting the old cap across the seven pinned repos were
extracted from bare mirrors and tested with old vs new extraction: **42/42
byte-identical** compact, sorted-key UTF-8 JSON of every Board dataclass field.
Counts: webcam 1, hackrf 5, Lily58 6, crkbd 12, ESP32-POE 16,
Dev-Kit-Clone 1, ESP32_HAT 1. Pro_V2 is separately covered by the memory gate.
The new tests also compare exact compare_boards rows on small fixture pairs.

Opt-in corpus test: set EXTRUDE_PCB_EQUIVALENCE_MANIFEST to a JSON list of local
PCB paths, then run tests/test_memory_bounded_pcb.py. Without external files the
corpus case explicitly skips; the synthetic cases always run.

GC tests check GC is enabled before each real per-form parse, then deliberately
leave it disabled on both successful return and exception. The wrapper restores
it in both cases under the original lock. Trees are discarded after extraction;
only footprint spans wait for all net declarations, preserving out-of-order nets.

Synthetic tests cover 10 MiB / exact 32 MiB parsing and paired electrical
assembly coverage, 40 MiB per-file refusal with independent good findings,
8 MiB per-form guards for footprints and skipped geometry, quotes/escapes and
parentheses, legacy modules, malformed and empty inputs, wrong roots, no pads,
no footprints, net zero, conflicting net definitions, and unchanged schematic
blob limits. MAX_FILE_BYTES in kicad_snapshot stays 8 MiB: it bounds native-tool
materialization, not electrical collect's direct PCB blob reads.

## Suites

PR #12 baseline: targeted 132 passed / 3 failed; Atlas 141 passed / 3 failed.
Final targeted with the external corpus enabled: 152 passed / the same 3 failed.
All 42 corpus boards ran in that invocation. Final Atlas: 160 passed /
the same 3 failed / 1 external-corpus skip / 284 deselected. Workspace UI passed.

Pre-existing failures, unchanged:

- test_real_native_phase2_gate
- test_native_hierarchical_sheet_evidence
- test_native_workspace_api_gate

All are in tests/test_kicad_audit.py and report incomplete/invalid native KiCad
DRC/ERC JSON coverage. CadQuery 2.8.0 imports and its targeted checks pass here;
the previously reported CadQuery environment failure did not reproduce.

Commands:

```sh
.venv/bin/python -m pytest tests/test_memory_bounded_pcb.py \
  tests/test_electrical_robustness.py tests/test_trust_blockers.py \
  tests/test_electrical_reasoning.py tests/test_kicad_pcb.py \
  tests/test_github_workspace.py tests/test_workspace_phase3.py \
  tests/test_workspace_phase4.py tests/test_kicad_audit.py -q
.venv/bin/python -m pytest tests -m atlas -q
node tests/ui/github_workspace.test.cjs
```

## Independent verification limitation

Deep Test 3 harness NOT run in this task — harness and ground-truth files are local-only on the operator machine; the independent verify job runs the harness tonight against this branch and checks AC5/AC8.

Local direct electrical.collect comparisons below are independent production
function checks, not a reconstruction of that harness or its ground truth.

| Repo | PR #12 electrical findings | New | Direct collect outcome |
| --- | ---: | ---: | --- |
| Webcam-Design | 3 | 3 | ran |
| hackrf | 3 | 3 | ran |
| Lily58 | 12 | 12 | ran |
| crkbd | 469 | 469 | ran |
| ESP32-POE | 19 | 19 | ran |
| ESP32-Dev-Kit-Clone | 1 | 1 | ran |
| ESP32_HAT | 1 | 1 | ran |

For every repo, the entire serialized finding multiset is byte-identical to a
fresh run of archived PR #12 code against the same pinned input. This is stronger
than comparing counts or only rule_id/summary pairs; duplicates are preserved.
Total electrical findings remain 508, delta zero. Applying the supplied PR #12
classification leaves 497 false flags unchanged; no independent classification
or ground-truth reconstruction was attempted. There are no individual finding
additions/removals to explain. Pro_V2 now has Electrical assembly outcome ran,
with no Not checked electrical entry. Harness AC5 and AC8 remain explicitly
pending independent verification.
