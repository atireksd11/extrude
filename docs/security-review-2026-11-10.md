# Extrude security review — 2026-11-10

Review base: `origin/main` at `ce5826d089c3a5c8bf679b0545b24a1f7c2e6dc0`.
New branch: `security/review-2026-11-10`. Draft PR only; no merge or direct main push.
PRs #6, #7 and #8 were not modified. All remote branch refs were fetched read-only
for the history scan; none of their changes were incorporated.

This review does **not** establish that the app is secure. The running Render
service was not changed. In particular, this draft does not protect the existing
service until reviewed and deployed. Live Render access was denied by this
workspace's outbound policy (HTTP 403 / HTTPS CONNECT 403).

## Outcome and deployment impact

Atirek explicitly selected an **interim shared bearer-token gate**. Hosted data
and API routes now require `EXTRUDE_API_TOKEN` with at least 32 bytes. Missing or
short configuration fails closed with 503; absent/wrong authorization gets 401;
repeated requests get 429. There is no default token. Tokens are checked in
constant time. Browser entry stays only in page memory, clears on reload, and
is never attached by the wrapper to another origin. No user-account system,
password database, payment system, cookies or sessions were added.

All token holders still share the same data. This is not tenant isolation. Use
throwaway public projects only. Hosted `/v1/projects` and its descendants, plus
`/v1/design`, `/v1/copilot` and `/v1/compare`, return 403 even with a valid token:
they expose server folders or legacy code/tool execution. Local mode remains a
trusted operator tool, bound to loopback, with optional request budgets.

Before deployment, Atirek must set the token out of band in Render environment
settings, set `EXTRUDE_PUBLIC_ORIGIN` to the real HTTPS origin, and verify which
proxy IPs Uvicorn may trust for forwarded protocol/IP. Do not set a wildcard
proxy trust without confirming that the app is reachable only through trusted
ingress. Incorrect proxy trust can cause redirects or spoofed client identity.
Docker sets hosted mode by default; Render's `RENDER=true` also activates it.

## Checklist, in requested order

### 1. Authentication — fixed interim gate; real authentication still open (critical)

Before this PR every route in the inventory below was public, including reads,
repository imports/syncs, audits, model explanations, settings writes, local
folder registration, finding reviews and pin-rule deletion. Visitors could read
shared repositories/files, write shared settings/audits, consume compute/model
budget and register arbitrary readable server directories. There is no general
file-delete route, but rules can be deleted and demo files changed.

`extrude/api/security.py` gates every `/v1/` and `/artifacts/` route, including
future routes under these prefixes. Static UI assets/pages remain public;
interactive API docs/OpenAPI endpoints are disabled. `static/access.js` provides
interim token entry without storage or URL tokens. `test_interim_bearer_gate_and_unsafe_hosted_features`
proves short token → 503, absent/wrong/query token → 401, correct bearer → 200,
unsafe hosted features → 403, other origin → 403. The browser test proves retry,
reload clearing, no storage/cookies, and no external-origin token attachment.

**Still open:** Atirek must deploy the environment settings; maintainers must add
user identity, ownership checks and separate storage before private or paid work.
Never grant the shared token as if it isolated users.

### 2. Hide API keys — verified, no confirmed leaked credential found

Scanned current tracked source/config/docs/frontend/tests and reachable history
with detect-secrets offline heuristics. Current-tree initial candidates were
fixture specification hashes; historical candidates were Git/specification/
evidence identifiers. No confirmed real secret was found or copied into this PR.
Model and GitHub credentials already come from environment variables in
`extrude/harness/client.py` and `extrude/github_history.py`. New shared access also
uses only an environment variable. `.env` loading is disabled in hosted mode.
A final scan covers added files and the diff. Scanning is heuristic, not proof
that an unknown secret format cannot exist; binaries and unreachable Git objects
are outside the text scan. See item 24 and the scan evidence.

### 3. Lock the database — fixed hosted filesystem exposure and artifact traversal; isolation open

The supplied app description is outdated: `extrude/project_map.py` uses SQLite
at `EXTRUDE_PROJECT_DB` or `data/project-map.sqlite`. `memory/db.py` optionally uses
`EXTRUDE_MEMORY_DB` (constraints, prompts and telemetry). `github_history.py` stores
bare Git repositories under the data directory. Audits/settings, explanations,
CAD caches, generated files and temporary snapshots also live on disk. These
stores are shared, not visitor-owned. No external database integration was found.
Render disk/persistence settings are not in this checkout and were not verified.

