# Phase 4: file connections and evidence-backed AI review

Implemented November 4, 2026. **Local Phase 4 gates passed**, including a real
configured-provider request on a synthetic fixture. Your existing Astra commit
comparison was re-audited locally without sending its contents to the model.

## What changed in the product

1. **Connections tab:** file nodes show schematic/PCB component matches,
   configured BOM and firmware links, and declared or possible board/CAD links.
   Click either file or a component entry to inspect its saved source evidence.
2. **Cross-file evidence:** PCB findings now link to the relevant schematic
   symbol at the same commit. Movement of a component on a CAD-linked board offers
   a possible mechanical-review link, without inventing a collision.
3. **AI review:** after an audit finishes, open AI review and click **Explain
   this audit**. The interface names the configured provider/model and discloses
   the selected audit facts and readable source snippets that will be sent. The
   three sections are what changed, what else to review, and what could not be
   checked. Every selected finding or connection has source links.
4. **ESP32 declarations:** namespace-qualified constants such as
   `Pins::motorLeftPwm = GPIO_NUM_39` are now readable. The parser keeps the
   logical GPIO interpretation separate from package/header pad numbers.

No additional test commits are needed to inspect this version. Refresh the
workspace, select `astra-companion`, and open its existing audit's Connections
tab. The AI action remains an explicit click; loading the workspace or polling
the result does not send project content to a model.

## Relationship engine

`extrude/workspace_links.py` builds commit-scoped relationships using the
existing bounded Git snapshots and readers. The version-4 audit stores them as:

```text
id, kind, status, source Evidence, target Evidence, summary, metadata
```

Kinds are schematic/PCB component, BOM/schematic component, firmware/hardware
pin, and board/enclosure. Status is confirmed, configured, possible, or
unverified. Each endpoint carries its exact repository, SHA, path, and locator.

- **Schematic ↔ PCB:** a strict basename-paired root scopes component references.
  Annotated references and pin numbers come from native KiCad netlists. Source
  sheet instance paths and symbol UUIDs resolve hierarchical components to the
  actual child file. A child schematic is not guessed to be another root.
- **Identity versus connectivity:** a unique reference match confirms identity
  within that project. Metadata separately lists agreeing and unresolved
  pad/net assignments. Reference matching does not approve the electrical design.
- **BOM:** configured assembly scope is retained, including when two assemblies
  both contain `U1`. Ambiguous/DNP rows are excluded from confirmed associations.
- **Firmware:** only explicit net/MCU/pad mappings can become confirmed. A
  configured disagreement remains a declared relationship and its separate pin
  check reports the discrepancy. GPIO enums are never accepted as package-pad
  numbers merely because the integers match.
- **CAD:** an explicit pair is configured. If there is exactly one paired KiCad
  project and one regular CAD asset, the engine can offer a possible project
  association. It requires confirmation and establishes no cavity or fit result.

The engine caps output at 600 relationships and eight KiCad projects, with
explicit truncation/unavailability coverage. Existing findings receive scoped
source links; no new deterministic fault is created just because two files were
connected. The JSON audit and evidence IDs remain the durable local record.

## ESP32 reader fix

`extrude/parse/workspace_firmware.py` recognizes namespace scopes while retaining
the restriction against evaluating function/local runtime context. It reads the
documented `GPIO_NUM_n` convention on `gpio_num_t` declarations and preserves a
qualified name. A short-name alias is available only when unambiguous; aliases
do not duplicate change findings. Conditional expressions, shadowed GPIO macros,
ambiguous assignments and unsupported expressions remain unverified.

