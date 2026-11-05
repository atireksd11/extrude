# Phase 3: CAD, firmware, and BOM readers

Implemented November 4, 2026. **The controlled Phase 3 gates pass.** STEP/STP is
included alongside STL/OBJ, following the expanded scope. The application reads
the team's actual chassis STEP assembly. Full board/cavity and firmware/BOM
cross-checks on that project still require the explicit mappings described below.

## What is available in the product

- Open a saved STEP/STP or STL/OBJ file in the GitHub tree. The inspector shows
  dimensions, units, before/after facts, and a draggable 3D preview within the
  display limits. STEP also provides solid/face counts, topology validity, and
  the sum of solid volumes. It retains assembly placements, but does not recover
  parametric construction history or edit the imported model.
- Open **Project check setup** to add board/enclosure, firmware/pin, and BOM
  mappings. Forms persist through the local settings API. These mappings apply
  to both saved commits in a comparison; changing settings invalidates the audit
  cache without modifying Git files.
- Run an audit. It retains the Phase 2 KiCad checks, reads supported changed
  artifacts, and runs each configured cross-file check on both revisions.
  Findings cite exact files, commits, source lines, nets/pads, and measurements.
  Missing context remains visible in coverage.
- The same CAD reader is available as a typed, read-only tool for a future
  agent. No model is connected to it yet and no arbitrary CadQuery/Python code
  execution endpoint was added.

Refresh `http://127.0.0.1:8000/projects/github` after the backend restart. Open the
chassis STEP file in the tree to test the reader without configuring relationships.

## Research and library selection