`create_project()` formerly accepted any readable server folder. Hosted local
project routes are now disabled. Artifact resolution now confines the target to
the selected run, rather than merely the shared generated directory; the
cross-run `../other/secret.html` regression gets 404. Existing project preview
checks resolved containment, SQLite statements bind user values, and KiCad
snapshot paths reject traversal, symlinks/devices and external dependencies.

**Still open (critical):** no ownership separation between token holders.
**Still open (high):** hard disk quotas and private-file permissions/backup policy
must be designed by maintainers/Atirek before private use. Container UID 10001
reduces OS privileges but does not create tenants or native-tool sandboxing.

### 4. Enforce HTTPS — application behavior verified; Render verification open (medium)

Hosted HTTP redirects with 308 to the configured fixed HTTPS origin, never to an
untrusted Host header; absent/invalid origin configuration fails closed. HTTPS
responses set HSTS. Local HTTP is intentionally available for loopback development.
Scripts/assets use same-origin URLs; external font URLs are HTTPS. Tests cover
redirect and HSTS, and real Uvicorn requests exercised HTTP and trusted forwarded
HTTPS. Render TLS termination and its public HTTP redirect could not be checked:
the environment proxy denied the target. Atirek must verify both URLs and trusted
forwarding on the deployed service; this report makes no claim about Render's
currently returned headers or redirects.

### 5. Hash passwords — not applicable

`rg` inspection of password/auth/session/reset references found no stored user
password or password login flow in `extrude/`. The added high-entropy bearer
secret is operator configuration, not a user-password database. No password
system was added.

### 6. Server-side validation — fixed boundary limits; native parser limits remain open (high)

Added server-side bounds for project names/paths, rule fields, reviews, prompts,
pasted source/filenames and CAD/audit SHA bodies. Existing Git functions require
full commit SHAs and fixed GitHub owner/repository syntax; pagination and settings
already have Pydantic limits. All bodies are capped at 1 MiB **before parsing or
processing**, including chunked bodies with no length header. Invalid lengths →
400; oversized bodies → 413; non-JSON bodies → 415. Validation errors return a
generic 422 without echoing input. Source filenames allow `.scad`, `.net`, `.fs`
only and reject path separators/NUL. Field tests reject a 512,001-character
artifact, executable `.py` and `../part.scad`. No network/tool runs are needed
for these rejections.

**Still open:** not every native parser has an enforced process memory/CPU
boundary. Fuzzing every KiCad/OCP/mesh parser and every nested settings structure
was not performed. Maintain subprocess/container isolation before untrusted use.

### 7. Block XSS — fixed artifact delivery/CSP; rendering verified

Frontend review found user content assigned through `textContent` or text nodes;
existing `innerHTML` assignments in `static/app.js` are constant markup/clears.
Artifacts now download as attachments and carry sandbox/default-src-none CSP,
preventing active HTML/SVG from becoming same-origin application content.
Every response gets a CSP with same-origin scripts, no objects/base/frame parents,
and HTTPS font exceptions. Inline styles remain permitted for existing UI styles;
inline scripts and eval are not permitted.

`node tests/ui/security-browser.cjs` used Chromium with CSP bypassed so escaping
itself was exercised: an image-event/script payload in a repository name stayed
literal text, no injected image node appeared and no script marker executed.
Production CSP was separately observed on real HTTP responses.

### 8. Log suspicious activity — added and verified; operations still open (medium)

`SecurityMiddleware` emits JSON warnings for 4xx/5xx outcomes, including failed
shared access, bad requests, oversized bodies, traversal/404s, forbidden origins,
restricted features and 429s. Records include UTC time, method, matched route
when available (otherwise a fixed category), status, connection IP and a hashed
user-agent. Query strings, authorization, bodies, raw user-agent values and
exception text are omitted. Tests confirm a synthetic marker in URL/header/agent
is absent from the security log. There are no admin access successes to log.

**Still open:** Atirek must configure retention/alerts and protect log storage.
IP attribution depends on trusted ingress configuration. Early rejections use
route categories rather than attacker-controlled URLs. Infrastructure access
logs are outside this middleware; configure them to avoid secret query strings.
No load-scale log flooding/alert-delivery test was performed.

### 9. Lock admin routes — disabled docs and gated diagnostics, verified

