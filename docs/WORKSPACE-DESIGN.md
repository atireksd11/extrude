# Extrude workspace design

The workspace follows a simple path. Pick the project and commit, review changes or findings, then open the evidence in the inspector. The import form is prominent for a first visit and can be reopened from **Add repository** once a project is active.

## Sources reviewed

- [Open Design Agent Kit](https://github.com/feimacode/open-design-agent-kit) and its [Open Design skill](https://github.com/feimacode/open-design-agent-kit/blob/main/packages/claude-plugin/skills/open-design/SKILL.md). Apply a consistent visual system, ground the work in existing UI, and distinguish source inspection from rendered verification.
- [Awesome Claude Design](https://github.com/VoltAgent/awesome-claude-design). Its DESIGN.md approach keeps tokens, component rules, and their reasons together. The developer-tool references informed the compact navigation and restrained surfaces.
- [UI/UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) and its [web review checklist](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/blob/main/.claude/skills/ui-ux-pro-max/references/quick-reference.md). Apply visible focus, labels, keyboard navigation, reduced motion, state feedback, and explicit selected states.
- [Superdesign](https://github.com/superdesigndev/superdesign-skill) and its [existing-interface workflow](https://github.com/superdesigndev/superdesign-skill/blob/main/skills/superdesign/references/SUPERDESIGN.md). Start from the existing product and preserve its workflow while making a coherent change. The implementation uses these design principles locally. Its hosted canvas and account workflow were not used.

## Tokens and reasons

| Token | Value | Use |
| --- | --- | --- |
| Canvas | #f6f7f9 | Quiet background for the review |
| Surface | #ffffff | File, review, and inspector panes |
| Text | #20252b | Primary content and actions |
| Muted | #616a75 | Readable metadata and help |
| Border | #e4e7ec | Pane and row separation |
| Accent | #c64c29 | Primary audit action, active tab, and selected file |
| Navigation | #1d2229 | Stable product navigation |
| Type | DM Sans with Segoe UI/system fallback | Interface text |
| Code type | IBM Plex Mono with monospace fallback | SHAs, dimensions, and source |
| Spacing | 4, 8, 12, 16, 24, 32 px | Consistent grouping and padding |
| Pane radius | 10 px | Main surfaces |
| Control radius | 6 px | Buttons, inputs, and selects |

Fonts use Google Fonts with display=swap. System fallbacks keep the workspace usable if that request is unavailable.

## Interaction rules

- Keep one active review pair and show its SHAs above the panes.
- Present commit history in a disclosure so the workspace remains the main view.
- Changes and Findings are keyboard-operable tabs. Running an audit selects Findings and exposes its progress.
- Selecting a file highlights its row and opens the inspector. Removed and renamed files retain their correct before and after sources.
- Show change letters and words together. Color supports the meaning.
- Show source and related-file links with their establishing evidence. Keep coverage inside Findings.
- On smaller screens, collapse navigation and then stack the panes. At narrow mobile widths, use full-width controls and source panes.

## Verification

The Node UI checks exercise commit and preview races, saved audit coverage, sync preserving the review, tab switching, counts, and import disclosure. Browser access was checked and remains disabled in Work settings. Visual layout and actual browser interaction still require a rendered pass.
