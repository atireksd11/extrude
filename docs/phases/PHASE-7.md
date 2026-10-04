# Phase 7 — The score, then the gate

Write the 8 tasks first, with answers and a reference parts list, before turning the harness on.

## Build

- Eight task files under `eval/proxy_tasks/`
- Score is `0.65 × technical + 0.35 × cost`. Cost counts only when the circuit works
- A results log with model name, harness on or off, per-task score, average, dollars, and seconds
- The result names airflow, radios, and fast memory as not checked
- `learn` stays uncalled between the two gate runs

## Show-people bar

- Luna, harness on, at least 40% on two full runs
- Astra, harness on, at least 73% on two full runs
- If harness-off Luna is already above 45%, or harness-off Astra above 80%, the set is too easy and the attempt does not count

People outside the build see it only after that checklist is signed. A higher score on the three power tasks alone does not sign it.

## Checkpoint

Not signed. 2026-10-03. 110 tests passed, 1 skipped. The skip is the live ngspice check when `NGSPICE_PATH` is unset.

- The eight tasks are in `eval/proxy_tasks/`, each with the sentence, a written answer, a technical check, and a reference cost. The stored card matches what intake freezes from that sentence.
- A failed circuit scores 0 even when its parts list is cheaper than the reference. A working circuit scores `0.65 + 0.35 × cost efficiency`. The gate recomputes that formula, so a log cannot invent a higher average.
- Harness-on and harness-off both appear in the log. Dollars and seconds are on each row.
- The export names heat-in-airflow, radios, and fast memory as not checked, and says this is not an official EEBench score.
- `learn` is not called.
- With no model key, the three power tasks miss as tools and the other five miss as requests. Every score is 0. The checklist stays unsigned.
- A log of only the three power tasks cannot sign. Three perfect power scores and five failures average 37.5%, which is under Luna’s 40% bar.
- No prompt was changed to fit these tasks.