No admin/debug/metrics endpoint implementation was found. `/v1/status` exposes
tool/model configuration and is now behind the same gate. `/docs`, `/redoc` and
`/openapi.json` are disabled; `/admin`, `/debug`, `/metrics` return 404. Tests
request every declared API method/path without access and confirm denial;
explicit sensitive/internal-path requests return 404.

### 10. Parameterized queries — verified; unsafe legacy hosting disabled

SQLite user values use `?` parameters in `project_map.py` and `memory/db.py`;
migration f-strings interpolate static schema names, not request values.
Subprocess calls use argument arrays, not `shell=True`; Git uses validated IDs,
40-character SHAs, literal pathspecs, disabled hooks/credential helpers,
HTTPS-only remote protocol and no redirects. `test_rejects_non_github_sources_and_paths`
rejects local/file/credentialed/lookalike-host inputs and traversal. Snapshot and
artifact path tests reject escapes. The source filename rejection test also
prevents filenames from being treated as paths. A SQL DROP-TABLE payload is
stored as a literal project name while the table remains usable; an OR-1=1 file
lookup does not match a row, and a shell-like repository source is rejected
without creating its marker file.

No SQL or shell evaluator consuming raw request values was found. OpenSCAD is a
language executed by a design tool, so disabling legacy hosted generation is a
boundary restriction, not a claim that tool-language execution is sandboxed.

### 11. Environment variables — fixed safe defaults; deployment settings open

`.env` and `.env.*` are gitignored, `.env.example` has placeholders, and Docker
context exclusions now cover `.env.*` and work files. Hosted execution skips
`.env` loading. Shared access has no default secret and fails closed if missing
or short. Data paths, model credentials/URLs, optional memory DB, GitHub token,
origin and mode are environment settings. Docker defaults to hosted mode.
Static tool/parser bounds and domain rules remain code constants, not secrets.

Tests exercise missing/short tokens and HTTPS-origin configuration. Atirek must
set actual Render values privately; no secret was set remotely by this task.

### 12. Rate limiting — added/verified; distributed quotas still open (high)

Hosted API requests have process-wide rolling budgets of 10 mutations and 120
reads per minute, plus at most two in-flight API requests. Denied access uses a separate ten-attempt budget, so anonymous traffic cannot
spend the authenticated request budget. 429 returns `Retry-After: 60`. Limits are global
rather than based on spoofable forwarded-IP headers; one token/IP cannot bypass
by changing headers. Trusted local mode can opt in with `EXTRUDE_RATE_LIMIT=1`.
Existing audit workers additionally cap queued/running audits (two workers,
four pending); Git operations have timeouts and native tools have existing limits.

Tests prove request 11 is 429, repeated hosted failures are limited, and a third
concurrent request is denied while two requests or slow bodies are held. Invalid
access attempts cannot exhaust the valid-token request budget. **Still open:** these counters
are per process and reset on restart; multiple workers/replicas require a shared
limiter. This is not a hard memory/disk/CPU quota. Maintainers must isolate native
workers and bound Git fetch/storage/cache growth before wider token distribution.

### 13. Restrict CORS — verified

No wildcard/credentialed CORS middleware was found. API requests with a supplied
Origin must exactly match the configured origin (or trusted local host origin).
Cross-site Fetch Metadata is also rejected. Local Host allowlisting blocks DNS
rebinding via arbitrary hostnames. Tests show other-origin, cross-site and
untrusted-Host requests → 403 with no Access-Control-Allow-Origin header.
CORS is not authentication; the bearer gate protects non-browser clients too.

### 14. Security headers — real responses verified

Local Uvicorn returned 200 with `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` and the CSP specified in
`api/security.py`. Trusted forwarded-HTTPS requests additionally returned
`Strict-Transport-Security: max-age=31536000`. Data responses use no-store.
Tests cover success, error and 404 responses. Captures are in
[`security-evidence/2026-11-10/`](security-evidence/2026-11-10/).
Live Render headers remain unverified as described in item 4.

### 15. Secure cookies — not applicable

No `set_cookie`, cookie dependency or SessionMiddleware implementation was found.
Neither the server nor the shared-token browser flow creates a cookie; HTTP and
browser tests confirm no Set-Cookie/cookies. The token is not browser-persisted.

### 16. CSRF protection — cookie-token scheme not applicable; browser boundary hardened

