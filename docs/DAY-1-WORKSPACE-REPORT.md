# Day 1 workspace report

Implementation is ready for browser verification. The full Day 1 gate remains pending.

## Built

- The GitHub workspace now uses three panes for the project tree, commit changes and audit findings, and the file inspector. A collapsed history section keeps commit selection on the same screen.
- The tree groups actual paths into PCB, schematic, CAD, firmware, code, BOM, docs, and other files. Inventory and change pages load independently. Removed files open the base version, and renamed files preserve the old and new paths.
- The URL saves the repository and selected commits. Sync preserves an existing review selection and offers a button to open the latest commit. Responses from an earlier selection cannot replace the current view.
- Workspace and audit routes expose the selected commit pair. The audit worker saves a versioned JSON report atomically, reuses duplicate runs, limits concurrent work, and reports interrupted runs as retryable. Parser, Git, rule, and settings versions participate in the cache key.
- The existing PCB adapter produces observations and review suggestions with exact file and commit evidence. A matching schematic filename appears as a suggested related file with its matching basis shown. Unsupported adapters appear in coverage.

## Gate evidence

| Criterion | Status | Evidence and remaining work |
| --- | --- | --- |
| Git revisions, root, rename, deletion, unchanged file, and pagination | Passed in direct backend verification | The controlled robot fixture contains all seven named project areas. The core test verifies both pages, original and renamed paths, and a root baseline against actual Git objects. |
| Duplicate requests and one active audit per repo | Passed in direct backend verification | Concurrent calls reuse one audit ID. A second comparison waits until the first run finishes. |
| Saved report after restart and interruption recovery | Passed in direct backend verification | A fresh Python process reopens the identical saved report. A stored running report without an active worker becomes failed and can be retried. |
| Cache invalidation and individual file failure | Passed in direct backend verification | Changing the parser version or scope limit changes the cache key. A failed PCB adapter leaves the other file coverage available. |
| Revision and preview races in the frontend | Passed in Node DOM simulation | Delayed responses cannot overwrite newer selections. The test also checks deleted, renamed, and unchanged previews and saved audit coverage. |
| Real project input | Passed in direct backend verification | Used the previously imported public janelia-kicad/RP2040_minimal repository. Compared 6ca7ee395e8170a6f9a2c4bc3a01185c87013a5f to 53a58647c9126f1029388eae2c36df2d15e17106. The workspace listed 38 files and 5 changed paths. The saved partial report records that the PCB placement/pad check ran and found zero changes within its scope. |
| Import and review through the browser UI | Pending | Browser control is disabled in Work settings. Layout, actual click flow, and a real browser reload need verification. The DOM simulation does not establish those results. |
| Full FastAPI HTTP integration | Pending | The loopback-enabled test run was not executed. Automatic approval review returned a usage-limit error. Endpoint functions and model schema were checked directly. |

The fixture and direct checks use a simulated offline fetch that transfers real local Git objects. Public GitHub transport was verified in the earlier GitHub slice. The public RP2040 project is a reference input, and the user's pilot project still needs to be chosen for the later domain gates.

## Reproduce

Run the core verification with:

```text
.venv/Scripts/python.exe -m pytest -q tests/test_github_workspace.py -k core --basetemp data/.pytest-day1-core
node tests/ui/github_workspace.test.cjs
```

Run the full Atlas gate on a machine with working loopback:

```text
python -m pytest -q -m atlas --basetemp data/.pytest-atlas
```

With Extrude running, open /projects/github. Import a repo, select a commit, expand a project folder, open a changed file, and run the audit. Open an evidence link and reload the page to verify that the comparison and saved report return.

The pilot worker uses one FastAPI process and keeps audit coordination in memory. It currently audits up to 1,000 changed paths and 12 PCB files, with 200 findings per board. Scope limits appear in coverage. Local folder scanning remains available through its existing page.
