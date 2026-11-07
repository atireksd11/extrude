# Extrude

Extrude is a local workspace for reviewing changes across a hardware project's GitHub repository: PCB, schematic, CAD, firmware, code, BOM, and documentation.

Paste a repository URL, select a commit, and run an audit. Supported checks show evidence from the saved revisions, links between related files, and what still needs manual review. An optional AI review summarizes the existing audit after you explicitly approve sending selected evidence to the configured model provider.

## Start locally

Requires Python 3.11 or newer and Git. Python 3.11 or 3.12 is a practical starting point for native CAD dependencies.

```sh
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install '.[dev]'
python -m uvicorn extrude.api.server:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/projects. Saved repositories, settings and audits stay in local `data/`, which is excluded from Git. Copy `.env.example` to `.env` and set your own provider credentials only if you want AI review. Never commit `.env`.

Install KiCad separately for DRC, ERC, schematic netlists, and board/schematic parity. The native integration was exercised with KiCad 10.0.6. Set `KICAD_CLI_PATH` if it is not discovered automatically. Missing tools or unsupported files appear as coverage gaps.

## Current scope and next work

This is an assisted local pilot, not a hosted team service. See [current product status](docs/CURRENT-STATUS.md) for implemented features and limitations, and [the pilot build plan](docs/PILOT-BUILD-PLAN.md) for the technical phases and acceptance gates. The next step is Phase 5: test the import-to-finding workflow with real builders and fix the problems they encounter.

The repository also retains an older circuit-generation and validation harness. Its experiments and historical architecture documents are separate from the current workspace MVP.

The long architecture write-up is [docs/architecture/hardware-ai-master-blueprint.md](docs/architecture/hardware-ai-master-blueprint.md).

Start with the one-page room map: [docs/MAP.md](docs/MAP.md).

For the verified Muse, Linear, Codex Cloud, and GitHub workflow, see the [Extrude operating guide](docs/EXTRUDE-OPERATING-SYSTEM.md).

The first local project change-map pilot is at `/projects` when the API is running. Setup and its two-week pilot plan are in [docs/PROJECT-MAP-MVP.md](docs/PROJECT-MAP-MVP.md).

For the install, offline tests, and Docker commands, see [the Slice 0 stabilization gate](docs/SLICE-0-STABILIZATION.md).

Atlas can also import and compare GitHub commits locally. See [the GitHub history guide](docs/SLICE-1-GITHUB-HISTORY.md).

For a changed KiCad board, Atlas compares footprint placement and pad net assignments. See [PCB comparison](docs/SLICE-2-PCB-COMPARISON.md).

The GitHub workspace also compares native schematic symbols and runs KiCad DRC,
ERC, and matched schematic/PCB parity on both saved commits. Findings retain
their source files and distinguish new, existing, and resolved issues. Missing
tools, libraries, or sheets remain visible as unverified checks. See the
[Phase 2 report and testing steps](docs/PHASE-2-KICAD-REPORT.md).

Phase 3 adds STEP/STP, STL/OBJ previews and measurements, explicit board/cavity
checks, literal firmware pin mapping, and scoped CSV/TSV BOM checks. Use
**Project check setup** in the GitHub workspace to declare units, orientation,
package-pad mappings and BOM columns. The same CAD reader is exposed as a typed,
read-only tool for the future agent. See the [Phase 3 report](docs/PHASE-3-WORKSPACE-REPORT.md).

Phase 4 adds **Connections** between scoped schematic/PCB components and declared
BOM, firmware and CAD files. **AI review** can prioritize a saved audit after an
explicit provider-data disclosure and click. Its citations and certainty are
validated against the original report. See the [Phase 4 report](docs/PHASE-4-AUDIT-REVIEW.md).

The older circuit-generation claim remains gated by the practice-set bar in [docs/GROUND-RULES.md](docs/GROUND-RULES.md): Luna at least 40%, and Astra at least 73%, each on two full runs. The project map is a separate local pilot for invited testers.