No ambient session/cookie authentication exists. The browser explicitly adds a
bearer header, which a cross-origin form cannot supply. Additionally, state-changing
requests reject other Origins, cross-site Fetch Metadata and non-JSON bodies.
This also closes the former local form/DNS-rebinding attack surface. Requests
without Origin still require hosted authorization; non-browser requests are not
assumed trustworthy from CORS alone. No unnecessary CSRF token system was added.

### 17. Expiring reset links — not applicable

No reset, invite or magic-link flow/routes/storage were found in `extrude/` or the
route inventory. Operator shared-token rotation is an environment update, not a
password-reset flow.

### 18. Upload limits — fixed pasted-source bounds/type checks; hard storage quota open (high)

There is no multipart/file-upload endpoint (`UploadFile`/`File` handlers absent).
The legacy UI submits pasted source in JSON; the API now enforces body/field
size and filename allowlists before processing. Oversized chunked/declared body
→ 413; oversized field or `.py`/traversal filename → 422. Hosted legacy generation
is disabled even for valid shared access. Git imports accept only normalized
GitHub sources, never arbitrary fetch URLs; snapshots already limit selected
files, blob sizes and aggregate materialization bytes.

**Still open:** repository fetches and persistent audit/CAD/generated caches do
not have a hard aggregate disk quota or complete eviction policy. A trusted token
holder can still fill the shared disk via imports/cache growth; a bounded upload
body does not close that risk. Maintainers must enforce filesystem/container
quotas, reserve free space, cap fetched repository bytes and expire caches; Atirek
must verify the actual Render disk allowance. This PR does not claim the 512 MB
host budget is protected against all writes.

### 19. Verify prices — not applicable to billing

No checkout/payment/discount implementation was found. `extrude/eval/bom.py`
contains static distributor reference prices; `cost_usd` is internal model
usage/telemetry and budget accounting, not a client-authoritative purchase price.
No billing was added.

### 20. Debug mode off — verified

FastAPI explicitly uses `debug=False`; Docker launches Uvicorn without reload or
debug options. Unexpected request exceptions return generic JSON 500 without
logging exception contents; request validation returns generic 422. The error
regression deliberately raises a sensitive internal message and confirms it is
absent from the response. Container smoke checks import the app with debug off.
No live Render crash was deliberately triggered.

### 21. Update dependencies — patched/pinned; upstream vulnerabilities remain open

Updated dev pytest 9.0.2 → 9.0.3 for PYSEC-2026-1845 / CVE-2025-71176
(local directory privilege/DoS risk). `pip-audit` inventoried 70 installed local Python distributions and reported no
known vulnerabilities in 69 third-party distributions after the update; the local
`extrude` package is not on PyPI and was skipped by the advisory service (its
source was reviewed separately).
Direct project dependency versions were already exact pins. Both Docker base
references now pin the scanned SHA256 digest. Runtime OS packages are upgraded
during build, and runtime pip (including vulnerable vendored build libraries) is
removed. The image is built and independently scanned; the local Python audit
does not establish container/OS safety.

The final image scan reports 96 HIGH, 107 MEDIUM, 129 LOW and 25 UNKNOWN
package/advisory records (27 unique HIGH CVEs; no CRITICAL records). No fixed
version is listed for these remaining records. These are scanner findings, not
a reachability or exploitability determination.

The final image scan and every remaining finding, with package/version/severity
and listed fix, are recorded in `container-vulnerabilities.json` beside this
report's evidence. No upstream-fixed version was listed for the remaining
findings at scan time. High/critical IDs and counts are summarized in the evidence
summary; unknown severity is retained as unknown, not downgraded. Maintainers
must track Debian/Python image releases and rebuild/rescan; do not infer that
these are remotely exploitable without a reachability analysis. Full transitive
cross-platform locks and analysis of every native binary remain open (medium).
JavaScript is first-party browser code with no npm runtime dependency manifest.

### 22. Remove unused packages — removed runtime-only excess, verified

`httpx` is used by tests/TestClient, not application runtime source; inspected
installed dependency metadata showed only optional extra requirements from
FastAPI/Starlette/trimesh, none enabled by this project. Moved its exact pin into
the dev extra. Removed runtime pip after install; the container verifies it is
absent. Retained Pydantic/FastAPI (models/routes), Uvicorn (Docker/README launcher),
kicad-tools (schematic/PCB parsers), trimesh (`parse/workspace_mesh.py`), CadQuery
and OCP (`cad_worker.py`). Transitive libraries were not removed based solely on
lack of direct imports: their parent packages require them. No blanket claim is
made that every installed transitive/OS package is essential.

