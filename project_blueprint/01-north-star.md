# North star

A raw model, with this harness wrapped around it, reaches 80% or higher on motherboard designs. The same model without the harness stays near its unassisted baseline. That gap is the product.

## The sentence that counts

“Motherboard design” means a frozen task whose subject is a real board subsystem or a whole board, graded by tools, not by the model’s confidence.

Two scores are kept separate. They are never averaged into one marketing number.

1. **Slice score.** A frozen pack of motherboard subsystem tasks. Each task passes only when pinout, electrical checks, and KiCad DRC all pass. The score uses the same blend already in `extrude/eval/api.py`: `0.65 × technical + 0.35 × cost efficiency`. Cost efficiency counts only when technical is 1.0.
2. **Boot score.** Named boards, named image, named rails. A board that does not boot counts as a miss. This score does not exist until boards have been built and powered.

80% on the slice score is the eight-week target. 80% on the boot score is the same harness after fabrication. Week 8 reports the slice score it actually measured. It does not borrow the boot score.

## What is not the north star

- The current eight-task practice average. That seat is already near 86% harness-on for Luna. It is a regression lock, not a motherboard result.
- An EEBench leaderboard percent. EEBench V1 grades circuit simulation and cost. Its methodology states that layout, manufacturing, and bring-up are outside V1. See [10-sources.md](10-sources.md).
- Layout hours saved by a router that was handed a finished schematic.

## Model policy

The harness is tested on a raw model named in the environment (`EXTRUDE_MODEL`). Default evidence model is Luna (`openai/gpt-6-luna`). Sol (`openai/gpt-6.1-sol`) is the second evidence model. Astra is not required for this program.

Every reported percent includes harness-off and harness-on. If harness-off already clears the pass line, the pack is too easy and the run is discarded. That rule already exists for the practice gate in `extrude/eval/gate.py` (Luna off above 45% throws the set out). The motherboard pack uses the same idea: the off-score must stay below the on-score bar.

## Coverage honesty

A pass notice lists only checks that ran and passed. Unrun domains stay listed as unverified. `extrude/coverage/api.py` already does this for thermal, RF, and mechanical clearance. Motherboard work adds domains to that list only after a checker exists. A domain without a checker is never printed as passed.
