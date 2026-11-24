# 0011. Defer the proposed SAM4S regulator tie rule

## Context

The workspace spec “Internal-regulator output tied directly to its load:
VDDOUT → VDDCORE/VDDPLL (Deep Test 3 item 6)” proposes a SAM-only check
scoped by the same-part pin names VDDOUT, VDDCORE and VDDPLL. The pinned
Webcam design has all three pin names on one net.

## Decision

Defer the proposed rule pending a corrected spec. Atmel's SAM4S Schematic
Checklist (AT03463, Figure 1-1 and Table 1-1) requires a direct connection
from VDDOUT to VDDCORE in the single-supply design. The 10 µH inductor in
Figure 1-1 filters VDDPLL from VDDCORE. The SAM4S datasheet (11100K,
§5.4, Figure 5-2) also shows VDDOUT feeding VDDCORE directly.

The proposed pin-name scope can identify candidates for a SAM4S-specific
review. A VDDOUT-to-VDDCORE tie alone would flag the manufacturer's
recommended design. On Webcam, L1 reaches a decoupling branch while
VDDPLL remains on the common rail, so L1 does not provide the depicted
PLL supply filtering.

[Atmel SAM4S Schematic Checklist](https://www.microchip.com/content/dam/mchp/documents/OTH/ApplicationNotes/ApplicationNotes/Atmel-42155-SAM4S-Schematic-Checklist_ApplicationNote_AT03463.pdf)
[Atmel SAM4S Datasheet](https://ww1.microchip.com/downloads/aemDocuments/documents/OTH/ProductDocuments/DataSheets/Atmel-11100-32-bitCortex-M4-Microcontroller-SAM4S_Datasheet.pdf)
