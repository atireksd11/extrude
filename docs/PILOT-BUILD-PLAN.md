# Extrude pilot build plan

## What ships

A teammate pastes a GitHub URL, opens a real commit, and sees one workspace for the whole robot. The file tree includes PCB, schematic, CAD, firmware, code, BOM, docs, and other files. The audit explains supported changes and checks. Selecting a finding opens its evidence and the related files. **Explain this audit** turns those findings into a short review list on request. The deterministic audit works independently of that button.

Target five focused workdays for one real pilot repo and one machine running Extrude locally. Use its actual KiCad version, firmware language, BOM columns, and CAD export format. Pick a before/after commit pair and write down one expected result per area before coding. Start testing the workspace as soon as the PCB audit is connected.

## How a phase passes

- Every required criterion in its gate must be demonstrated. A working demo, a passing unit test, and a successful run against a real project are different kinds of evidence. Record which one supports each criterion.
- Keep two inputs. The **pilot repo** shows that the workflow works on real project files. A **controlled Git fixture** contains known good and bad revisions so we can prove that a check detects the intended change and stays quiet when it should.
- After each phase, report **passed**, **failed**, or **blocked** with the repo and commit pair, commands or UI steps, expected and observed results, and remaining gaps. An unavailable required check blocks the phase. The optional pcb-inspector adapter may be deferred under Phase 2's explicit fallback. Calendar days are targets and never override a gate.

### Entry gate · Choose the pilot inputs

Record the repository, immutable base and head SHAs, root schematic, PCB, at least one supported mesh export with units, firmware language, and BOM column names. Record the Git and KiCad versions on the pilot machine. Obtain two readable revisions or use a controlled fixture to supply a deliberately broken case. Agree on the board-to-enclosure and GPIO-to-pad mappings before checking either one. If the real repo lacks a supported artifact, say which domain will only have fixture evidence. A domain with fixture evidence alone does not count as validated on the pilot repo.

Use this format for each phase report:

| Criterion | Status | Evidence | Remaining gap or next fix |
| --- | --- | --- | --- |
| Gate item | Passed / failed / blocked | Repo, commit pair, command or UI steps, expected result, observed result | Owner or next action when relevant |

## Keep the foundation

