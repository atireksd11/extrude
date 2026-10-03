# Learnings

Things that showed up while building and were not in the phase plan. Append only.

## Template

- Date:
- Phase:
- What showed up that was not planned:
- Does a later phase change? yes / no
- If yes, what changes:

## 2026-10-03

- Phase: 0
- What showed up that was not planned: The import drill works. Adding `import extrude.learn` inside `extrude/harness/api.py` failed `test_user_path_imports_stay_inside_the_rules`. Reverting that line made all 6 Phase 0 tests pass. The broken import was not committed.
- Does a later phase change? no

## 2026-10-03

- Phase: 0
- What showed up that was not planned: The skeleton was signed off after about 15 minutes. That broke the rule that a run under 90 minutes is not signed off. The sign-off was removed. The rooms, the tests, and one import drill are real. The job cards are thin, and the map boxes were ticked by the writer, not by a separate reading.
- Does a later phase change? no
- If yes, what changes:

## 2026-10-03

- Phase: 1
- What showed up that was not planned: “output 3.3 V from input 5 V” was first called ambiguous, because the look-back window for the 5 V still contained the earlier word “output”. The nearest word now wins, so input stays input.
- Does a later phase change? no

## 2026-10-03

- Phase: 1
- What showed up that was not planned: A second pass found three wrong cards. “Power an ESP32 from 5 V to 3.3 V at 2 A” was treated as an MCU swap. “I want to use 5 V to 3.3 V at 2 A” was called ambiguous because the word “to” earlier in the sentence marked the first voltage as the output. A hold-up sentence that already named 4.7 V, 20 ms, and 545 µF still asked for those facts. Those three are fixed.
- Does a later phase change? no

## 2026-10-03

- Phase: 2
- What showed up that was not planned: A capacitor between VSS and GND looks connected and is not a DC path, so the power pin still fails until the design says those names are the same net. A bead followed by a bulk capacitor does not fail; it only warns that the capacitor is not on the pin's own net.
- Does a later phase change? no

## 2026-10-03

- Phase: 2
- What showed up that was not planned: A second pass found three misses. A capacitor on 3.3 V was treated as covering the 5 V pin, because the check walked through ground into the other rail. Two ideal sources on 5 V were ignored when their pins were not labeled plus. A tie that named GND only in the tie list, with every pin on VSS, did not count as ground. Those three are fixed.
- Does a later phase change? no

## 2026-10-03

- Phase: 3
- What showed up that was not planned: The retest did not find a wrong number. A negative bias uses the same curve as a positive one. A curve name that is not in the repo falls back to the generic screen and only warns. A buck is not given an LDO temperature, and equal input and output do not produce a ripple.
- Does a later phase change? no

## 2026-10-03

- Phase: 3
- What showed up that was not planned: A later pass found five wrong numbers. A ceramic at 0 V was cut in half. A tolerance of 20, meaning percent, became a negative capacitance. A space after X7R skipped the curve. A generic 100 µF part hid a vendor part that was actually short. An input capacitor was added into the buck ripple. Those five are fixed.
- Does a later phase change? no

## 2026-10-03

- Phase: 4
- What showed up that was not planned: ngspice prints a measurement as `v_hold = 2.16e-62 at= 3.5e-03`, with text after the number. The first parser required the number to end the line, so a real run was called a tool failure. The parser now keeps the number and ignores the `at=` note. The console program is `ngspice_con.exe`, found only through `NGSPICE_PATH` or PATH.
- Does a later phase change? no

## 2026-10-03

- Phase: 4
- What showed up that was not planned: A negative capacitance was still sent to ngspice, and a part named Bank was written as a device that is not a capacitor. Zero or negative capacitance is now refused before a process starts. The device name is forced to start with C, and the original name stays in the comment.
- Does a later phase change? no

## 2026-10-03

- Phase: 5
- What showed up that was not planned: The follow-up pass did not find a miss filed in the wrong notebook. A 12 V block starts again at 10.8 V, which is 90 percent of the failed voltage, and not at 10.79 V. An over-current block does not fire from a voltage alone.
- Does a later phase change? no

## 2026-10-03

- Phase: 5
- What showed up that was not planned: A later pass found two wide bans. An unknown tape suffix still blocked the base part when that part was attached beside the suffix. A failure stored at 0 V blocked 3.3 V and 12 V. An unknown orderable name now blocks nothing, and a voltage of 0 does not count as a stress level.
- Does a later phase change? no
