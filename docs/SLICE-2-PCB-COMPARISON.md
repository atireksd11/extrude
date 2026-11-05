# Slice 2 — PCB comparison

In **Project Atlas → GitHub history**, select a commit and open a changed `.kicad_pcb` file. The **PCB changes** panel compares the exact Git snapshots. Use **Compare with previous sync** to see the cumulative change across a batch of commits.

Atlas compares footprint placement, rotation, side, library, and reference, plus each numbered pad's net assignment. The reader pairs footprints by a unique UUID first, then a unique reference. Numeric net IDs are normalized to names, so a renumbering by KiCad does not create a wiring alert. A previously connected pad that loses its net gets a review label. This label describes a change in the file and does not establish a design-rule violation.

The board reader uses the published MIT-licensed [kicad-tools](https://github.com/rjwalters/kicad-tools) package, pinned to [0.27.0](https://pypi.org/project/kicad-tools/0.27.0/). Its [S-expression parser](https://github.com/rjwalters/kicad-tools/tree/main/src/kicad_tools/sexp) reads the Git blob directly in memory. Extrude extracts and compares the fields it displays, preserving the path and commit on each side. Install or update the workspace dependencies with `python -m pip install '.[dev]'`.

This comparison covers native KiCad board files up to 8 MiB. A malformed, oversized, or unavailable board is marked unverified, with the reason shown in the panel. Routing, board outline, pad geometry, and electrical correctness need separate checks.

## Reuse shortlist for later slices

| Slice | Candidate and decision |
| --- | --- |
| Schematic ingestion | Use [kicad-tools' schematic loader](https://github.com/rjwalters/kicad-tools/blob/main/src/kicad_tools/core/sexp_file.py) and evaluate hierarchical sheets and net resolution before persisting dependencies. |
| Deterministic checks | Use [KiCad CLI](https://docs.kicad.org/master/en/cli/cli.html) for ERC/DRC. Evaluate [pcb-inspector](https://github.com/takzen/pcb-inspector) for additional spatial rules on known good and bad boards. Keep results tied to the revision and rule version. |
| Board inspection | Evaluate [TRACE](https://trace-boardviewer.github.io/) for selection and cross-probing patterns. Verify what can be embedded and under which license before adopting viewer code. |
| Review history | Evaluate the memory patterns in [Neo4j Labs MKG](https://github.com/neo4j-labs/meta-knowledge-graph) and [Letta](https://github.com/letta-ai/letta) when project review history is ready. Preserve human review decisions and deterministic check results as distinct records. |

[KiKit](https://github.com/yaqwsx/KiKit) is a candidate for manufacturing exports and panelization. [pcb-tools](https://github.com/curtacircuitos/pcb-tools) targets Gerber and drill data. Native KiCad comparisons use the board design source.
