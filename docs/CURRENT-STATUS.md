# Current product status

## What the pilot does

- Imports a GitHub repository into a local Git store, retains commit history, and compares selected revisions.
- Groups all files into one workspace while preserving paths; supports previews, changed-file review, and evidence navigation.
- Compares KiCad footprints, pad assignments, and schematic symbols. When KiCad is available, runs native DRC, ERC, and board/schematic parity on saved revisions.
- Reads STEP/STP with CadQuery/OCP and STL/OBJ with Trimesh, showing dimensions and a coarse interactive preview.
- Reads supported literal firmware pin declarations and CSV/TSV BOMs. Explicit project mappings enable scoped cross-file checks.
- Shows confirmed, configured, and possible relationships with their evidence. Certainty is separate from severity.
- Offers an optional bounded AI review of an existing audit. The user explicitly starts the provider request; returned citations are checked against the saved report.

## Evidence and limits

Local controlled fixtures and the Astra Companion project have exercised PCB removals, STEP preview and measurements, and a BOM cell change. Phase reports record the scope of each check. A synthetic fixture was submitted to a real model provider for the AI review integration; that is not evidence of general engineering accuracy.

The product cannot diagnose every hardware fault or prove a design is safe to fabricate. CAD bounds alone do not prove enclosure fit. Missing cavity dimensions, units, board outlines, or GPIO-to-package-pad mappings remain unverified. Arbitrary code semantics and unsupported CAD formats are not fully audited.

This is a single-machine pilot for known projects. Do not expose the local API publicly. Hosted accounts, automatic GitHub webhooks, cross-repository projects, email/WhatsApp notifications, autonomous repairs, and a general-purpose agent harness are not delivered by this MVP. External native tools need stronger isolation before accepting arbitrary public imports as a hosted service.

## Plan and next gate

The active roadmap is [PILOT-BUILD-PLAN.md](PILOT-BUILD-PLAN.md). Its phase reports describe the implementation and evidence:

1. [Day 1: GitHub workspace](DAY-1-WORKSPACE-REPORT.md).
2. [Phase 2: native KiCad review](PHASE-2-KICAD-REPORT.md).
3. [Phase 3: CAD, firmware, and BOM](PHASE-3-WORKSPACE-REPORT.md).
4. [Phase 4: relationships and AI review](PHASE-4-AUDIT-REVIEW.md).
5. Phase 5 remains open: two builders should independently import their own project, follow a finding to its evidence, identify a useful next action, and return after another change. Measure usability, misleading findings, and performance before expanding scope.

## What is stored in GitHub

Application source, UI assets, tests and controlled fixtures, examples, dependencies, plans, and phase reports. Local Git snapshots, user project data, databases, generated reports, logs, virtual environments, credentials, and local model transcripts are excluded. Fresh clones start with no imported projects; users import their own repositories.

Historical circuit-generation plans and evaluation scripts are retained for reference. They do not replace the current pilot roadmap or establish that the product has passed its user-validation gate.
