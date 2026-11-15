# M1 electrical ingestion robustness — memory-gated fallback

This draft is stacked on `codex/general-electrical-trust-blockers` at
`b04aad503f7e11c1ecf48a8be2f8a87451857234` (PR #11). It retains every cap and
adds tolerant text decoding and per-file failure isolation. Rule version is 8;
findings schema remains v4. No new electrical checks or false-flag fixes.

## Memory gate: failed

Pinned Lily58 `58c649797c185b7b32b9928d4546665153cfacfd`,
`Pro_V2/Pro_V2.kicad_pcb`: 8,892,279 bytes, 312 footprints.
The measured file is byte-identical to that commit's Git blob:
SHA-256 `7cf6645dbc5ac7684f6a70af6690e9b64eef3b32c9e9be8cf89b57ff6c06a483`.

The first fresh-process `resource.getrusage` result was 309,468 KiB (302.2 MiB).
The requested clean recheck used a fresh Python process with only the repository's
PCB parser imported; no audit runner or test infrastructure. GNU time reports:

```text
Maximum resident set size (kbytes): 309448
Elapsed (wall clock) time (h:mm:ss or m:ss): 0:03.32
Exit status: 0
```

**309,448 KiB = 302.2 MiB; the 256 MB gate fails.** Do not ship the 32 MiB cap.
The system lacks `/usr/bin/time`, so Debian's GNU time 1.9 `/usr/bin/time` binary
was extracted from `time_1.9-0.2_amd64.deb` into `work/gnu-time` and executed there.
The measurement command, from the repository root, was:

```sh
/workspace/work/gnu-time/usr/bin/time -v .venv/bin/python -c 'from extrude.parse import kicad_pcb; kicad_pcb.MAX_BOARD_BYTES = 32 * 1024 * 1024; data = open("/workspace/work/Pro_V2.kicad_pcb", "rb").read(); board = kicad_pcb.parse_board(data); print(len(data), len(board.footprints))'
```

The subprocess-only override permits measurement of the otherwise rejected input.
No production cap is raised: `collect()` regular blobs, `MAX_BOARD_BYTES`,
`MAX_SCHEMATIC_BYTES`, `MAX_FILE_BYTES`, and `electrical_graph.MAX_BYTES` stay
at 8 MiB. The 256-file / 64 MiB limits and other domain/graph caps are retained.

## Failure semantics

- Replace invalid UTF-8 at every specified decode site, including the workspace
  BOM and mapped-netlist readers used by cross-file electrical checks.
- Record path-specific not-checked coverage for replaced text, while keeping
  supported ASCII facts available. A valid, already-encoded U+FFFD is not treated
  as invalid UTF-8.
- Isolate blob read/oversize failures, missing blobs, malformed sheets, unsafe
  dependencies, cyclic hierarchies, root analysis failures, CSV parser errors,
  and per-file model scans. Do not discard other designs' findings.
- The total input budget still admits at most 64 MiB; a candidate crossing that
  budget is skipped with per-file coverage. File-count and inventory caps remain
  repo-wide guards.
- `workspace_audit.py` changes only `RULE_VERSION`; its last-resort handler is
  unchanged. Tests call the real workspace collector and assert that bad firmware,
  malformed schematics and oversized PCBs never enter that handler.

## Pinned local audit results

The external `hidden_files/deep-test-3-2026-11-15/run_extrude.py` harness and
`files/deep-test-3-ground-truth-2026-11-15.md` are absent from this workspace and
repository. The four comparison pins and expected Nov 15 counts/rule families were supplied explicitly.
Use the permitted equivalent: pre-seeded bare mirrors, revision = pinned HEAD,
base = the supplied parent (first parent for the original three), then the production `workspace_audit._descriptor()` and
`workspace_audit._collect()` entry points. No other layers were stubbed in these
runs. A separate direct `electrical_reasoning.collect()` run confirms the same
layer outcomes. No repository source or firmware was executed.

| Repository | Pinned HEAD | Electrical layer |
| --- | --- | --- |
| ErenErenel/Webcam-Design | `3b5b1e54f0711e720bdcf7477e6e2bbe46252c03` | ran |
| greatscottgadgets/hackrf | `3a63b29953a3b763f428821e02110def9fb1cade` | ran |
| kata0510/Lily58 | `58c649797c185b7b32b9928d4546665153cfacfd` | ran |
| foostan/crkbd | `1747b2623b018a7b5acc6d1f7e316debad96a727` | ran |
| OLIMEX/ESP32-POE | `deb38a377d50eadb04ddc7118a17a5ae58b1ee53` | ran |
| BrijModi/ESP32-Dev-Kit-Clone | `ab7d6491243f16dd0895d63786f04da362e704fb` | ran |
| Rufilla/ESP32_HAT | `b02f0acafc18509c680914fab8fbd77329ffb6d9` | ran |

Webcam reports replacement coverage for `conf_board.h` and `conf_clock.h`;
hackrf reports it for `firmware/common/rad1o/ubuntu18.c`. Lily58 reports
`Pro_V2/Pro_V2.kicad_pcb` as not checked at the retained 8 MiB cap and audits the
remaining inputs. **AC3 is unmet under the authorized fallback.** Independent
roots are retained; synthetic tests separately prove root isolation.

All seven layers ran without entering the whole-layer last-resort handler. The
four additional audits use the explicitly supplied bases:

| Repository | Audit base |
| --- | --- |
| crkbd | `e79413032d6f9330e49daf55904cf98e044d0686` |
| esp32-poe | `a9ccb127e4eff6bf58b2e366adc8dca24b42d9e7` |
| dev-kit-clone | `450925bff4c8bf19286b07161e380fdc0605ad99` |
| esp32-hat | `fc350ccad8c98bb4546be56dcdc388805259c1ee` |

The crkbd HEAD is a merge commit. The supplied base is its **second parent**;
that exact base was used, rather than the first parent `63366fb7...`.

## AC6 comparison: fails against Nov 15; identical to PR #11

The user supplied the missing pins and Nov 15 counts/rule families. Original raw
Nov 15 JSON remains outside this environment, so reconstruct the full exact
summary strings by running the same production audit from archived PR #10 source
at `20d66bbd27750c5b437b4a0b009a2133f4533d74`. Its electrical counts and rule
families match all four supplied expectations exactly: **35 / 15 / 1 / 3**.
Also run unmodified PR #11 source at
`b04aad503f7e11c1ecf48a8be2f8a87451857234` and this draft at
`a7ae97e85bc1992da4e9d2ccf7ef464c0449208b` against the identical pinned inputs and
supplied bases. Archived trees use the same dependency environment; each run
imports from its own source tree, with independent application-state folders.

For each electrical layer, filter `electrical.*` findings, sort the
`(rule_id, summary)` list **preserving duplicates**, serialize as compact UTF-8
JSON with `ensure_ascii=False` and a trailing newline, and compare the resulting
bytes. The evidence JSON records SHA-256 hashes for all three source revisions,
exact rule-family counts, delta counts, examples, and the retained genuine hits.
Coverage and unrelated/native diff findings are excluded from this layer-specific
comparison. No normalization of references, values, or summary text is applied.

| Repository | Nov 15 / reconstructed PR #10 | PR #11 | PR #12 | Identical to Nov 15? | Identical to PR #11? |
| --- | ---: | ---: | ---: | --- | --- |
| crkbd | 35 | 469 | 469 | no | yes |
| esp32-poe | 15 | 19 | 19 | no | yes |
| dev-kit-clone | 1 | 1 | 1 | yes | yes |
| esp32-hat | 3 | 1 | 1 | no | yes |

Differences already present on PR #11:

- **crkbd:** 434 added `electrical.assembly` findings. All original 35 findings
  remain byte-identical, including USB ×4, protection ×4, clock ×4, pull-up ×8,
  and model ×15 findings.
- **ESP32-POE:** four added `electrical.assembly` findings: C29 PCB-only ×3 and
  R23 PCB-only ×1. All original 15 remain byte-identical.
- **Dev-Kit-Clone:** the original single J1 protection finding is byte-identical;
  no additions or removals.
- **ESP32 HAT:** the two `electrical.pullup` findings are absent on PR #11 and
  PR #12. The original Y1 clock finding remains byte-identical.

The **nine genuine OLIMEX findings are retained exactly**: USB-UART1 protection
×3, C1 capacitor derating ×3, and C7 capacitor derating ×3. The **one genuine
Dev-Kit-Clone J1 protection finding is retained exactly**. Full strings and
multiplicities are recorded in the evidence JSON.

**AC6 fails as written against the supplied Nov 15 PR #10 expectation.** It is
not blocked by missing pins anymore. PR #12 adds no finding differences relative
to its required PR #11 base: all four canonical finding files are byte-identical
to PR #11. This evidence update does not change production rules or chase the
pre-existing flags. M1's layer-outcome target is now verified on all seven repos;
AC3 remains unmet under the authorized memory-gated fallback.

Machine-readable measurements, pins, outcomes, and input degradation are in
[evidence/electrical-robustness-2026-11-15.json](evidence/electrical-robustness-2026-11-15.json).

## Validation and baseline errors

Baseline at unmodified PR #11 head:

```text
Targeted: 105 passed, 3 failed
Atlas:   114 passed, 3 failed, 284 deselected
```

All failures are in `tests/test_kicad_audit.py`, with captured error output:

```text
FAILED test_real_native_phase2_gate
E AssertionError: ... KiCad DRC JSON is invalid or lacks required check coverage.
E ... KiCad ERC JSON is invalid or lacks required check coverage.

test_native_hierarchical_sheet_evidence, line 249:
> assert result.outcome == "ran", result.detail
E AssertionError: KiCad ERC JSON is invalid or lacks required check coverage.
E assert 'failed' == 'ran'

test_native_workspace_api_gate, line 276:
> assert all(row["outcome"] == "ran" for row in report["coverage"]
>            if row["tool"] == "kicad-cli" and row["check"] != "Library consistency")
E assert False
```

The full stdout/stderr logs were captured locally for both baseline and final
runs; native adapter failures were not skipped or repaired in this work.
Final completed-tree results:

```text
Targeted: 132 passed, 3 failed (same three as baseline)
Atlas:   141 passed, 3 failed, 284 deselected (same three as baseline)
New robustness regressions: 27 passed (included in both runs)
Workspace UI gate: PASS
Formatting: git diff --check passes
```

There are no new failing tests relative to PR #11.

Targeted invocation:

```sh
.venv/bin/python -m pytest tests/test_electrical_robustness.py \
  tests/test_trust_blockers.py tests/test_electrical_reasoning.py \
  tests/test_kicad_pcb.py tests/test_github_workspace.py \
  tests/test_workspace_phase3.py tests/test_workspace_phase4.py \
  tests/test_kicad_audit.py -q
.venv/bin/python -m pytest tests -m atlas -q
node tests/ui/github_workspace.test.cjs
```

The robustness regressions include non-UTF-8 firmware (including all-invalid bytes
and empty files), schematic/PCB/BOM/library-table/JSON/netlist text, malformed
sheets, cyclic/unsafe dependencies, root exceptions, CSV exceptions, blob read
exceptions, independent roots, and the real whole-layer-handler regression.
A padded 8 MiB PCB parses; padded 10 MiB and 40 MiB boards degrade per file under
the fallback. These intentionally replace the full-spec 10 MiB parsing assertion,
which would violate the retained cap.
