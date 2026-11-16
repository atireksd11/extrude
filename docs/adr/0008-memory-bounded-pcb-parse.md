# ADR 0008: Memory-bounded PCB parsing

Date: 2026-11-16

Status: Accepted for the draft M1 stack; merge blocked pending M3.

## Context

The pinned Lily58 Pro_V2 board is 8,892,279 bytes, exceeding the retained
8 MiB PCB cap. The PR #12 whole-tree parser costs about 302.2 MiB peak RSS,
above the existing 256 MB parse gate. The decision whether to change that gate
remains pending. Raising schematic limits would expose the same full-tree cost.

Before changing production code, a fresh Python 3.12 process reproduced the
baseline at 310,268 KiB (303.0 MiB). Phase peaks were 52,148 KiB after decode,
309,884 KiB after parsing, and 310,268 KiB after Board construction. Separate
tracemalloc profiling confirms the full S-expression tree dominates allocations.

## Decision

Scan the PCB root's immediate children once, respecting strings and escapes.
Reject comments, malformed framing, and top-level forms exceeding 8 MiB. Parse
only version, nets, footprints, and legacy modules with the existing parser.
Retain footprint offsets until all nets are read, then extract one footprint
at a time with unchanged helpers. This preserves net lookup regardless of file
order without retaining trees. Keep the parser lock and restore garbage
collection after every parse, including failure.

Raise MAX_BOARD_BYTES and electrical collect's PCB-only blob limit to 32 MiB.
The per-form implementation measured 57,860 KiB peak RSS on Pro_V2 in a fresh
minimal process, meeting the unchanged 256 MB gate with margin.

Keep schematic, firmware, BOM, mesh, graph, total-byte, and file-count limits
unchanged. Keep snapshot MAX_FILE_BYTES at 8 MiB: it bounds native KiCad tool
materialization, not electrical collect's direct PCB blob reads. Increment
RULE_VERSION to 9; findings schema remains v4.

## Consequences

Peak parse memory is bounded by decoded input, the largest single parsed form,
and extracted output, plus a small offset index. Tracks, zones, and graphics
never become parser trees. The full decoded input is still retained; this is
bounded parsing, not a streaming file reader. A pathological large form is
reported through the existing per-file Not checked path.

The schematic cap remains 8 MiB. Native snapshot materialization can still
exclude a PCB over 8 MiB even when the independent electrical layer reads it.
The memory gate is met as written without changing Render configuration.
No new checks or false-flag fixes are included. This stack remains draft and
merge blocked until the separate M3 assembly correction lands.