### 23. Exposed files — verified

Sensitive files are not mounted as static roots: only `api/static` is served.
Requests to `/.env`, `/.git/config`, `/pyproject.toml` and
`/data/project-map.sqlite` return 404. Tracked-file inspection found no committed
.env/private-key/database file; `.env.example` is a placeholder. Internal docs
are not served by the application. Arbitrary server-folder registration is
blocked in hosted mode; artifact containment and download sandboxing are tested.
Real private fixtures were not identified by the text scan; binary fixture
contents were not exhaustively forensically inspected.

### 24. Scan Git history — verified within documented scope

Ran `git fetch origin '+refs/heads/*:refs/remotes/origin/*'` read-only and
confirmed `git rev-parse --is-shallow-repository` → false. Scanned all 609 unique
reachable blobs across main and all nine fetched remote branch refs, not merely
main's current tree. Offline detect-secrets identified 119 candidates, all reviewed
as specification hashes, Git SHAs or evidence identifiers. No confirmed credential
was found. [`history-scan.json`](security-evidence/2026-11-10/history-scan.json)
records file, line, introducing/removing commit lookup, blob and disposition;
no candidate values are recorded. Scan execution used detect-secrets 1.5.0 with
normal entropy thresholds/filters and provider verification disabled.

Scope excludes unreachable/deleted server refs, GitHub account/org secrets,
LFS object contents and binary payloads. Git history scanning cannot prove
credentials were never exposed elsewhere. No history was rewritten.

### 25. Revoke leaked keys — not applicable to confirmed findings

No confirmed leaked credential was identified, so no revocation/rotation was
performed or falsely claimed. Atirek alone must inspect provider dashboards if
an independently known leak exists, revoke the old model/GitHub credential there,
replace its hosting secret and inspect usage logs. No live key/account access was
requested in chat. Rotate shared access through environment settings whenever a
holder should lose access; no individual revocation is possible with one token.

### 26. Full security review — findings and boundaries

| Severity | Finding | Status / exact next step |
| --- | --- | --- |
| Critical | Anonymous shared API/files/compute exposure | Interim gate fixed in branch; Atirek must deploy token/settings. Current live service unchanged. |
| Critical | No user identity or tenant ownership | Still open. Maintainers implement identity, ownership checks and separate storage before private/paid work. |
| High | Arbitrary server-directory registration / legacy code generation | Hosted routes disabled even with token. Trusted local feature only; do not re-enable remotely without sandbox/storage boundary. |
| High | Cross-run artifact traversal / active same-origin artifact content | Fixed with per-run containment, attachment and sandbox CSP; regression-tested. No per-user artifact isolation implied. |
| High | Git fetch and persistent cache disk exhaustion | Still open. Maintainers enforce hard storage/repo-byte quotas, reserved free space and eviction before wider token distribution. |
| High | Native KiCad/OCP/mesh worker memory/CPU/filesystem access | Still open. Existing bounds/timeouts and new API concurrency help, but maintainers must isolate workers without application secrets and apply OS resource quotas. Nonroot is not a sandbox. |
| High | Known upstream OS package advisories | Still open; see full severity/package list. Maintainers track fixed releases and rebuild; no fix listed for remaining findings. |
| Medium | Render HTTPS/proxy/header configuration unverified | Still open. Atirek verify ingress trust, real responses and canonical origin after deployment. |
| Medium | Process-local rate budgets, restarts/multiple replicas | Still open. Maintainers add a shared limiter before scaling; keep one server process meanwhile. |
| Medium | Log retention/alerting and log-flood handling | Still open. Atirek configure platform retention/alerts/access logs. |
| Medium | Dependency locking and broad native parser fuzzing | Still open. Maintainers add supported-platform transitive locks and sandboxed fuzz runs. |
| Low | Baseline functional test failures | Still open. Same 24 failures reproduced on main; maintainers repair missing baseline artifacts and native-tool/render coverage independently. |

SSRF checks reject IP/local/file/credentialed/alternate-host sources, and remote
Git is fixed to `https://github.com/{normalized-owner/repo}.git` with redirects
and non-HTTPS protocols disabled. Repositories are bare; they are not checked
out or executed. Native snapshots validate paths/dependencies and scrub tool
environments. No live SSRF probe was sent to private services. Request limits,
JSON validation, same-origin checks, CSP and generic errors are defenses with
explicit tests; they do not replace the open boundaries above.

### 27. Test and report — actual executions