| Option | Decision and reason |
| --- | --- |
| [Trimesh](https://trimesh.org/trimesh.exchange.load.html) | Pinned 5.2.0. Used for STL/OBJ geometry from byte streams. Explicit file types, empty resolver, remote assets disabled, and material loading skipped. These formats do not establish physical units; the project mapping must supply them. |
| [CadQuery](https://cadquery.readthedocs.io/en/latest/importexport.html) + [OCP](https://pypi.org/project/cadquery-ocp/7.9.3.1.1/) | Pinned CadQuery 2.8.0 and compatible cadquery-ocp 7.9.3.1.1. Used now for STEP BREP geometry in a fixed worker process. Import explicitly normalizes length units to mm. This also gives the future agent a useful geometry foundation. |
| [pythonocc-core](https://github.com/tpaviot/pythonocc-core/blob/master/INSTALL.md) | Another OCCT binding. Not installed alongside OCP: that would duplicate the geometry stack without improving the current read-only checks. |
| [CADParser](https://github.com/spicywagyu04/CADParser) | Its documented task reconstructs modelling command sequences using a trained model. It is not the deterministic file reader used for these acceptance checks. No weights or reconstruction pipeline were integrated. |
| Autodesk / Cascade-Share | No exact repository was established from that name. No capability was assumed from it. [Autodesk's documented Data Exchange offering](https://aps.autodesk.com/developer/overview/data-exchange-api) is a separate service integration, which this local reader does not need. |

The implementation uses the installed libraries rather than copying these
repositories into Extrude. CadQuery and OCP versions were checked against their
available Python 3.14 Windows wheels, then verified by actual imports and geometry
tests. `pip check` reports no broken dependency requirements.

## CAD: measured scope

`extrude/parse/workspace_mesh.py` reads STL/OBJ bounds, triangles and closure.
Duplicate STL facet vertices are merged before measuring closure; holes are not
filled and geometry is not repaired. All coordinates must be finite. Materials,
textures, URLs, and adjacent files are never resolved.

`extrude/cad_worker.py` imports a single inert STEP file using CadQuery. It
measures BREP bounds before display tessellation. The sum of imported solid
volumes does not subtract overlaps and is labeled accordingly. STEP previews
use a complete coarse tessellation when it fits the display budget; dropping
arbitrary triangles would make solids appear to have holes. If the coarse mesh
is still too large, measurements remain available with a preview-unavailable note.

`extrude/workspace_cad.py` starts that fixed worker using an argument array,
isolated Python import mode, a fresh directory, and a small environment without
application credentials. It accepts no script or command input. Successful
results are atomically cached by blob content, worker version, tool versions,
and preview settings. Inputs and outputs are cleaned up after failure or success.

`extrude/parse/workspace_mesh.py:board_spans` reuses the pinned KiCad outline
helper for Edge.Cuts extrema. Missing, unreadable, open or branched outline paths
cannot produce a measured board/cavity finding. Outline self-intersection and
complete topology validation remain KiCad's responsibility.

A board/enclosure mapping declares:

```json
{
  "board_file": "hardware/main.kicad_pcb",
  "mesh_file": "cad/enclosure.step",
  "units": "mm",
  "mesh_kind": "exterior",
  "board_axes": ["x", "y"],
  "cavity_mm": [95, 70, 20]
}
```

STL/OBJ units may be mm, cm, m, or inches. STEP coordinates are normalized to mm
and its mapping must use mm. `board_axes` maps board X and Y to two distinct
enclosure axes. This supports an explicitly axis-aligned installation, not
arbitrary rotations. `cavity_mm` supplies declared inner dimensions in the CAD
frame. Alternatively, `mesh_kind=cavity` identifies a closed exported cavity
volume whose bounds can be measured. An exterior without cavity information
produces only a review suggestion.

The deterministic finding is **board span exceeds declared cavity span on the
configured axis**. A smaller board receives no complete-fit verdict. These
checks do not establish mounting-hole alignment, collision-free placement,
connector access, tolerances, board/component height, or manufacturability.

## Firmware and code

`extrude/parse/workspace_firmware.py` reads literal integer declarations and
source lines from C/C++/Arduino and Python. It strips C comments/strings, rejects
partial numeric matches, recognizes ambiguous/conditional/reassigned values, and
uses Python AST without importing project modules. Expressions, function calls,
compiler branches and unsupported languages are not guessed. Python syntax
errors remain file-level coverage failures.

A pin rule declares firmware file and symbol, a KiCad netlist or root schematic,
net name, MCU reference, and numbering mode. GPIO mode requires a user-declared
GPIO-to-package-pad dictionary. Package mode explicitly declares that firmware
numbers already identify physical pads. A GPIO value is never silently treated
as a package-pad number.

`extrude/workspace_netlist.py` retains physical pad numbers separately from pin
functions and reuses the existing electrical netlist reader. It rejects duplicate
physical pads or ambiguous connectivity. Committed `.net` files are read directly.
For a mapped root schematic, it materializes the safe KiCad snapshot and runs:

```text
kicad-cli sch export netlist --format kicadsexpr --output <temporary.net> <root.kicad_sch>
```

Exports are memoized separately by repository, exact SHA and source path within
an audit. Missing sheets/libraries, missing CLI, failed exports, unresolved
expressions or absent mappings make the check unverified. No repository build,
firmware program, test command or Python/CadQuery script is executed.

Ordinary code retains Git before/after contents. Literal facts are a narrow
source reader, not proof of runtime behavior, compilation or software correctness.

## BOM

`extrude/parse/workspace_bom.py` uses `csv.DictReader` with declared column names
and delimiter. Part numbers remain strings, including leading zeros. CSV/TSV
facts are available in the inspector; XLSX is visible but unsupported for analysis.

CSV inspection renders a table with highlighted before/after cells, a changed-row
filter, and bounded row pagination. Shopping lists with a unique `Item` or `Part`
column are compared directly without schematic setup. Exact item/reference/part
identifiers anchor matches; row reordering does not invent changes. Duplicate or
blank identifiers remain unmatched, and an unreadable side cannot yield a clean
comparison. Columns added/removed are explicit. These observations do not claim
schematic validation, procurement arithmetic or currency conversion.

The CAD-only pilot comparison from `32e1f56640a2171e521edb4dcd9ca116acd6d9b4`
to `53a7a92adb0b6bb0408f8082e48b3bb714a5a0f6` detects one cell change:
`Estimated total shipping`, `Total Cost`, `$3.70` to `$3.72`. It is recorded as an
observed BOM finding with both CSV source lines. Report schema remains version 3;
rule version 4 invalidates earlier cached audits for the added cell comparison.

A BOM mapping supplies its assembly's root schematic, reference/MPN/quantity
columns, and an optional DNP/exclusion column. Simple grouped references such as
`R1, R2` and `R3-R5` are supported. Invalid ranges, duplicate references,
unreadable flags or quantities are excluded from verified missing-part claims.
Duplicate references invalidate the earlier occurrence as well as the later one.
Ambiguous head rows cannot silently resolve baseline findings.

Checks report changed part numbers, quantities/population flags, quantity versus
listed-reference count, and BOM references absent from the configured assembly.
DNP rows skip missing-part checks. Known schematic DNP/excluded components skip
the normal population quantity verdict. Quantity comparisons assume one assembly;
procurement lot quantities or multiple builds need separate semantics. A shopping
list without design references is not automatically matched to schematic parts.

## APIs, cache and UI

| Endpoint | Purpose |
| --- | --- |
| `GET/PUT /v1/github/repositories/{id}/settings` | Validated, persistent project mappings. Unknown fields and invalid axes, units, paths, or duplicate mappings are rejected. |
| `GET /v1/github/repositories/{id}/artifact` | Revision-pinned before/after geometry, CSV or literal source facts; optional previous path supports renames. |
| `POST /v1/github/repositories/{id}/cad/inspect` | Typed read-only CAD tool, OpenAPI operation ID `inspect_project_cad`; request contains revision, path, and preview flag only. Response includes exact SHA, geometry facts, and evidence. |
| Existing audit endpoints | Persist Phase 3 results using the shared version-3 report. |

Audit descriptors freeze the selected project settings. Workers never silently
switch mappings when settings change mid-run. Cache keys include those settings,
Trimesh/CadQuery/OCP versions and reader/worker limits. Existing Phase 2 reports
remain readable, but are not served as the current version-3 comparison.

The GitHub inspector renders CAD, CSV and source facts separately from raw text.
Native/checker findings use lifecycle and certainty labels. Repository text and
paths are rendered as text. Stale artifact responses cannot overwrite the next
file or commit selection, and mesh observers/frame work are disposed on navigation.

## Limits and failure behavior

- STL/OBJ: 8 MiB, 100,000 triangles, sampled preview up to 1,800 triangles.
- STEP: 32 MiB, 30-second worker timeout, two concurrent CAD workers, bounded
  JSON output, complete coarse preview up to 16,000 triangles. Complex previews
  may be unavailable even when measurements work.
- Source: 512 KiB, 256 declared constant names per file.
- BOM: 1 MiB, 2,000 CSV records, 10,000 references with bounded range expansion.
- Netlists: 2 MiB; at most six native exports per audit, 20 seconds per export
  within a 90-second export budget.
- Phase 3: at most 60 changed artifacts and 500 findings; truncation is explicit
  coverage, not a clean result.

These subprocesses provide failure/timeout isolation for a local pilot. They
are not an OS security sandbox or a hard memory quota. A separately isolated,
resource-limited worker is still required before hosting arbitrary untrusted
CAD uploads or executing agent-generated design scripts.

## Gate evidence and remaining validation

| Criterion | Status | Evidence |
| --- | --- | --- |
| Board versus cavity | Passed | Controlled Git revisions move a board from 90 to 100 mm and a cavity from 100 to 95 mm. The head reports exactly 100 mm > 95 mm with file/axis evidence. Baseline is quiet for that rule. |
| CAD uncertainty | Passed | Exterior-only gives a suggestion; missing units/invalid axes are rejected; open or missing Edge.Cuts gives no measured verdict. A smaller board is explicitly not approved as a complete fit. |
| STEP units and assemblies | Passed | Real CadQuery STEP input with inch-valued coordinates normalizes to 100 × 60 × 20 mm. A translated two-solid assembly measures 300 mm across both placements. |
| Actual project STEP | Passed | `atireksd11/astra-companion` at `0c8afb27b14d1b6190441f2ab683fe8058f7e7f0`, `cad/astra-companion-chassis-assembly.step`: 18 solids, 1,274 BREP faces, approximately 151.083 × 84 × 170 mm. No inner cavity is inferred from that whole assembly. |
| Firmware mismatch | Passed | A saved literal changes from 12 to 13 while the configured MCU/net remains on physical pad 12. Matching declared mappings are quiet; expressions, multiple assignments, runtime assignments and missing netlists remain unverified. |
| Native schematic export | Passed | Actual KiCad exports the mapped native schematic; the reader retains physical pad 1 and scoped component references. Temporary data is removed. |
| BOM | Passed | Leading-zero MPN change, quantity change and unknown reference detected. Quoted fields/ranges are preserved. DNP and ambiguous/duplicate references do not create false missing-part findings. An ambiguous head cannot produce a false resolved result. |
| API and persistence | Passed | Settings validation, cache invalidation/frozen mappings, audit worker, evidence preview, artifact endpoint and typed CAD tool tested together. Unknown script input to the CAD tool is rejected. |
| Previous product behavior | Passed | Existing Git history, workspace workers/API, PCB diff and native KiCad gates pass after the integration. |
| Frontend | Passed in DOM checks | STEP metadata, stale artifact responses, settings save/render, and previous review navigation are checked. A new visual browser walkthrough is not claimed. |
| Own-project cross-domain verdicts | Pending configuration | Actual chassis parsing is verified. The project's shopping BOMs lack explicit reference columns, and no GPIO-to-package/cavity mappings have been supplied. Those checks correctly remain unavailable rather than guessing. |

The final live server check returned HTTP 200 for the workspace and the new setup
forms. Its CAD tool returned the actual chassis with a complete coarse preview
of 14,190 triangles. The version-3 audit on the saved project completed as
partial, with explicit missing CAD, firmware and BOM mapping coverage.

Evidence artifacts:

- `data/phase3-controlled-gate.json`: exact controlled repository/commit pair,
  declared mappings, source evidence and findings.
- `data/phase3-astra-step.json`: actual chassis measurements and preview facts.
- `data/phase3-live-cad.json`: live local API CAD-tool response.
- `data/phase3-astra-audit.json`: actual project's audit, including readable
  changed source files and the explicit missing mapping coverage.

Repeat the gates with:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_workspace_phase3.py -q --basetemp=data/pytest-phase3-review
.venv/Scripts/python.exe -m pytest tests/test_kicad_audit.py tests/test_kicad_pcb.py tests/test_github_workspace.py tests/test_github_history.py -q --basetemp=data/pytest-phase3-regression-review
node tests/ui/github_workspace.test.cjs
```

The smallest next user test is to open the existing STEP file, then configure one
known cavity or one documented firmware/net mapping. The AI explanation and
broader relationship work remain Phase 4.
