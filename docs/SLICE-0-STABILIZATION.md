# Slice 0 — stabilization gate

This gate covers the existing local Project Atlas and Design Studio routes.

## Baseline recorded before this slice

- 286 tests collected. The first full-suite failure was `tests/phase0/test_entries.py::test_no_hard_coded_pass_in_the_package`: Design Studio used literal `passed=True` for a successful parse.
- The prior pytest hooks could load a developer's model key from `.env` and permit an external model request during the offline suite.
- The package omitted UI assets, the tool manifest, physics curves, demo files, and imported `eval` modules. A wheel could therefore install but fail on API import or page delivery.
- The project-map schema was created and altered at connection time without a tracked version.

## Gate

1. Install with `python -m pip install '.[dev]'`.
2. Run `python -m pytest -q --basetemp data/.pytest-local`. Use `-m atlas` for the project workflow or `-m legacy` for the Design Studio and harness. The full legacy suite uses OpenSCAD with working PNG rendering. The default fixture clears model keys and blocks outbound HTTP through the model client and external socket connections. Tests marked `live` require explicit `--run-live`.
3. Boot with `uvicorn extrude.api.server:app --host 127.0.0.1 --port 8000`; verify `/`, `/projects`, `/static/app.js`, `/static/projects.js`, and `/v1/projects` return 200.
4. A clean Docker build uses `docker build -t extrude .` and `docker run --rm -p 127.0.0.1:8000:8000 -v extrude-data:/app/data extrude`. The image runs the installed package and uses a separate volume for local state. This image targets the Atlas workflow and API startup. The optional OpenSCAD and ngspice tools are installed in CI for the legacy tests.

The local SQLite schema is now at `PRAGMA user_version = 2`. A transaction upgrades existing unversioned databases in place and preserves project rows. Project Atlas data and generated designs default to `./data` and can be relocated with `EXTRUDE_DATA_DIR`. `EXTRUDE_PROJECT_DB` still overrides the SQLite path. Design Studio shows an unverified state when a file parses without enough evidence for a design check. Warnings are shown as informational rows and excluded from scores.

## Verification

- Windows offline suite: 290 passed. The ngspice integration test was skipped because ngspice was unavailable.
- Installed wheel: Uvicorn started outside the checkout, served both pages and their assets, and detected the bundled demo's firmware pin change.
- The CI workflow runs both test groups, checks the installed UI, and boots the Docker image. The GitHub Actions run and Docker build are pending.
