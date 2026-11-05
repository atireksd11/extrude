# Data stores

All of this is local. No remote embedding service. No parts-site call on the request path.

## SQLite

Opened only when `EXTRUDE_MEMORY_DB` is set. Implementation: `extrude/memory/db.py`.

| Table | Written when | Read when |
| --- | --- | --- |
| `constraints` | A checker fails a design and the identity is known | `retrieve` before a frozen design, top 3 |
| `telemetry` | Every `/v1/design` call, including needs-info | Offline review, not the prompt |

Constraint identity for dedup: `spec_hash`, `check_id`, `manufacturer`, `capacitance`. A second identical failure does not insert another row.

A constraint may be inserted only when `check_id` is a checker that ran. A sentence the model disliked is not a constraint. A tool crash is a telemetry row, not a ban.

Schema growth in this program, as columns or a sibling table, not a new database:

- `board_rule_id` for a KiCad DRC id.
- `pin_name` and `mpn` for a datasheet miss.
- `measured_mm` and `required_mm` for clearance.

Existing rows stay valid. New columns are nullable.

## Task packs

| Path | Role |
| --- | --- |
| `eval/proxy_tasks/<family>/task.json` | Practice lock. Do not edit limits to lift the average. |
| `eval/cousins/sentences.json` | Wording changes inside known families. |
| `eval/proxy_tasks/motherboard_slice/<id>/task.json` | New pack. Created in week 5. |
| `eval/proxy_tasks/results-*.json` | Evidence. Not inputs to the model. |

Each slice task file contains: id, prompt, task class, limits, reference BOM lines with distributor price and quantity 100, required checker ids, and the datasheet file name.

## Datasheet tables

`project_blueprint/data/` is not the runtime path. Runtime JSON lives at `extrude/parts/<mpn>.json` once week 3 starts. One file per placed part. Fields: `mpn`, `pins` as name to number, `footprint`, `electrical` limits the checker reads, `source` as a datasheet title and table name. If `source` is empty, the part cannot be used on a slice task.

## What learning is allowed to read

Nothing, until [09-learning-rule.md](09-learning-rule.md) says a trajectory is verified. The live path does not import `extrude.learn`.

## Secrets

`EXTRUDE_MODEL_KEY` stays in `.env`. `.env` stays gitignored. Docs and results files never contain the key. Logs that include provider error text are trimmed before they are written into the repo.
