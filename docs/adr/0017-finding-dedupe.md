# 0017. Deduplicate findings across schematic roots

## Context

Electrical reasoning analyzes each root schematic independently. Roots that
share a child sheet or carry the same defect in successive board revisions
can emit multiple copies of a single finding. The finding count then
overstates how many defects a builder needs to address.

## Decision

Deduplicate the final list returned by electrical reasoning. Require every
source to have a non-empty locator. Match the rule, summary, severity,
status, domain, lifecycle, before and after values, related files, sorted
locators, and sorted revision-normalized paths. Keep the first finding in
place and union original evidence in first-seen order by evidence identity.
At this stage, path and locator identify evidence within the single repository
and commit. The collector materializes the IDs downstream.

Normalize each slash-delimited segment's stem with the curated
`REVISION_SUFFIX_RE` and preserve its extension. The v3 Python reproduction
showed that `_Rev[A-Za-z0-9]*` could not consume the underscore in
`_Rev_M`, `_Rev_M1`, and `_Rev_M2`. V4 changes that character class to
`_Rev[_A-Za-z0-9]*`. All three filenames now normalize to the same stem.
The other alternatives and stem splitting follow v3. Paths such as
`left/board.kicad_sch` and `right/board.kicad_sch` remain distinct.

## Consequences

Finding order and verdict fields stay stable, and each distinct source path
remains available in evidence. The pass adds no coverage entries. A
repository that names distinct physical boards with revision-like suffixes
can still collide if the rest of the key matches. The pinned-repository
mechanism check gates changes to this heuristic.

Reverting the pass restores the original per-root findings.
