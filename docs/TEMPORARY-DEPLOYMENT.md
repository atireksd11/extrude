# Temporary public pilot: deployment audit

This configuration is for an invited-friends experiment with disposable public
repositories. It does not turn the local pilot into a secure multi-user service.
No application code changes, account creation, deployment, payment or merge are
part of this PR.

## Runtime requirements and blockers

- Python metadata requires >=3.11. The container selects Python 3.12 on Debian
  trixie for native wheel compatibility, rather than the previous floating 3.13
  slim base. `pip install .` installs the exact direct pins in `pyproject.toml`,
  including FastAPI/Uvicorn, Pydantic, HTTPX, kicad-tools, Trimesh, CadQuery/OCP.
  Transitive dependencies and Debian patch versions are not locked.
- The existing Dockerfile only installed Git and CA certificates. This one also
  installs KiCad and its stock symbol/footprint libraries plus GL/GLib libraries
  needed by native CAD dependencies. `kicad-tools` from pip is not `kicad-cli`.
  The app accepts CLI majors 9 and 10; trixie supplies major 9. The README's
  previous native validation used 10.0.6, so newer-format files can remain
  unverified on 9. Inspect actual image versions before testing a project.
- Git and outbound HTTPS to github.com are needed for imports and sync. Public
  repos need no token. Private repos require `EXTRUDE_GITHUB_TOKEN`, but do NOT
  configure one on this unauthenticated public pilot: everyone shares imported
  files/history and the server's access. This is not per-user GitHub OAuth.
- KiCad CLI checks are headless. xvfb is not required for these checks. OpenSCAD
  and ngspice belong to the older generation/simulation features; they are not
  installed in this minimal workspace image. Those features remain unavailable
  or report coverage gaps. To exercise them later, install their OS packages;
  OpenSCAD graphical rendering may additionally need Xvfb/Mesa and a wrapper
  selected with `OPENSCAD_PATH`. Installing Xvfb alone does not change the app's
  subprocess invocation. `NGSPICE_PATH` and `KICAD_CLI_PATH` override discovery.
- `EXTRUDE_DATA_DIR=/app/data` must be writable. It holds bare Git clones,
  settings, audit reports, snapshots, CAD caches, demo projects and generated
  artifacts. Project-map SQLite defaults below it; `EXTRUDE_PROJECT_DB` can
  override that. Optional legacy memory/telemetry uses `EXTRUDE_MEMORY_DB`.
  Temporary native check files also need writable temporary disk. No external
  database or object store is required for disposable testing.
- Uvicorn serves both UI and API on `0.0.0.0:8000`, one process. Render config
  sets `PORT=8000`; no CORS setup or separate frontend is needed. Health check
  `/v1/status` verifies HTTP startup/tool discovery, not a successful CAD audit.
  Start friends at `/projects/github` (or `/projects` for the demo). Paths entered
  for local projects refer to the server, not a friend's computer.
- **Public-use blocker:** no login, tenant separation or comprehensive request
  quotas. All visitors can see/change shared pilot state and consume CPU/disk.
  Native parsers are not an OS sandbox. Run only trusted, small public test
  projects, keep secrets/private files out, stop the service after testing.
  Authentication, stronger isolation and abuse controls are needed before
  confidential or unrestricted public use; they are outside this minimal PR.
- No secret is required to boot/import public repos/run deterministic checks.
  Leave `EXTRUDE_MODEL_KEY`, `OPENAI_API_KEY`, `EXTRUDE_ESCALATION_KEY` unset.
  AI review/generation will not work without provider credentials and may cost
  money if enabled. Optional provider settings are `EXTRUDE_MODEL_URL` and
  `EXTRUDE_MODEL`. `EXTRUDE_LOAD_ENV=0` prevents loading a bundled `.env`.
  The legacy `EXTRUDE_SPEND_CAP_USD` is not a global public-service billing guard.

## Hosting fit

[GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages)
is static hosting: it cannot run FastAPI, Git fetch, SQLite or native tools.
Serving only the HTML/JS leaves its API calls broken.
Vercel is not static-only: it also supports Python functions. However its
[function limits](https://vercel.com/docs/functions/limitations) and execution
model do not provide this Dockerfile's persistent process, shared local state,
OS packages or durable background audit lifecycle. This app cannot be moved
there unchanged. A container host runs Uvicorn and the required native binaries.

## One recommendation: Render Free web service

Verified against official documentation on 2026-11-08. Use a $0 Hobby workspace
and explicitly choose **Free** compute; the Blueprint specifies `plan: free`.
This is a limited pilot recommendation, not a promise that large CAD fits.

| Resource | Current limit / implication |
| --- | --- |
| Runtime | 0.1 CPU, 512 MB RAM, single instance; CAD workers/large audits can OOM or time out. Test one small project at a time. |
| Idle | Sleeps after 15 minutes; next request takes about a minute to wake. |
| Hours | 750 running instance-hours per workspace/calendar month; exhausted hours suspend free services until reset. |
| Storage | Ephemeral; all runtime data disappears on sleep, restart or redeploy. No free persistent disk. The cited free-service docs do not promise a runtime disk capacity; do not treat it as durable or unlimited. |
| Builds | Hobby includes 500 Starter pipeline minutes/month. Build machine: 2 CPU, 8 GB RAM; 16 GB build disk limit; 120-minute timeout. Native dependencies make first builds large. Actual duration depends on network/cache. |
| Egress | Hobby includes 5 GB/month shared across workspace services. |
| URL | Supplied HTTPS `*.onrender.com`; Hobby includes two custom domains with managed TLS, but owning a domain is separate. Use the supplied URL for $0. |
| Cost guard | Do not add a payment method, paid compute, disk or paid add-on. Without a payment method, exceeded bandwidth suspends services; exhausted build allowance blocks builds. With payment details, overages can be billed. |

Sources: [free service lifecycle/quotas](https://render.com/docs/free),
[compute plans](https://render.com/docs/compute-plans),
[build resources and limits](https://render.com/docs/build-pipeline),
[bandwidth](https://render.com/docs/outbound-bandwidth),
[custom domains](https://render.com/docs/custom-domains).

## Local container verification (does not publish)

```sh
docker build -t extrude-pilot .
docker run --rm -p 127.0.0.1:8000:8000 --memory=512m --cpus=0.1 \
  -e EXTRUDE_LOAD_ENV=0 extrude-pilot
# In another terminal:
curl http://127.0.0.1:8000/v1/status
```

The container runs as UID 1000 with a writable `/app/data`; no host files,
credentials or Docker socket should be mounted into a public instance.
For local persistence only, a named volume can be mounted at `/app/data`.

## User actions still required (only when you decide to publish)

1. Review this draft; no merge is needed to test its branch. Create/sign in to
   your own Render account, choose a free Hobby workspace without a payment
   method. If account verification demands payment, stop rather than pay.
2. Connect **only** `atireksd11/extrude` and select this PR's branch
   `draft/temporary-public-container`, not `main` until it contains these files.
   Create a Blueprint using `render.yaml`, or manually create a Docker Web
   Service with the same values. Creating the service/Blueprint can trigger
   its first live deployment: do this only when you intend to publish.
3. Confirm Free compute, Dockerfile at repo root, port 8000, health check
   `/v1/status`, writable data directory and `EXTRUDE_LOAD_ENV=0`. Auto-deploys
   are off in the Blueprint; this does not prevent its initial deployment.
   Do not provision a database/disk, enable paid previews, or add model/private
   GitHub credentials. No secrets are needed for the recommended test.
4. Once you personally deploy, visit `/v1/status`, `/projects/github` and
   `/projects`; import a small trusted public repo and confirm findings and
   coverage gaps. Check memory/logs before inviting friends. If 512 MB is
   insufficient, stop the $0 experiment instead of upgrading automatically.
5. Share the supplied HTTPS URL with friends. Explain that state is shared
   and disposable. Save needed findings before idle/restart; delete the service
   when finished. Durable storage or confidential testing needs further work.

## Validation in this environment

- A clean Docker image build succeeded with Python 3.12, KiCad 9.0.2 and the
  pinned Python dependencies (about three minutes here; not a host build SLA).
- Existing offline stabilization tests: 5 passed, including installed UI/API
  routes and demo creation/change. Existing Node workspace UI checks passed.
  Blueprint values and `git diff --check` passed.
- A separate `docker run` smoke attempt could not start: this environment's
  8 GB filesystem and Docker VFS driver ran out of disk duplicating the large
  image. An in-build smoke retry also exhausted the remaining disk. Thus the
  container's runtime, native CAD checks and behavior under Render's 512 MB /
  0.1 CPU limits remain unverified. The offline tests above ran in the local
  Python environment, not the built image. No public host was contacted to
  create a service or deploy. Test the image and a small project before sharing.
