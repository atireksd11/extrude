# Eight-week contract

Calendar: eight weeks from the start of execution. Two people are not assumed. One engineer plus the model API is the staffing plan. Spend stays on Luna and Sol. Astra is out of this contract.

## Week 8 must be true

- The practice eight still replay at or above the last signed harness-on averages, harness-off still under the easy line. The LED task stays in the pack when the supply voltage was not typed.
- KiCad is installed. `KICAD_CLI_PATH` is the only path the code uses. `kicad-cli pcb drc --format json --exit-code-violations` grades one real `.kicad_pcb`. Exit 0 is pass. Exit 5 is a design miss. A missing binary is a tool miss and does not consume a design retry.
- Parts on that board have datasheet pin tables in-repo. A net on a pin the table does not list fails the run.
- One power rail on that board has decoupling and the existing ripple and derating checks. A short from power to ground fails closed.
- A frozen **slice pack** exists under `eval/proxy_tasks/motherboard_slice/`. At least six tasks: two pinout, two power, two DRC. Each has a reference BOM priced the way `extrude/eval/bom.py` prices the practice set (quantity 100).
- Luna and Sol each have two full runs, harness off and harness on. The report file is `eval/proxy_tasks/results-motherboard-slice.json`. The printed average is the measured one.
- `extrude/learn/api.py` still raises `NotImplementedError` on the user path. `docs/GROUND-RULES.md` still holds: the learn drawer is not called from a design request.

## Week 8 target number

Harness-on slice score at or above 80% on both runs, for Luna, with harness-off still below that bar.

If the measured score is under 80%, week 8 still ships the report. The following two weeks (the remainder of the two-month window) harden the failing checks. They do not delete tasks, hide rules, or widen tolerances to cross 80%.

## Week 8 must not be claimed

- A motherboard that boots.
- An official EEBench score.
- That more closed-loop retries on the practice eight produced motherboard skill.
- Reinforcement learning, LoRA, or a weight file.

## Two-month close

End of week 8 is the production harness and the first measured slice score. Weeks 9–10, if the slice score is short, are repair weeks on that same pack. The boot test is specified in [08-motherboard-climb.md](08-motherboard-climb.md) and starts only after the slice score is real, because fab and assembly are calendar time the software loop cannot skip.
