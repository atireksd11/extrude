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
