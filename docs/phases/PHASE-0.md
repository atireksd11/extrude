# Phase 0 — Make the building visible

Phase 0 does not design a circuit, call a model, or run a simulator. It builds the labeled rooms and proves they are real.

## Slices

1. Write the map and the rules. Commit.
2. Create the drawers, doorway types, and job cards. Commit.
3. Make the project installable and add the “not built” entry on each drawer. Commit.
4. Add the checkpoint tests. Commit.
5. Run the human checkpoint and the deliberate-break drill. Commit the checklist and the learnings note only after the break is reverted.

## Checkpoint checklist

Automated:

- [x] Install succeeds with no KiCad and no ngspice
- [x] `pytest tests/phase0` passes
- [x] The tree test fails if a drawer or a required doc is missing
- [x] Every job card names who it may talk to and who it must not talk to
- [x] Import scan uses the syntax tree, including aliases and submodules
- [x] Each job-card signature matches the function in code
- [x] Every public entry raises “not built”
- [x] No file reports a hard-coded pass

Human, from `docs/MAP.md` only:

- [x] A sentence from the user lands in intake
- [x] A banned part would be stored in memory
- [x] The simulator would run in sim
- [x] Offline learning sits in learn
- [x] Deliberate break: `harness` imported `learn`, the import test failed, the import was reverted, and all 6 tests passed
- [x] Clock recorded below

Sign-off is both lists. Green tests with an empty checklist do not count.

## Clock

- Started: 2026-10-03 16:10 (first commit)
- Drill finished: 2026-10-03 16:14
- Elapsed: about 15 minutes of file writing
- Signed off: no

The checks above are real, and the import drill did fail and then pass. The phase is still not signed off. It finished far under the 90-minute floor, the job cards are only a few lines, and the “human” boxes were ticked by the same pass that wrote them. A green test run is not a finished phase.
