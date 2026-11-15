# ADR 0007: Isolate electrical input failures; retain the 8 MiB cap

Date: 2026-11-15

Status: Proposed (stacked draft on PR #11; memory-gated fallback)

## Context

Deep Test 3 lost the entire electrical layer on three of seven repositories:
webcam and hackrf contained non-UTF-8 firmware comments, and Lily58 contained
an 8,892,279-byte PCB above the 8 MiB limit. These input failures propagated to
the workspace's whole-layer last-resort handler and erased unrelated evidence.

The proposed 32 MiB cap required a measured parse peak below 256 MB. An initial
fresh-process `resource.getrusage` measurement was 309,468 KiB (302.2 MiB).
A clean GNU `/usr/bin/time -v` binary measurement, loading only the repository's
PCB parser and the pinned Lily58 Pro_V2 file, measured **309,448 KiB (302.2 MiB)**.
The parser extracted 312 footprints. Both exceed the gate. The GNU time binary
was extracted from Debian's `time_1.9-0.2_amd64.deb` under the workspace because
this environment does not install `/usr/bin/time`; the measured process did not
import the audit runner, resource, pathlib, or test infrastructure.

## Decision

Take the explicitly authorized fallback: tolerant UTF-8 decoding and per-file
failure isolation, without raising any caps. Decode electrical firmware, BOM,
schematic, PCB, model, library-table, project JSON and mapped netlist text using
`decode("utf-8-sig", errors="replace")`. Replacement retains usable ASCII facts;
per-file coverage discloses the damaged text as not checked rather than claiming
that the substituted text was verified.

Catch blob read/size failures per candidate, schematic/dependency failures per
sheet, hierarchy/analysis failures per root, CSV failures per BOM, and model-scan
failures per file. Continue with other inputs. An input that would exceed the
unchanged total byte budget is skipped, without discarding already accepted
inputs. Preserve the workspace's whole-layer handler exactly as the final guard
for unexpected failures, including repository-wide inventory failures.

Keep the regular-blob, PCB parser, schematic parser, snapshot and electrical graph
limits at **8 MiB**. Keep the **64 MiB total / 256-file** electrical input limits,
firmware/BOM/mesh limits, and graph complexity guards. Bump rule version **7 to 8**
to invalidate caches; findings schema remains **v4**. No new electrical checks or
false-flag corrections are included.

## Consequences

A bad input produces path-specific not-checked coverage while independent designs
still run. Malformed roots may lose their own hierarchy's findings; unsupported
or missing child sheets cannot establish absence-based verdicts. Replaced bytes
are not evidence about the original text. A successful layer can still contain
not-checked coverage; it does not imply a clean design.

**AC3 is unmet:** Lily58 Pro_V2 still exceeds 8 MiB and degrades per file, while
its schematic and the other independent designs can be analyzed. The 10 MiB and
40 MiB regression boards both exercise this retained-cap behavior. Supporting
32 MiB remains deferred because the measured largest test-board parse exceeds
256 MB; this ADR does not claim that the process fits that bound. Caps remain
DoS guards. Streaming/incremental parsing or a separately measured cap decision
would be follow-up work, not part of this fallback.

Regression tests exercise the actual workspace last-resort handler and require
that input defects never reach it. Pinned-repository outcomes and the exact test
baseline failures are recorded in `docs/electrical-robustness.md`.