The source convention was checked against [Espressif's GPIO definitions](https://github.com/espressif/esp-idf/blob/v5.4.1/components/hal/include/hal/gpio_types.h).
This is source-fact reading, not a compiler or a guarantee that a pin exists on
the selected device. Your actual schematic represents ESP32 connections as
headers, so a documented GPIO-to-header-pad mapping is still required for an
electrical pin verdict. No mapping was fabricated or silently added to settings.

## Explanation harness

`extrude/workspace_explain.py` wraps the existing model client with a narrowly
defined task: select and prioritize existing audit entries. It does not provide
an autonomous command runner or free-form engineering-fault generator.

```text
GET  /v1/github/repositories/{repo}/audits/{id}/explain
POST /v1/github/repositories/{repo}/audits/{id}/explain
     {"consent": true}
```

GET returns provider disclosure and cached job status. POST requires consent and
a complete/partial audit. It starts or reuses a queued/running/complete job. The
saved result is keyed by the frozen audit content, provider configuration, model,
prompt contract, and bounds. Only one explanation per repo and two globally can
run at once. Interrupted work becomes retryable after restart.

The model receives a trusted system instruction plus untrusted JSON audit data.
The context includes at most 40 findings, 24 relevant relationships, 20 coverage
gaps and six short readable code/CSV snippets. Missing configuration and failed
checks are prioritized among coverage gaps. Credential-like source lines and
sensitive filenames are omitted; raw CAD files and environment credentials are
not supplied. This is not a general secret-scanning guarantee, and the UI
discloses that source snippets may leave the machine.

Input is capped at 48,000 characters, response at 128 KiB/1,600 output tokens,
and the provider request at 35 seconds. There are no automatic model retries or
escalation calls. The model receives no tools or command capability.

The response schema accepts only existing source IDs and evidence IDs, grouped
into the three sections. Unknown entries, unrelated citations, duplicate entries,
inherited findings categorized as new changes, extra certainty/status fields and
invalid JSON are rejected. The server constructs display wording and certainty
from the cited deterministic records. The model cannot promote a suggestion into
a verified fault or mutate the audit. This deliberately restricts AI review to
grounded prioritization and linked-file review rather than novel design claims.

The UI shows how many findings were included in the bounded context. Empty
sections explicitly mean no items were selected, not that every possible issue
was checked. Failure, timeout or missing credentials affect only AI review;
findings, connections and file inspection remain usable.

The generic model client gained optional system-message, timeout, output-token
and response-byte bounds. Existing callers keep their previous defaults. Model
credentials stay in its authorization header and are separate from GitHub access.

## Gate evidence

| Criterion | Result |
| --- | --- |
| Scoped component/BOM connections | Passed. Two fixture assemblies share `U1`; BOM and finding evidence stay in the configured assembly. Pad/net agreement is recorded separately. |
| Hierarchical sources | Passed with real native KiCad export. A root-board relationship cites the component's actual child schematic and instance context. |
| Mechanical review | Passed. A moved connector on a CAD-linked board gets a possible CAD review link and retains observed-change certainty. No collision is invented. |
| ESP32 namespace reader | Passed. Named GPIO constants resolve; runtime scopes, shadowed enums and conditional/expression cases remain unverified. Your saved pin header now reads its named GPIO values. |
| Invalid AI claims/citations | Passed. Unknown evidence IDs, unknown source IDs, wrong categories and invented certainty fields are rejected. Original audit records remain unchanged. |
| Repository instruction injection | Passed at the harness boundary. Source instructions remain JSON data; no tools/commands exist in the model call, and only validated source selections are rendered. |
| API consent/cache/failure | Passed. GET never invokes the model; missing/false consent is rejected; concurrent duplicate requests reuse one call; saved responses persist; timeout/unavailable-provider states preserve the audit. |
| Existing product behavior | Passed. Git, PCB, CAD, BOM, native KiCad and workspace API regressions, plus existing model-client/loop tests, pass. |
| UI behavior | Passed in DOM checks. Connection nodes, tab navigation, explicit explanation request, source links and existing review behavior are covered. A fresh visual browser walkthrough is not claimed. |

Real-project local evidence:

- Repository `atireksd11/astra-companion`, base
  `e0751c92cdb498a6cf31f22fc47734bbc530117f`, head
  `0c8afb27b14d1b6190441f2ab683fe8058f7e7f0`.
- Final prepared audit: 324 findings and 208 relationships across both revisions:
  195 confirmed component identities, 11 unverified component matches, and two
  possible CAD associations. These counts do not mean all electrical nets or
  physical relationships are approved.
- The C34 missing-footprint finding opens both its head PCB evidence and the
  exact schematic symbol UUID. The actual board's unreadable/missing Edge.Cuts
  still prevents a physical board/cavity verdict.
- `data/phase4-astra-evidence.json` contains the saved audit/relationships.

Real model-call evidence:

- `data/phase4-live-model-evidence.json` records a successful request to the
  configured OpenRouter `openai/gpt-6-luna` model using a synthetic shipping-cost
  example, not the private project. The model selected the `$3.70 → $3.72` source
  and the missing pin-mapping coverage gap with valid IDs.
- Provider-reported usage: 430 input tokens, 105 output tokens, `$0.0000955`.
  This is that call's reported bill, not a price estimate for future requests.

Repeat checks:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_workspace_phase4.py tests/phase6/test_client.py tests/phase6/test_loop.py -q --basetemp=data/pytest-phase4-review
node tests/ui/github_workspace.test.cjs
```

Live project AI review is intentionally left to an explicit click after the
provider disclosure. Phase 5 is the assisted builder pilot, with remaining
physical mappings/outline inputs and unsupported source cases recorded as gaps.