Commands and exact final counts are in
[`verification.txt`](security-evidence/2026-11-10/verification.txt). In particular:

- New security boundary tests cover auth, HTTPS, validation, origins/hosts,
  size/type limits, logging, rate/concurrency, exposed paths, artifact traversal
  and generic errors.
- Targeted existing project/GitHub/copilot tests pass alongside these tests.
- Chromium tests verify the shared-token flow, token clearing/storage/origin
  behavior and XSS escaping; existing Node UI race/evidence tests also pass.
- Full suite failures are compared to a clean detached main worktree. The same
  24 pre-existing failures occur on main (324 pass, 2 skip); final branch counts
  are recorded in verification evidence. No new failure IDs were introduced.
  Missing historical benchmark artifacts and native OpenSCAD/KiCad behavior
  remain unverified by those failing tests; do not call the entire suite green.
- Docker build and real HTTP smoke run use the pinned image, nonroot UID,
  no runtime pip/httpx, correct bearer behavior and writable data directory.
- Python audit, image vulnerability scan, history scan, sensitive-file requests,
  real local response captures and `git diff --check` were run.

Tests used synthetic access tokens only. No paid model call, live account change,
secret rotation, Render deployment, merge or direct main push was performed.

## Route inventory

The following inventory comes from `app.openapi()` in the reviewed source;
`/openapi.json` itself is disabled. All `/v1/` and `/artifacts/` routes require
shared access in hosted mode. Local mode without configured token is a trusted
loopback tool. Static pages/assets are public. Disabled hosted routes require
both authorization and local deployment rather than merely a bearer token.

| Methods | Route | Hosted access |
| --- | --- | --- |
| POST | `/v1/github/repositories/{repo_id}/cad/inspect` | Shared bearer token |
| GET, POST | `/v1/github/repositories` | Shared bearer token |
| POST | `/v1/github/repositories/{repo_id}/sync` | Shared bearer token |
| GET | `/v1/github/repositories/{repo_id}/commits` | Shared bearer token |
| GET | `/v1/github/repositories/{repo_id}/files` | Shared bearer token |
| GET | `/v1/github/repositories/{repo_id}/changes` | Shared bearer token |
| GET | `/v1/github/repositories/{repo_id}/preview` | Shared bearer token |
| GET | `/v1/github/repositories/{repo_id}/pcb` | Shared bearer token |
| GET | `/v1/github/repositories/{repo_id}/workspace` | Shared bearer token |
| GET, PUT | `/v1/github/repositories/{repo_id}/settings` | Shared bearer token |
| GET | `/v1/github/repositories/{repo_id}/artifact` | Shared bearer token |
| GET | `/v1/github/repositories/{repo_id}/schematic` | Shared bearer token |
| POST | `/v1/github/repositories/{repo_id}/audits` | Shared bearer token |
| GET | `/v1/github/repositories/{repo_id}/audits/{audit_id}` | Shared bearer token |
| GET, POST | `/v1/github/repositories/{repo_id}/audits/{audit_id}/explain` | Shared bearer token |
| GET | `/` | Public page |
| GET | `/projects` | Public page |
| GET | `/projects/github` | Public page |
| GET, POST | `/v1/projects` | Disabled (403 after auth) |
| POST | `/v1/projects/demo` | Disabled (403 after auth) |
| POST | `/v1/projects/{project_id}/pin-rules` | Disabled (403 after auth) |
| DELETE | `/v1/projects/{project_id}/pin-rules/{rule_id}` | Disabled (403 after auth) |
| POST | `/v1/projects/{project_id}/findings/{finding_id}/review` | Disabled (403 after auth) |
| GET | `/v1/projects/{project_id}/preview` | Disabled (403 after auth) |
| POST | `/v1/projects/{project_id}/demo-change` | Disabled (403 after auth) |
| POST | `/v1/projects/{project_id}/scan` | Disabled (403 after auth) |
| GET | `/v1/projects/{project_id}/handoff.md` | Disabled (403 after auth) |
| GET | `/artifacts/{run_id}/{path}` | Shared bearer token |
| GET | `/v1/status` | Shared bearer token |
| POST | `/v1/compare` | Disabled (403 after auth) |
| POST | `/v1/copilot` | Disabled (403 after auth) |
| POST | `/v1/design` | Disabled (403 after auth) |
| GET/HEAD | `/static/{path}` | Public static directory only |

No public health/metrics/admin route was added. Unknown paths return 404.
