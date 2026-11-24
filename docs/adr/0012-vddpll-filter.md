# 0012. Check VDDPLL for a direct tie to the core rail

**Date** November 24, 2026

**Status** Accepted

**Spec** “VDDPLL tied directly to the core rail with no LC filter; L1 misplaced (Deep Test 3 item 6, CORRECTED),” supplied in the cycle 2 task attachment.

This decision supersedes ADR 0011 and the proposed check in PR #29. The SAM4S datasheet (Atmel-11100K, §5.4, Figure 5-2) shows the internal regulator output feeding VDDCORE. AT03463, the SAM4S Schematic Checklist, specifies a direct VDDOUT-to-VDDCORE connection and calls for a decoupling/filtering RLC circuit on VDDPLL. Microchip's kit revision note explains that omitting the LC filter can let supply ripple prevent the 48 MHz PLL from locking and disrupt USB.

For a fitted on-board part with VDDOUT and VDDPLL pins, compare VDDPLL's schematic net with the same part's VDDOUT and VDDCORE nets. A tie produces one warning. An inductor on the tied rail that ends on a net with only fitted C/R/L passives contributes evidence to that warning. A separate VDDPLL net produces a coverage line that leaves filter values unjudged. The check leaves the direct VDDOUT-to-VDDCORE connection alone.

On the pinned Webcam board, VDDPLL pin 64 shares the core rail and the 10 µH inductor leads to a decoupling branch. The corrected Deep Test 3 item 6 rationale follows the manufacturer guidance and retains the same board, PLL pin, and inductor as evidence.
