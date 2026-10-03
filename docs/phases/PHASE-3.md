# Phase 3 — One shared physical number

`physics.derive` computes the numbers later checks must share. Still no model.

## Build

- For Class II ceramics, one use-value from nominal capacitance, DC voltage, and tolerance
- That same use-value is what a later deck and the ripple math must read
- A vendor curve, or the same maker and same series, case, voltage rating, and dielectric, may fail a minimum-capacitance check
- A generic “loses about half” curve may warn only
- Film, C0G, and electrolytics do not use the ceramic curve
- Buck ripple uses the continuous-conduction formula and the shared use-value. If the inductor current hits zero, ripple is not covered
- Heat is a still-air estimate, labeled as an estimate

## Checkpoint

- The hold-up example uses a curve marked as that example. A generic half-loss formula must not hard-fail it
- A 25 V part at 5 V must not be failed by the generic formula
- Two callers asking for the capacitance of the same part get the same number
- A light-load buck that leaves continuous conduction does not emit a fake ripple

Stop when those cases pass. Curves used here are files in the repo, not a live download.

## Checkpoint

Passed 2026-10-03, then retested. `tests/phase0` through `tests/phase3` are green.

- The 22 µF hold-up example at 4.7 V comes from `strategy_holdup_22u_4v7`. Effective capacitance is 11.4 µF. With 20% tolerance the use-value is lower, and that vendor curve may fail a minimum.
- The same numbers through the generic half-loss screen only warn. A 25 V X7R at 5 V is not failed by that screen.
- Two calls return the same result. A light-load buck leaves ripple empty instead of inventing a continuous-conduction number. A heavy-load ripple is computed from the use-value, not the nominal value.
- C0G, film, and electrolytic keep their nominal capacitance. A missing curve name falls back to a warning. A buck is not given a linear-regulator temperature. Equal input and output do not produce a fake ripple.
- Heat, when it is an LDO, is labeled a still-air estimate.
- A ceramic at zero volts keeps its nominal value. A tolerance written as 20 instead of 0.2 does not become a negative capacitance. A generic part cannot fill a hole left by a real curve. Buck ripple uses the output capacitor, not an input capacitor on another voltage.
