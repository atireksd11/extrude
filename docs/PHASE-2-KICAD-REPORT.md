# Phase 2: native KiCad audit and schematic context

Built on November 4, 2026. **Required native gates passed locally; optional PCB
heuristics deferred.** This phase adds actual engineering checks to the saved
Git workspace. It does not implement CAD fit checks, BOM validation, firmware
pin mapping, or AI explanations; those remain the next phases.

## What a tester can do

1. Open `/projects/github`, import/sync a KiCad repository, and select a commit
   and baseline. Leave the baseline blank to compare with the first parent.
2. Open a changed `.kicad_sch`: the inspector compares placed symbol references,
   values, footprints, and units. Added, removed, and renamed files retain their
   correct Git sources. This comparison does not infer electrical connectivity.
3. Click **Run audit**. The worker compares PCB placement/pad assignments and
   schematic facts, then runs native KiCad on both immutable snapshots. Even an
   unchanged board is checked when reviewing a code/settings-only commit.
4. Read findings labeled **New finding**, **Already present**, **Resolved**, or
   **Present at selected commit · Baseline unverified**. Open a finding to inspect
   its source file and object UUID at the cited SHA. Parity findings link to the
   matched root schematic. Hierarchical ERC findings cite the actual child file.
5. Expand coverage. Unsupported domains, missing dependencies, checker failures,
   timeouts, ignored native rules, and unavailable optional checks remain visible.
   A partial report is not an engineering approval.

KiCad is discovered from `KICAD_CLI_PATH`, PATH, or the standard Windows/macOS
install location. Native JSON integration accepts KiCad 9/10; **10.0.6 on Windows
is the tested installation**. No model or paid API is needed for this phase.
Restart an already-running backend after updating Python files; refresh the page
to load the revised inspector.

The local backend was restarted after implementation. A live HTTP check returned
200 for `http://127.0.0.1:8000/projects/github` and confirmed the new schematic
route in the running server's OpenAPI document.

## Implementation

| Component | What it does |
| --- | --- |
| `extrude/parse/kicad_schematic.py` | Uses pinned `kicad-tools` 0.27.0 S-expression parsing. Reads placed symbols, never embedded symbol definitions. Matches unique UUIDs, then unique references within a sheet. Reads child-sheet dependencies. |
| `extrude/schematic_review.py` | Reads bounded regular blobs from exact commits, preserves absent versus unreadable input, and paginates changes. Exposed as `GET /v1/github/repositories/{id}/schematic`. |
| `extrude/kicad_snapshot.py` | Copies only allowlisted regular KiCad inputs, preserving paths. Includes project settings, design rules, local libraries, and safe library tables. Validates the selected hierarchy, missing children, cycles, traversal, Windows devices/ADS, symlinks, submodules, and case collisions. |
| `extrude/kicad_audit.py` | Runs native DRC/ERC and matched-project parity by argument array. Validates JSON schema, source, required rule groups, and ERC sheet coverage. Accepts exit 5 with a valid violations report. Separates successful checks from tool failures. |
| `extrude/workspace_audit.py` | Stores version-2 shared reports. Cache identity includes commit pair, native availability/version, parser version, executable location, and limits. Existing worker concurrency, retry, atomic persistence, and restart handling remain in use. |
| GitHub inspector | Shows schematic comparisons and native findings without treating them as PCB placement changes. Displays lifecycle, severity, source evidence, and unverified library warnings. |

