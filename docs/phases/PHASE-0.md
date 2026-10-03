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

- [ ] Install succeeds with no KiCad and no ngspice
- [ ] `pytest tests/phase0` passes
- [ ] The tree test fails if a drawer or a required doc is missing
- [ ] Every job card names who it may talk to and who it must not talk to
- [ ] Import scan uses the syntax tree, including aliases and submodules
- [ ] Each job-card signature matches the function in code
- [ ] Every public entry raises “not built”
- [ ] No file reports a hard-coded pass

Human:

- [ ] Using only `docs/MAP.md`: sentence lands in intake, a banned part would be stored in memory, the simulator would run in sim, offline learning sits in learn
- [ ] Deliberate break: `harness` imported `learn`, the test failed, the import was reverted, the test passed
- [ ] Clock recorded below. A hollow run under 90 minutes is not signed off

Sign-off is both lists. Green tests with an empty checklist do not count.

## Clock

- Started:
- Drill finished:
- Signed off: no
