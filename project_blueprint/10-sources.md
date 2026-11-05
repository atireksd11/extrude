# Sources

These are the outside facts the roadmap uses. Each one is narrower than a motherboard boot rate.

## EEBench

- Methodology: [https://eebench.org/methodology.html](https://eebench.org/methodology.html)
- Scope note: [https://eebench.org/blog/can-ai-design-circuit-boards-yet/](https://eebench.org/blog/can-ai-design-circuit-boards-yet/)

V1 grades original circuit tasks with deterministic simulation and design checks at tolerance corners. The published blend is `0.65 × technical + 0.35 × cost efficiency` against a reference bill of materials at quantity-100 prices. Cost counts when the design works. The EEBench site states that layout, manufacturing, and physical bring-up are not in V1.

Extrude’s practice score copies that blend and says so. It is not an EEBench submission. `extrude/eval/api.py` carries `NOT_OFFICIAL` for that reason. Leaderboard percents for any named model are not boot rates and are not this repo’s slice score.

## Quilter

- Project Speedrun: [https://www.quilter.ai/project-speedrun](https://www.quilter.ai/project-speedrun)
- What the upload must already contain: [https://docs.quilter.ai/using-quilter/prepare-your-input-board-file](https://docs.quilter.ai/using-quilter/prepare-your-input-board-file)

Project Speedrun reports 38.5 hours of human cleanup against 428 hours quoted for manual layout of an i.MX 8M Mini module plus baseboard. The schematic was held fixed. The board outline, footprints, and locked mechanical parts were prepared before the router ran. That result is evidence that placement and routing can be automated after the netlist exists. It is not evidence that a raw model produced a booting motherboard from a sentence.

## KiCad CLI

- KiCad 9: [https://docs.kicad.org/9.0/en/cli/cli.html](https://docs.kicad.org/9.0/en/cli/cli.html)

`kicad-cli pcb drc` writes a report. `--format json` selects JSON. `--exit-code-violations` returns 0 when there are no violations and 5 when there are. Other non-zero codes mean the tool or the input failed. Those are tool misses in this harness.

KiCad is not installed in this workspace yet. Week 3 is the install.

## Internal rules that outrank this note

`docs/GROUND-RULES.md` and `docs/MAP.md`. If a blueprint file disagrees with a checker in the repo, the checker is the behavior and the blueprint file gets corrected in the same change.
