# Milestones

Each week ends when its exit test passes, not when the files exist. A failed exit test stays the current week.

```mermaid
flowchart LR
  w12[Weeks 1 to 2]
  w34[Weeks 3 to 4]
  w56[Weeks 5 to 6]
  w78[Weeks 7 to 8]
  w12 --> w34 --> w56 --> w78
```

## Weeks 1–2 — Practice ceiling

Work:

- Replay Luna and Sol, harness off and on, on the existing eight. No new API spend beyond those four passes if logs are fresh and the code has not changed.
- Add cousin sentences only in families `walk` already runs.
- Fix any regression in pin hoisting, ground aliases, or coverage stamps before adding board work.
- Write the slice-pack task list on paper in `eval/proxy_tasks/motherboard_slice/PACK.md`: six tasks, limits, and the model-off risk for each.

Exit test: practice harness-on Luna still at or above 80% on the eight, harness-off at or under 45%, LED still a question when the supply is absent. Full unit suite green.

## Weeks 3–4 — KiCad grade and pin tables

Work:

- Install KiCad. Wire `KICAD_CLI_PATH`.
- Emitter writes one `.kicad_pcb` for a 9-pad power slice: U1, input capacitor, output capacitor, bleed resistor, nets `VIN`, `VOUT`, `GND`, outline 25 mm by 18 mm, edge keepout 1 mm, part gap 2 mm.
- Parser reads DRC JSON. Unit tests use saved reports in `tests/fixtures/drc/`, including a clean report and a clearance report. No model call.
- Three parts get `extrude/parts/<mpn>.json` from their datasheets: the regulator used on the slice, one 10 µF capacitor, one resistor. Pin checker fails unknown pins.

Exit test: a planted short and a planted pin error fail in unit tests. A hand-built clean board returns exit 0 from the real CLI on this machine.

## Weeks 5–6 — Slice pack and power rail

Work:

- Six frozen tasks on disk, with reference BOMs.
- Decoupling check: each power pin named in the datasheet JSON has a capacitor on that net. Distance limit is a number stored on the task, checked from pad coordinates in the board file.
- Existing derating and ripple stay on the regulator stage. They are not replaced by a generic half-capacitance guess.
- Harness-off run of the six, Luna only, one run. Record the misses. Do not change the model prompt to hide a rule that the checker enforces.

Exit test: all six tasks run to a real status (`checked`, `stopped`, or `needs_info`). None crash. Results file written.

## Weeks 7–8 — Measured 80% attempt

Work:

- Luna two runs, Sol two runs, off and on.
- For each harness-on miss, add the checker’s `MUST_FIX` text if the payload was vague. Do not loosen the limit.
- If a task is passed by both models with the harness off, mark it easy in the report and replace it with a harder sibling before the second run. The replacement is logged.
- Publish `eval/proxy_tasks/results-motherboard-slice.json` and a one-page reading note in `project_blueprint/results/week-08.md` stating the four averages.

Exit test: the week-8 contract in [02-eight-week-contract.md](02-eight-week-contract.md). If Luna harness-on is under 80%, the note names the failing checker ids and weeks 9–10 keep those tasks.

## Weeks 9–10 — Only if the slice score is short

Same pack. Same models. Changes allowed: richer failure text, a missing datasheet field, a board-file bug in emit. Changes forbidden: dropping a task, raising a clearance, skipping DRC.

Exit test: a new results file, `results-motherboard-slice-r2.json`, and the practice eight replayed once so the small-circuit score did not fall.