| Decision | Reason |
| --- | --- |
| Use the existing bare Git store. | It already fetches and retains the default branch's commit history and blobs. A depth-one clone would omit the parent needed for the first comparison. Use Git's tree, diff, and blob commands through the existing Python subprocess wrapper. [Git clone](https://git-scm.com/docs/git-clone) · [Git tree](https://git-scm.com/docs/git-ls-tree) · [Git objects](https://git-scm.com/docs/git-cat-file) |
| Materialize files only for tools that require paths. | The PCB parser already accepts bytes. KiCad CLI and pcb-inspector need a project directory with the original relative paths. Use a temporary directory scoped to the repo, commit, and audit run. |
| Build the split workspace in the current HTML, CSS, and JS. | Atlas already has the panels, styles, and inspector. Use native `<details>` and `<summary>` for collapsible folders and CSS Grid for the three panes. shadcn/ui is an option if the frontend moves to React. [shadcn Vite setup](https://ui.shadcn.com/docs/installation/vite) |
| Keep Git as the record of files. | Persist only a small JSON audit report under the app data directory, keyed by repo, base SHA, head SHA, tool versions, and a hash of the audit settings. Write it atomically. An in-process lock prevents duplicate runs for the same key in the local pilot. |

## Phase 1 · Day 1 · One GitHub project workspace

1. Use the existing import and sync endpoints in `extrude/api/github.py`. Take the user directly to the imported workspace. Choose the selected commit's first parent by default and retain the existing **Compare with previous sync** option. Show an initial snapshot for a root commit.
2. Build the tree from the selected commit. Classify each file into a domain, then keep its actual directory structure within that domain. Include deleted and renamed files from the comparison in the change list. Paginate large inventories and render file names as text. Each item opens the existing preview or a clear unsupported-file state.
3. Use a tree on the left, changes and findings in the middle, and a file inspector with related files on the right. Keep the existing PCB comparison accessible in the inspector. Show the repo name and base/head SHAs above the review.
4. Define a shared result shape with fields `rule_id`, `domain`, `status`, `summary`, `before`, `after`, `evidence[]`, and `related[]`. Each evidence item has an ID, path, SHA, and a locator such as component reference, pad, or line. Keep statuses separate for an observed change, a verified finding, a review suggestion, and an unverified check. Record successful checks under coverage, with their scope.

Add `GET /v1/github/repositories/{id}/workspace?revision=<sha>&base=<sha>` for the inventory, changed paths, and audit status. Use `POST /v1/github/repositories/{id}/audits` with the two SHAs to run or reuse an audit. Keep tool adapters behind a small Python interface that takes those SHAs and returns findings and coverage. Run the first pilot audit in a bounded worker thread within FastAPI, with one active audit per repo and a visible running state. Expire or bypass cached reports when tool availability changes, and allow retrying failed tool runs.

### API and report contract

- Validate both commits in the selected repository. Resolve an omitted base to the first parent, use an explicit empty baseline for a root commit, and include the resolved pair in every response. A sync may advance the repo tip while the current review stays pinned to its selected pair.
- Audit creation returns an ID and a state. `GET /v1/github/repositories/{id}/audits/{audit_id}` returns `queued`, `running`, `complete`, `partial`, or `failed`. A partial report contains completed findings and identifies each skipped or unavailable check. A stopped process exposes an interrupted run as retryable after restart. Repeated requests for the same active key return the same run.
- Use a versioned report with `repo_id`, `base_sha`, `head_sha`, tool versions, config hash, `findings[]`, and `coverage[]`. Coverage records the target path, check, tool, and outcome: ran, unsupported, unavailable, or failed. A finding records severity separately from certainty. Each evidence ID resolves to the exact repo, SHA, path, and locator. Related links say how they were established.
- Key reusable reports by the resolved commit pair, report schema and rule versions, tool availability and versions, and settings hash. Recompute on a changed key. Never serve a stale report as the current comparison. Write the final report atomically.

### Pass gate

- Import the pilot repo through the UI. One screen shows each project area, its actual paths, the selected SHAs, and the existing PCB comparison. A tester can open an unchanged file, a renamed file, and a PCB change without switching screens.
- Verify root commits, deleted files, renames, and pagination against the controlled repository. Inspecting a deleted file shows the base version. Inspecting a rename opens the correct path on each side. Switching revisions while a request is in flight leaves the latest selection on screen.
- Two concurrent requests for the same comparison reuse the same run. An invalid SHA, interrupted run, and failed import have a clear recovery path. A saved report is readable after restarting Extrude.

The implementation and current gate evidence are recorded in [the Day 1 report](DAY-1-WORKSPACE-REPORT.md). Browser and HTTP transport verification are pending in the current environment.

## Phase 2 · Day 2 · KiCad audit and schematic context

Implementation and local gate evidence: [Phase 2 report](PHASE-2-KICAD-REPORT.md).
Required native checks passed on KiCad 10.0.6; optional pcb-inspector heuristics
are explicitly deferred. Robotics-team project validation remains pending.

1. Keep the pinned `kicad-tools` reader for board facts and the current footprint/pad comparison. Use the same parser on native schematic blobs to compare placed symbol references, values, and footprints. Identify the root schematic and corresponding board by project name or an explicit pilot setting. Treat ambiguous or missing sheets as unverified. Use KiCad to resolve electrical connectivity, including hierarchical sheets. [kicad-tools](https://github.com/rjwalters/kicad-tools) · [KiCad CLI reference](https://docs.kicad.org/10.0/en/cli/cli.html)
2. Build a snapshot helper that copies only regular, allowlisted Git blobs needed for the selected KiCad project. Preserve relative paths for the board, root and child sheets, project settings, custom design rules, and local libraries. Reject paths that escape the snapshot, skip symlinks and submodules, and mark missing dependencies in coverage. Run approved tools by argument array with a timeout, a controlled working directory and configuration, and no application secrets. Use a separate report directory. For the local pilot, run external checkers on the team's known repo. Require an isolated worker before opening this flow to arbitrary public imports.
3. Verify the installed CLI supports the flags on the pilot machine. Run the following against the pinned revision. For parity, use the matching project and schematic, and check that the report actually covers parity. For firmware lookup, export a netlist only when required and reuse Extrude's existing reader.

   ```text
   kicad-cli pcb drc --format json --exit-code-violations --output drc.json board.kicad_pcb
   kicad-cli sch erc --format json --exit-code-violations --output erc.json board.kicad_sch
   kicad-cli sch export netlist --format kicadsexpr --output board.net board.kicad_sch
   ```

4. Add `--schematic-parity` to the DRC invocation for the matched pair. Parse reports for actual findings. A timeout, missing binary, invalid report, or unsupported version yields **unverified**. Run the same settings on both revisions before labeling a finding **new** or **resolved**. If only the head was checked, label it **present at head**. [DRC and parity flags](https://docs.kicad.org/10.0/en/cli/cli.html#pcb-drc)
5. Timebox the `pcb-inspector` spike to half a day. Verify a release or pin a tested Git commit, then run `pcb-inspector check <project> -f json -o <report> -c <trusted-config>` on a known board. Disable vision in the trusted config. If the adapter already ran native DRC/ERC, turn those layers off in the inspector config so the audit reports them once. Import decoupling distance, power trace width, and differential pair length as **review suggestions** with the tool's rule IDs and measurements. Accept a valid findings report even if the process signals a severity threshold. Missing or invalid output makes the tool unavailable. Render JSON in the existing panel. If the spike slips, ship native DRC/ERC and leave the optional checks marked unavailable. [pcb-inspector manual and rule catalog](https://github.com/takzen/pcb-inspector/blob/main/MANUAL.md)

### Pass gate

- Run the native KiCad tools on the pilot machine. A controlled fixture detects a known DRC issue, a known ERC issue, and a deliberate board-to-schematic mismatch with the relevant file and object evidence. A known clean counterpart has no finding for those specific rules.
- Show the expected footprint move and pad change. A routing-only fixture with a seeded violation produces a DRC finding even when the footprint/pad comparison is empty. For one inherited finding, verify that it is not labeled new. Findings are compared using rule ID, scope, and stable object IDs where available. Use **present at head** when a reliable match cannot be made.
- Test a missing child sheet, missing CLI, timeout, and invalid JSON. Each yields an explicit coverage failure or unverified result. Verify the snapshot excludes symlinks and paths outside its root, and is removed after the tool completes or fails.
- Record the pcb-inspector version or commit, the rule outputs verified, and whether it passed its spike. If it fails, report **optional heuristics deferred**. The native checks, parity, and evidence requirements still apply.

## Phase 3 · Day 3 · CAD, firmware, and BOM checks

Implementation, scope and gate evidence: [Phase 3 report](PHASE-3-WORKSPACE-REPORT.md). STEP/STP is included alongside STL/OBJ under the expanded CAD scope.

| Area | Implementation | Acceptance case |
| --- | --- | --- |
| CAD | Read STL/OBJ blobs with pinned Trimesh from a bounded byte stream, with remote assets disabled. Read STEP/STP with pinned CadQuery/OCP in a fixed, disposable read-only worker; normalize STEP units to mm and preserve assembly placements. Expose the same revision-pinned reader as a typed CAD inspection tool for the future agent. Reuse Atlas's mesh preview. Compare axis-aligned extents in declared units, otherwise display file units. Reuse `kicad_tools.core.board_outline.board_outline_bounds` for `Edge.Cuts` dimensions and require a readable outline before doing fit arithmetic. Add a tiny pilot setting linking a board to an enclosure and declaring cavity dimensions or identifying an explicit cavity export, plus its units and installation orientation. STEP gets measured BREP bounds, solid/face counts, volume summaries, and a coarse 3D preview within display limits. Other CAD formats remain visible with explicit unsupported coverage. [Trimesh loader](https://trimesh.org/trimesh.exchange.load.html) · [KiCad board format](https://dev-docs.kicad.org/en/file-formats/sexpr-pcb/) | A board span of 100 mm exceeds a declared 95 mm cavity along the installed axis. Show **board exceeds cavity width**. A mesh of the exterior alone yields a review suggestion. A board smaller than the cavity bounds gets no fit verdict. |
| Firmware and code | Use the existing numeric pin matcher for C/C++/Arduino, with a Python `ast` adapter if the pilot uses Python. Extract literal assignments and source lines. Reuse Atlas's explicit mapping from firmware symbol to KiCad net and MCU pad. A GPIO number may differ from a package pad number, so require a documented mapping if they differ. Give ordinary code and docs a diff and related-file context. [Python AST](https://docs.python.org/3/library/ast.html) | A configured pin changes from 12 to 13 while the linked hardware net stays on its original pin. Show both sources. A macro expression or missing mapping stays unverified. |
| BOM | Use `csv.DictReader` with the pilot's column names and delimiter. Preserve part numbers as strings, expand supported grouped reference designators, and compare by reference. Check quantities and compare references with the designated schematic assembly. Track DNP or excluded parts explicitly when that information is available. [Python CSV](https://docs.python.org/3/library/csv.html) | Show a changed part number and a BOM reference absent from the designated schematic. A DNP item or ambiguous grouped reference must not be called a missing part. |

### Pass gate

- **CAD:** Reproduce the 100 mm versus 95 mm cavity example with evidence for each dimension and the installed axis. Verify that an exterior mesh, missing units, or an unreadable outline cannot produce a measured fit verdict. A narrower board receives only the outcome of the dimension check, with full fit still unverified.
- **Firmware:** Detect the mapped numeric pin mismatch and show the source line and hardware net. Matching values produce no mismatch. An unresolved expression, ambiguous mapping, or missing netlist is unverified. Source files are read without executing project code.
- **BOM:** Detect a changed part number, a quantity change, and an unknown reference in the controlled BOM. Quoted fields and part numbers with leading zeros survive parsing. DNP entries and ambiguous references never produce a false missing-component finding.
- **Whole workspace:** Each area has at least one supported before/after example in the fixture. Every path remains visible even if its format or file size limits analysis. The real pilot report lists exactly which checks ran and which inputs are still missing.

## Phase 4 · Day 4 · Relationships and one AI explanation

Implementation and evidence: [Phase 4 report](PHASE-4-AUDIT-REVIEW.md). The
Connections tab, scoped source links, ESP32 declaration support and bounded AI
review are implemented. Local gates and a real-provider synthetic-fixture check
passed; live project submission remains an explicit UI action.

1. Derive confirmed links from exact matches within the selected project: schematic reference/pin to PCB reference/pad, BOM reference to schematic component, and configured firmware symbol to its documented hardware pin. Label declared board-to-enclosure pairs as configured. Use possible links for things such as an enclosure opening to review after a connector moves.
2. Build `POST /audits/{id}/explain` around the existing model client. Pass the saved report plus a bounded set of evidence snippets. Treat repository text as data. Allow only evidence IDs from that audit in the returned structured summary. Show **what changed**, **what else to review**, and **what could not be checked**. Link each claim to its evidence. Keep model credentials and GitHub tokens separate. Make clear that clicking the button sends selected evidence to the configured model provider.
3. Keep the report usable with the model disabled or unavailable. The AI may explain a board-to-enclosure review suggestion. A finding can only get a verified status from the check that produced its evidence.

### Pass gate

- An electrical finding opens both exact files at their cited commits. A BOM reference links to the correct schematic assembly, even when another assembly uses the same reference. A connector move opens the configured CAD file and displays a suggestion unless a measurement supports a stronger claim.
- Use a test response that cites an unknown evidence ID and one that tries to invent a verified fault. Both are rejected. A repo file containing instructions cannot grant the model tool access or change a deterministic result. Limit the explanation to one explicit request per click with a timeout and bounded input size.
- Verify one real explanation on approved pilot data. With the provider disabled or timed out, the workspace still shows all deterministic findings and their evidence. The explanation control reports its own failure separately.

## Phase 5 · Day 5 · Pilot and fixes

- Replay a known change across the real repo. Confirm the same commit pair produces the same deterministic results after restart. Check a bad import, missing KiCad CLI, missing sheet, unsupported CAD units, and an unavailable model. Each state should have a clear message.
- Give two or three builders one task on their own repo. Ask them to import it, open a commit they know, and use the report to tell a teammate what to check. Record time to first useful finding, misleading alerts, and whether they return after the next push.
- Use manual sync and assisted setup for this pilot. Put the week into improving evidence and removing friction in the one workspace. Hosted sync, team accounts, notification delivery, and broader format support can follow the pilot.

### Release gate

- Run one end-to-end review on the pilot repo after a fresh app start. Import, select the known pair, open a finding, follow its evidence into another project area, and then sync and review a second change. Record the real tool versions, the observed results, and which file types were audited versus shown as changes only.
- Proposed pilot targets on the chosen machine: open a cached workspace within **2 seconds**, finish a typical audit within **60 seconds** or clearly report a timeout, and get a tester to their first useful finding within **5 minutes** after access is configured. Measure and report any miss. If the repo or machine makes a target unrealistic, agree on a revised target before judging the run.
- At least **two builders** independently complete the import-to-finding workflow with their own project material after access setup. At least one can name a specific follow-up they would take from the evidence. Record whether they return for a later change as a pilot signal.
- A wrong commit, a false verified finding, or a failed import with no way forward blocks pilot release. A later feature can be marked as deferred only when this plan labels it optional. The phase report names the blocker and the smallest next fix.
