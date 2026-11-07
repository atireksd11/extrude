# Extrude operating system v1

Start in Muse. Linear tracks the work, Codex Cloud builds it, and GitHub holds the code and draft pull requests.

- [Extrude project](https://linear.app/plmp/project/extrude-8799dc9dae00) belongs to team `EXTRUDE`. Choose one **Issue type** label: **Dev**, **Testing**, or **Business / Research**. **Testing** also serves as the testing label. Use `muse`, `codex`, and `business` as appropriate.
- The six future-tool ideas are [EXTRUDE-5 through EXTRUDE-10](https://linear.app/plmp/project/extrude-8799dc9dae00) in Backlog with `future-tool`. Leave them there until Atirek explicitly selects one for development.
- Use the published `extrude` Codex Cloud environment for [`atireksd11/extrude`](https://github.com/atireksd11/extrude) on `main`. Extrude uses Python. Install with `python -m pip install '.[dev]'` when needed and choose checks appropriate to the task.

## Run a task

1. Tell Muse the goal. Have it create or reuse one issue in the **Extrude** project and one matching GitHub issue. Cross-link them and record the goal, allowed files, and acceptance test.
2. Have Muse use its cloud browser to start Codex in the published `extrude` environment. Codex makes the change on a branch, runs the requested checks, and opens a draft PR against `main`.
3. Have Muse review the diff and add the PR link, check results, and any blockers to the same Linear issue. If Muse is still waiting after Codex finishes, ask it to review the draft and record the result.
4. Atirek decides whether to merge. Keep automated work on branches and send changes to `main` through pull requests.

## Verified run

The README-only acceptance test used [Linear EXTRUDE-12](https://linear.app/plmp/issue/EXTRUDE-12/verify-the-readme-handoff), [GitHub issue #2](https://github.com/atireksd11/extrude/issues/2), and [draft PR #3](https://github.com/atireksd11/extrude/pull/3). Codex changed only `README.md` and `git diff --check` exited 0 with no output. Muse recorded its diff review and the check result in Linear. The draft stayed unmerged.

The separate owner-only `/codex` GitHub Actions workflow is proposed in [draft PR #1](https://github.com/atireksd11/extrude/pull/1). Its intake checks passed, but model execution is disabled and would require a separately configured OpenAI API key. The verified v1 route uses Muse's cloud browser and the existing Codex Cloud environment.
