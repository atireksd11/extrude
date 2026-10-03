# Ground rules

A phase ends when its checkpoint passes, not when the files exist.

One prompt is not a whole phase. Finish a slice, check it, then commit. Start the next slice only after that.

Unfinished work must refuse to run. It must raise “not built”. It must never report that a design passed.

After each phase, write anything that was built but not planned in `docs/LEARNINGS.md`. If that note changes a later phase, say so before the next phase starts.

Drawers call each other inside one program. That stays fast. The only separate programs are ngspice and, later, KiCad or a parts site. Do not put network calls between drawers.

The learn drawer is not on the path that talks to the user.

Do not turn this into a general context product. The labels are here so a later project could copy one drawer. Do not add extra layers for that.

Commit at the end of each slice, and only after that slice’s check is green. Do not commit a deliberate break. Revert it, rerun the tests, then commit the notes.

## Programs on the machine

Later phases find tools only through environment variables:

- `NGSPICE_PATH` — the ngspice program. If unset, look up `ngspice` on PATH.
- `KICAD_CLI_PATH` — the KiCad command-line tool. If unset, look up `kicad-cli` on PATH.

No drive-letter path is written into the code. Phase 0 must install and pass when both variables are unset and neither program is installed.

## Show-people bar

The work stays private until a frozen set of 8 original practice tasks says otherwise. Three tasks are power jobs this harness knows. Five are other small circuits. The score is `0.65 × technical + 0.35 × cost`, and cost counts only when the circuit works.

- Luna, with the harness on, averages at least 40% on two full runs.
- Astra, with the harness on, averages at least 73% on two full runs.
- If Luna already scores above 45% with the harness off, or Astra above 80% with the harness off, the set is too easy. Harden it. Do not lower the bar.
- This is not an official EEBench score. Do not claim one.
- Missing the bar means stay in the build. Do not drop a hard task to pass.

Nobody outside the build sees a demo before that checklist is signed.
