# 0013. Footprint pin count versus used pins

**Status** Blocked at the mechanism check on November 24, 2026.

**Spec** “Footprint pin count vs used pins (Linear EXTRUDE-25),” supplied in the cycle 2 task attachment.

The spec requires a fitted, on-board symbol and an exact reference match in its paired PCB. The proposed oversized-footprint check uses a two-pin R/C/L part with a parseable value, at least four numbered pads and at least two numbered pads without a net. The proposed undersized-footprint check compares the symbol pin count after the specified no-connect exclusions with the number of numbered pads.

At Astra revision `0c8afb27`, the collector sees two schematic pins each on R36, R37 and R38. All three references are absent from the paired `astracompanion.kicad_pcb`. The six-pad SOT-23-6 footprints with pads 3–6 unassigned are in `astracompanion copy.kicad_pcb` at the same revision. The earlier footprint-removal evidence is consistent with that distinction.

The spec's stop condition applies. The candidate checks remain unimplemented, and the paired-board selection and thresholds are preserved. Report-mode results on the available corpus also showed that the proposed undersized-footprint count can exceed the pad count when all enumerated symbol pin numbers have matching numbered pads.