Native commands follow the [KiCad CLI reference](https://docs.kicad.org/10.0/en/cli/cli.html):

```text
kicad-cli pcb drc --format json --exit-code-violations --output <report> <board>
kicad-cli pcb drc --format json --exit-code-violations --schematic-parity --output <report> <board>
kicad-cli sch erc --format json --exit-code-violations --output <report> <root-schematic>
```

Parity is enabled only for a root schematic in the same directory with the same
basename as the board. An ambiguous, absent, or unreadable root yields explicit
unverified coverage. Connectivity is KiCad's responsibility; netlist export is
not needed until the firmware mapping phase.

Lifecycle matching uses native rule ID, check scope, source path, and stable
object UUIDs. Duplicate/absent identities cannot establish a reliable match.
Both revisions must succeed with matching ignored rules and project/design-rule
settings before reporting new/resolved findings. A failed head check never
silently resolves baseline findings. A moved measurement on the same objects
does not automatically become a new issue. Library consistency depends on the
local installation, so those warnings remain **unverified**.

Limits: 10,000 tree entries, 256 KiCad files, 8 MiB per input, 64 MiB per snapshot,
12 native targets per revision, 500 findings per native check, 40 seconds per
process, and a 180-second native budget across the commit pair. Oversized or
truncated coverage is reported. Scratch directories live under the app data
directory and are removed on success and failure. Reports live separately from
inputs. Child processes receive a fresh tool configuration and a small
allowlisted environment, without application credentials or repository scripts.

This is the local pilot runner, not an OS isolation boundary. An isolated,
resource-limited worker is still required before hosting arbitrary untrusted
uploads as a public checker service.

## Gate evidence

Reproducible inputs live in `tests/fixtures/phase2`. The fixtures are intentionally
small and are not fabrication designs. The clean counterpart is quiet for the
specific seeded error rules; library/grid warnings are not hidden.

| Criterion | Status | Evidence |
| --- | --- | --- |
| Actual native DRC | Passed | Crossing tracks produce `tracks_crossing` with both track UUIDs. Clean counterpart has no finding for this rule. |
| Actual native ERC | Passed | Removing a no-connect marker produces `pin_not_connected` at the pin UUID; restoring it resolves that finding. |
| Actual parity | Passed | Changing only the PCB value produces `footprint_symbol_mismatch` with footprint evidence and the related schematic. Clean counterpart is quiet for this rule. |
| Routing-only change | Passed | `clean` versus `routing` has no footprint/pad changes, but native DRC finds crossing tracks. |
| Inherited and repaired findings | Passed | Crossing remains existing in the next commit; restored schematic/parity produce resolved findings. Failed/absent baselines produce present-at-head instead. |
| Hierarchical source mapping | Passed | Real KiCad ERC on a root/child fixture cites the child schematic and its sheet instance UUID. Missing or escaping children stop the native invocation. |
| Failure handling and cleanup | Passed | Missing CLI, timeout, malformed report, missing child, escaping paths, real Git symlinks and submodule entries, and cleanup after a tool failure are covered. No repo code or parent-process credentials enter the tool environment. |
| Full workspace/API path | Passed | POST audit -> worker -> native CLI -> saved report -> GET audit/workspace -> evidence preview; repeated requests reuse the saved report. Worker/restart and Git-history regressions are also checked. |
| Frontend behavior | Passed in DOM checks | Schematic inspector, native lifecycle text, evidence routing, asynchronous selection protection, and prior UI behavior. A new visual browser walkthrough is not claimed. |
| Team's own hardware project | Pending | The public reference below is a real-project smoke check, not feedback from the robotics team. |

`data/phase2-native-gate.json` records the exact fixture store, immutable base/head
and follow-up SHAs, native version, findings, coverage, and replay results from
the latest gate run. The actual Git objects remain in that recorded test store.

Real-project smoke input: [janelia-kicad/rp2040_minimal](https://github.com/janelia-kicad/rp2040_minimal),
base `6ca7ee395e8170a6f9a2c4bc3a01185c87013a5f`, head
`53a58647c9126f1029388eae2c36df2d15e17106`. DRC, ERC, and parity ran on both
revisions in 14.8 seconds in the final smoke run (35 seconds during an earlier
concurrent run) on this machine. The report contains 89 inherited
native findings, rather than inventing new faults for the selected commit.
Of these, 33 library-dependent results are unverified. The full result is saved in
`data/phase2-public-reference.json`.

## Optional pcb-inspector spike

Reviewed the upstream [manual](https://github.com/takzen/pcb-inspector/blob/main/MANUAL.md)
and package metadata advertising 0.1.0. The configured package index returned
no matching distribution for `pip download --no-deps pcb-inspector==0.1.0`.
Source/tag retrieval did not establish a pinned, executable artifact during this
spike. **No release/commit was run, no heuristic rule output was validated, and
no inspector code was copied into the product. Optional heuristics deferred.**
Coverage explicitly records that decision. We do not claim decoupling, power
width, or differential skew checking from this untested dependency. The required
native checker gates above are independent of it.

## Repeat the checks

```powershell
.venv/Scripts/python.exe -m pytest tests/test_kicad_audit.py tests/test_kicad_pcb.py tests/test_github_workspace.py tests/test_github_history.py -q --basetemp=data/pytest-phase2-review
node tests/ui/github_workspace.test.cjs
```

These tests use local Git fixtures, not remote imports or model calls. Real CLI
gates skip when KiCad is absent; a skip does not satisfy the native release gate
on a new machine. FastAPI's TestClient requires local socket transport permission.
For a manual check, follow the five steps at the top with the team's own project
and a known commit. CAD, firmware, and BOM analysis remain Phase 3.
