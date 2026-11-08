const $ = id => document.getElementById(id);
const root = "/v1/github/repositories";
let repos = [];
let repo;
let historyTip;
let revision;
let base;
let commitOffset;
let workspaceView;
let context = 0;
let previewRequest = 0;
let boardReview;
let auditTimer;
let historyRequest = 0;
let projectSettings = null;
let settingsRepo = null;
let disposeMesh = null;
let savingSettings = false;
let explanationTimer;
let explanationEpoch = 0;
const reviewNotes = new Map();
let selectedReview;
const reviewTabs = ["changes", "findings", "connections"];
const folders = new Map();
const commitTitles = new Map();

function selectReviewTab(name, focus = false) {
  for (const tab of reviewTabs) {
    const button = $(`github-tab-${tab}`);
    const selected = tab === name;
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
    $(`github-${tab}-panel`).hidden = !selected;
    if (focus && selected) button.focus?.();
  }
}

function showImport(visible) {
  $("github-import-panel").hidden = !visible;
  $("github-add").setAttribute("aria-expanded", String(visible));
  if (visible) $("github-source").focus?.();
}

function selectedPath(path) {
  for (const container of [$("github-tree"), $("github-files")]) {
    for (const button of container.querySelectorAll("button[data-path]")) {
      button.setAttribute("aria-pressed", String(button.dataset.path === path));
    }
  }
}

async function api(url, options) {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail
    : Array.isArray(body.detail) ? body.detail.map(item => `${item.loc?.slice(1).join(".")}: ${item.msg}`).join("; ")
      : "Workspace request failed.");
  return body;
}

function route(part, values = {}) {
  const params = new URLSearchParams(Object.entries(values).filter(([, value]) => value != null));
  return `${root}/${repo.id}/${part}?${params}`;
}

function row(list, title, detail, action) {
  const li = document.createElement("li");
  const button = document.createElement("button");
  button.type = "button";
  button.className = "github-row secondary";
  const heading = document.createElement("span");
  heading.className = "row-title";
  heading.textContent = title;
  const caption = document.createElement("small");
  caption.textContent = detail;
  button.append(heading, caption);
  button.addEventListener("click", () => {
    for (const current of list.querySelectorAll("[aria-pressed=true]")) current.setAttribute("aria-pressed", "false");
    button.setAttribute("aria-pressed", "true");
    run(action);
  });
  li.append(button);
  list.append(li);
  return button;
}

async function run(action) {
  const current = context;
  try { await action(); }
  catch (error) {
    if (current === context) {
      $("github-status").textContent = error.message;
      $("github-status").dataset.state = "error";
    }
  }
}

async function showRepo(id, selection = {}) {
  repo = repos.find(item => item.id === id);
  if (!repo) return;
  if (settingsRepo !== id) {
    projectSettings = null; settingsRepo = null;
    $("github-mapping-list").replaceChildren();
    $("github-check-setup").open = false;
  }
  $("github-link").href = repo.url;
  $("github-heading").textContent = repo.source;
  $("github-subtitle").textContent = "Your files, changes, and review evidence in one workspace.";
  $("github-welcome").hidden = true;
  $("github-add").hidden = false;
  showImport(false);
  $("github-compare").hidden = !repo.previous_head;
  $("github-workspace").hidden = false;
  const tips = [repo.head, ...repo.saved_tips.filter(sha => sha !== repo.head)];
  $("github-tip-label").hidden = tips.length < 2;
  $("github-tip").replaceChildren(...tips.map((sha, index) =>
    new Option(index === 0 ? `Latest sync · ${sha.slice(0, 8)}` : `Saved · ${sha.slice(0, 8)}`, sha)));
  await showHistory(repo.head, selection.revision || repo.head, selection.base);
}

async function showHistory(sha, selected = sha, compareFrom = null) {
  historyTip = sha;
  historyRequest++;
  commitTitles.clear();
  $("github-tip").value = sha;
  $("github-commits").replaceChildren();
  commitOffset = 0;
  await Promise.all([selectRevision(selected, compareFrom), loadCommits()]);
}

async function loadCommits() {
  const current = historyRequest;
  $("github-more-commits").hidden = true;
  const data = await api(route("commits", { revision: historyTip, offset: commitOffset }));
  if (current !== historyRequest) return;
  for (const item of data.commits) {
    commitTitles.set(item.sha, item.subject || "(No message)");
    const button = row($("github-commits"), item.subject || "(No message)",
      `${item.sha.slice(0, 8)} · ${item.author} · ${item.date.slice(0, 10)}`, () => {
        $("github-history-panel").open = false;
        return selectRevision(item.sha);
      });
    button.dataset.sha = item.sha;
    button.setAttribute("aria-pressed", String(item.sha === revision));
  }
  commitOffset = data.next_offset;
  $("github-more-commits").hidden = commitOffset == null;
  $("github-current-commit").textContent = commitTitles.get(revision) || revision.slice(0, 8);
}

async function selectRevision(sha, compareFrom = null) {
  revision = sha;
  base = compareFrom;
  const current = ++context;
  disposeMesh?.(); disposeMesh = null;
  clearTimeout(auditTimer);
  clearTimeout(explanationTimer);
  explanationEpoch++;
  reviewNotes.clear();
  selectedReview = null;
  $("github-ai-panel").hidden = true;
  $("github-ai-panel").open = false;
  $("github-review-summary").hidden = true;
  $("github-findings-empty").hidden = false;
  $("github-ai-results").replaceChildren();
  $("github-connections").replaceChildren();
  $("github-tab-connection-count").textContent = "0";
  workspaceView = null;
  $("github-preview").hidden = true;
  $("github-inspector-empty").hidden = false;
  $("github-tree").replaceChildren();
  folders.clear();
  $("github-files").replaceChildren();
  $("github-tree-count").textContent = "Loading project files…";
  $("github-file-count").textContent = "Loading files…";
  $("github-more-tree").hidden = $("github-more-files").hidden = true;
  $("github-audit-findings").replaceChildren();
  $("github-audit-coverage").hidden = true;
  $("github-audit-status").textContent = "";
  $("github-audit-run").disabled = true;
  $("github-audit-status").dataset.state = "idle";
  $("github-status").textContent = "";
  $("github-total-files").textContent = $("github-total-changes").textContent = $("github-total-findings").textContent = "—";
  $("github-tab-change-count").textContent = $("github-tab-finding-count").textContent = "0";
  $("github-current-commit").textContent = commitTitles.get(sha) || sha.slice(0, 8);
  selectReviewTab("changes");
  $("github-revision").textContent = `Loading ${sha.slice(0, 8)}…`;
  $("github-latest").hidden = sha === repo.head;
  for (const button of $("github-commits").querySelectorAll("button[data-sha]")) {
    button.setAttribute("aria-pressed", String(button.dataset.sha === sha));
  }
  let data;
  try { data = await api(route("workspace", { revision, base })); }
  catch (error) {
    if (current === context) {
      $("github-revision").textContent = error.message;
      $("github-latest").hidden = false;
    }
    return;
  }
  if (current !== context) return;
  workspaceView = data;
  base = data.base_sha;
  $("github-revision").textContent = base ? `${base.slice(0, 8)} → ${revision.slice(0, 8)}` : `Initial snapshot · ${revision.slice(0, 8)}`;
  $("github-revision").title = [base, revision].filter(Boolean).join(" → ");
  const params = new URLSearchParams({ repo: repo.id, revision });
  if (base) params.set("base", base);
  window.history.replaceState(null, "", `?${params}`);
  renderFiles(data.changes);
  renderTree(data.inventory);
  $("github-audit-run").disabled = false;
  $("github-audit-run").textContent = "Run audit";
  if (data.audit) await showAudit(data.audit.id, current);
  else $("github-audit-status").textContent = "Run the audit to review supported PCB changes.";
}

const statuses = { A: "Added", M: "Modified", D: "Removed", R: "Renamed", C: "Copied", T: "Type changed" };
const areas = { pcb: "PCB", schematic: "Schematic", cad: "CAD", firmware: "Firmware", code: "Code", bom: "BOM", docs: "Docs", other: "Other" };

function renderFiles(page) {
  $("github-file-count").textContent = `${page.total} changed files`;
  $("github-total-changes").textContent = $("github-tab-change-count").textContent = String(page.total);
  if (!page.total) {
    const empty = document.createElement("li");
    empty.className = "list-empty";
    empty.textContent = "These revisions have the same file contents. Pick another commit to review a change.";
    $("github-files").append(empty);
  }
  for (const item of page.files) {
    const title = item.previous_path ? `${item.previous_path} → ${item.path}` : item.path;
    const button = row($("github-files"), title, `${statuses[item.status] || "Changed"} · ${areas[item.domain] || "Other"}`,
      () => showPreview(item, base));
    button.dataset.status = item.status;
    button.dataset.path = item.path;
  }
  $("github-more-files").hidden = page.next_offset == null;
}

function folder(parent, label, key, open = false) {
  if (folders.has(key)) return folders.get(key);
  const details = document.createElement("details");
  const summary = document.createElement("summary");
  summary.textContent = label;
  details.open = open;
  details.append(summary);
  parent.append(details);
  folders.set(key, details);
  return details;
}

function renderTree(page) {
  $("github-tree-count").textContent = `${page.total} files at ${revision.slice(0, 8)}`;
  $("github-total-files").textContent = String(page.total);
  for (const item of page.files) {
    const area = item.domain in areas ? item.domain : "other";
    let parent = folder($("github-tree"), areas[area], area, true);
    let key = area;
    const parts = item.path.split("/");
    for (const part of parts.slice(0, -1)) {
      key += "/" + part;
      parent = folder(parent, part, key);
    }
    const button = document.createElement("button");
    button.type = "button";
    button.className = "github-row";
    button.textContent = parts.at(-1);
    button.title = item.path;
    button.dataset.path = item.path;
    button.setAttribute("aria-pressed", "false");
    button.addEventListener("click", () => run(() => showPreview(item, null)));
    parent.append(button);
  }
  $("github-more-tree").hidden = page.next_offset == null;
}

async function loadMore(which) {
  if (!workspaceView) return;
  const current = context;
  const offset = workspaceView[which].next_offset;
  if (offset == null) return;
  const button = $(which === "inventory" ? "github-more-tree" : "github-more-files");
  button.disabled = true;
  let data;
  try {
    const key = which === "inventory" ? "file_offset" : "change_offset";
    data = await api(route("workspace", { revision, base, [key]: offset }));
  } finally { button.disabled = false; }
  if (current !== context) return;
  workspaceView[which] = data[which];
  (which === "inventory" ? renderTree : renderFiles)(data[which]);
}

async function showPreview(item, parent, finding = null, inspectSha = revision, reviewItem = null) {
  const current = context;
  const request = ++previewRequest;
    disposeMesh?.(); disposeMesh = null;
    $("github-artifact").hidden = true;
    $("github-artifact-mesh").replaceChildren();
    if (/\.(stl|obj|step|stp|csv|tsv|c|cpp|cc|cxx|h|hpp|ino|py)$/i.test(item.path)) {
      $("github-artifact").hidden = false;
      $("github-artifact-summary").textContent = "Reading saved geometry or file facts…";
      $("github-artifact-facts").replaceChildren();
      run(() => loadArtifact(item, parent, inspectSha, current, request));
    }
  $("github-preview").hidden = false;
  $("github-finding-source").hidden = false;
  $("github-inspector-empty").hidden = true;
  $("github-file-name").textContent = item.path;
  selectedPath(item.path);
  $("github-source-hint").textContent = finding
    ? item.status && !item.singleRevisionEvidence ? "Finding evidence from both revisions." : "Finding evidence from one revision."
    : item.status
    ? `${statuses[item.status] || "Changed"} file · Compare the saved versions below.`
    : "Saved contents at the selected commit.";
  $("github-after-label").textContent = `At ${inspectSha.slice(0, 8)}`;
  selectedReview = reviewItem;
  renderFindingReport(reviewItem);
  renderEvidence(finding, reviewItem);
  if (reviewItem && window.matchMedia?.("(max-width: 640px)").matches) {
    $("github-finding-report").querySelector("h3").focus({ preventScroll: true });
    $("github-preview").scrollIntoView({ block: "start" });
  }
    const schematic = item.path.toLowerCase().endsWith(".kicad_sch");
    const board = item.path.toLowerCase().endsWith(".kicad_pcb");
    $("github-pcb").hidden = (!board && !schematic) || !item.status;
    $("github-hardware-label").textContent = schematic ? "SCHEMATIC REVIEW" : "PCB REVIEW";
    $("github-hardware-title").textContent = schematic ? "Inside the schematic" : "Inside the board";
    $("github-pcb-summary").textContent = "Reading both saved versions…";
  $("github-pcb-changes").replaceChildren();
  $("github-pcb-more").hidden = true;
  boardReview = $("github-pcb").hidden ? null : {
      context: current, request, revision: inspectSha, base: parent, path: item.path,
      previous_path: item.previous_path, offset: 0, schematic
  };
  if (boardReview) run(loadBoardReview);
  $("github-before").hidden = !item.status;
  const before = $("github-before").querySelector("pre");
  const after = $("github-after");
  before.textContent = after.textContent = "Loading…";
  async function read(sha, path) {
    if (!sha) return item.singleRevisionEvidence ? "No evidence was cited for this revision." : "File was not present.";
    const data = await api(route("preview", { revision: sha, path }));
    return data.text ?? data.reason;
  }
  const results = await Promise.allSettled([
    read(item.status === "A" ? null : parent, item.previous_path || item.path),
    read(item.status === "D" ? null : inspectSha, item.path)
  ]);
  if (current !== context || request !== previewRequest) return;
  [before, after].forEach((pane, index) => {
    const result = results[index];
    pane.textContent = result.status === "fulfilled" ? result.value : result.reason.message;
  });
}

const pcbLabels = {
  footprint_added: "Footprint added", footprint_removed: "Footprint removed",
  reference_changed: "Reference changed", position_changed: "Footprint moved",
  rotation_changed: "Rotation changed", layer_changed: "Board side changed",
  library_changed: "Footprint library changed", pad_net_changed: "Pad net changed",
  pad_disconnected: "Pad lost its net · Review wiring",
  pad_assignments_changed: "Pad assignments changed", pad_added: "Pad added", pad_removed: "Pad removed"
};

function boardValue(value, kind) {
  if (value == null) return "—";
  if (kind === "position_changed") return `(${value.join(", ")}) mm`;
  if (kind === "rotation_changed") return `${value}°`;
  if (Array.isArray(value)) return value.map(net => net ?? "unconnected").join(", ");
    if (typeof value === "object") return value.library && value.x_mm != null
      ? `${value.library} · (${value.x_mm}, ${value.y_mm}) mm · ${value.layer}` : JSON.stringify(value);
  return String(value);
}

async function loadBoardReview() {
  const active = boardReview;
  if (!active) return;
    const { revision, base, path, previous_path, offset, schematic } = active;
  const isCurrent = () => boardReview === active && active.context === context && active.request === previewRequest;
  $("github-pcb-more").hidden = true;
  let data;
  try {
      data = await api(route(schematic ? "schematic" : "pcb", { revision, base, path, previous_path, offset }));
  } catch (error) {
    if (isCurrent()) $("github-pcb-summary").textContent = error.message;
    return;
  }
  if (!isCurrent()) return;
  const evidence = (label, side) => side.status === "read"
      ? `${label}: ${schematic ? `${side.symbols} symbols` : `${side.footprints} footprints`} at ${side.sha.slice(0, 8)}`
      : `${label}: ${side.detail || "file absent"}`;
    const fields = schematic ? "placed symbol fields" : "footprints or pad assignments";
  const result = data.status === "unverified"
    ? "Comparison unavailable."
      : data.total ? `${data.total} changes in ${fields}.`
        : `No changes in ${fields}.`;
    $("github-pcb-summary").textContent = `${result} ${evidence("Before", data.before)}. ${evidence("After", data.after)}. ${schematic ? "Electrical connectivity is checked separately in the audit." : "This view covers placement and pad assignments."}`;
  for (const change of data.changes) {
    const row = document.createElement("li");
    const title = document.createElement("strong");
    title.textContent = `${change.reference}${change.pad ? ` · Pad ${change.pad}` : ""} · ${pcbLabels[change.kind] || change.kind}`;
    const detail = document.createElement("span");
    detail.textContent = `${boardValue(change.before, change.kind)} → ${boardValue(change.after, change.kind)}`;
    row.append(title, detail);
    $("github-pcb-changes").append(row);
  }
  active.offset = data.next_offset;
  $("github-pcb-more").hidden = active.offset == null;
}

function renderEvidence(finding, reviewItem) {
  const source = $("github-evidence");
  const related = $("github-related");
  source.replaceChildren();
  related.replaceChildren();
  source.hidden = !finding?.evidence.length;
  related.hidden = !finding?.related.length;
  if (!finding) return;
  const inspect = item => showPreview({ path: item.path }, null, finding, item.sha, reviewItem);
  for (const item of finding.evidence) {
    row(source, item.path, `${item.sha.slice(0, 8)} · ${item.locator}`, () => inspect(item));
  }
  for (const item of finding.related) {
      const basis = item.basis === "same_name" ? "Same project filename · Review link"
        : item.basis === "possible" ? "Possible impact · Needs review" : item.basis;
    row(related, item.path, `${item.sha.slice(0, 8)} · ${basis}`, () => inspect(item));
  }
}

function showFinding(finding, audit, reviewItem) {
  const before = finding.evidence.find(item => item.sha === audit.base_sha);
  const after = finding.evidence.find(item => item.sha === audit.head_sha);
  const item = after || before;
  if (!item) {
    if (reviewItem) {
      previewRequest++;
      disposeMesh?.(); disposeMesh = null;
      $("github-preview").hidden = false;
      $("github-finding-source").hidden = true;
      $("github-inspector-empty").hidden = true;
      selectedReview = reviewItem;
      renderFindingReport(reviewItem);
      if (window.matchMedia?.("(max-width: 640px)").matches) {
        $("github-finding-report").querySelector("h3").focus({ preventScroll: true });
        $("github-preview").scrollIntoView({ block: "start" });
      }
    }
    return;
  }
  const status = before && after ? "M" : before ? "D" : "A";
  return showPreview({ path: item.path, previous_path: before?.path, status,
    singleRevisionEvidence: !before || !after }, audit.base_sha, finding, audit.head_sha, reviewItem);
}

function findingTitle(finding) {
  const kind = finding.rule_id.split(".").at(-1);
  const label = finding.rule_id.startsWith("pcb.") && pcbLabels[kind];
  return label ? `${finding.summary.split(":")[0]} · ${label}` : finding.summary;
}

function findingState(finding) {
  const lifecycle = { new: "New at selected commit", existing: "Already present",
    resolved: "Resolved", present_at_head: "Present at selected commit · Baseline unverified" };
  const certainty = { suggestion: "Review suggested", verified: "Check found a problem",
    unverified: "Unverified", observed: "Observed change" };
  const severity = finding.status === "verified" && finding.lifecycle !== "resolved"
    ? { error: "Error", warning: "Warning", info: "Info" }[finding.severity] : null;
  const status = finding.lifecycle !== "resolved" ? certainty[finding.status] : null;
  return [status, lifecycle[finding.lifecycle], severity].filter(Boolean).join(" · ");
}

function appendExplanation(parent, fields) {
  const list = document.createElement("dl");
  for (const [label, value] of fields) {
    const term = document.createElement("dt");
    term.textContent = label;
    const text = document.createElement("dd");
    text.textContent = value;
    list.append(term, text);
  }
  parent.append(list);
}

function appendReviewNote(parent, note) {
  appendExplanation(parent, [["What it means", note.explanation], ["Why it matters", note.impact], ["What to do next", note.next_step]]);
}

function renderFindingReport(item) {
  const panel = $("github-finding-report");
  panel.replaceChildren();
  panel.hidden = !item;
  if (!item) return;
  const heading = document.createElement("h3");
  heading.tabIndex = -1;
  heading.textContent = item.title;
  const state = document.createElement("p");
  state.className = "finding-state";
  state.textContent = item.libraries ? item.caption : findingState(item.findings[0]);
  panel.append(heading, state);
  const fields = [["What happened", item.what], ["Why it matters", item.why], ["What to do next", item.next_step]];
  const finding = item.findings[0];
  if (!item.libraries && !finding.lifecycle && (finding.before != null || finding.after != null)) {
    const kind = finding.rule_id.split(".").at(-1);
    fields.splice(1, 0, ["Before → after", `${boardValue(finding.before, kind)} → ${boardValue(finding.after, kind)}`]);
  }
  appendExplanation(panel, fields);
  if (item.libraries) {
    const list = document.createElement("ul");
    for (const library of item.libraries) {
      const li = document.createElement("li");
      li.textContent = `${library.kind === "symbol" ? "Symbol" : "Footprint"} library: ${library.name}${library.references.length ? ` · ${library.references.join(", ")}` : ""}`;
      list.append(li);
    }
    panel.append(list);
  }
  const note = reviewNotes.get(item.source_id);
  if (note) {
    const section = document.createElement("section");
    section.className = "finding-ai";
    const title = document.createElement("h4");
    title.textContent = "AI interpretation";
    section.append(title);
    appendReviewNote(section, note);
    panel.append(section);
  }
  const details = document.createElement("details");
  const label = document.createElement("summary");
  label.textContent = "Original checker output";
  details.append(label);
  for (const finding of item.findings) {
    const raw = document.createElement("p");
    raw.textContent = `${finding.rule_id} · ${finding.summary}`;
    details.append(raw);
  }
  panel.append(details);
}

function inspectReviewItem(item, audit) {
  const findings = item.findings;
  if (findings.length === 1) return showFinding(findings[0], audit, item);
  const evidence = new Map(findings.flatMap(f => f.evidence)
    .map(e => [JSON.stringify([e.sha, e.path, e.locator]), e]));
  return showFinding({ evidence: [...evidence.values()], related: [] }, audit, item);
}

function renderAuditReview(audit) {
  const report = audit.review;
  const list = $("github-audit-findings");
  list.replaceChildren();
  const overview = $("github-review-summary");
  overview.hidden = !["complete", "partial"].includes(audit.state);
  $("github-tab-finding-count").textContent = String(report?.finding_count ?? audit.findings.length);
  if (overview.hidden) {
    const empty = document.createElement("li");
    empty.className = "list-empty";
    empty.textContent = "Retry the audit to read these files.";
    list.append(empty);
    return;
  }
  const changes = workspaceView.changes;
  const changedPath = changes?.total === 1 ? changes.files?.[0]?.path : null;
  const facts = changedPath ? `Only ${changedPath} changed.`
    : changes ? `${changes.total} changed files.` : "";
  const verified = report?.new_problems || 0;
  const baselineNote = report?.baseline_unverified ? "Some problems could only be checked at the selected commit." : "";
  const verdict = verified ? `${verified} new problem${verified === 1 ? "" : "s"} found by the checks.`
    : audit.base_sha ? "The checks that ran found no new verified problems."
    : "This audit covers a single commit.";
  overview.textContent = [facts, verdict, baselineNote, audit.state === "partial" ? "Some checks are still incomplete." : ""].filter(Boolean).join(" ");
  for (const group of report?.groups || []) {
    const label = document.createElement("li");
    label.className = "finding-group";
    label.textContent = group.title;
    list.append(label);
    for (const entry of group.items) {
      const findings = entry.indexes.map(index => audit.findings[index]);
      const finding = findings[0];
      const title = entry.title || findingTitle(finding);
      const caption = entry.libraries
        ? `${entry.libraries.length} missing library reference${entry.libraries.length === 1 ? "" : "s"} · ${findings.every(f => f.lifecycle === "existing") ? "Already present in both commits" : "Library check incomplete"}`
        : findingState(finding);
      const item = { ...entry, findings, title, caption };
      const button = row(list, title, caption, () => inspectReviewItem(item, audit));
      button.dataset.status = entry.libraries || finding.status === "unverified" ? "?"
        : finding.lifecycle === "resolved" ? "✓" : finding.status === "observed" ? "Δ" : "!";
    }
  }
}

async function showAudit(id, current) {
  const button = $("github-audit-run");
  button.disabled = true;
  const status = $("github-audit-status");
    const stateText = { queued: "Audit queued…", running: "Comparing files and running available KiCad checks…", complete: "Audit saved",
    partial: "Partial audit saved. See coverage for what still needs checking.", failed: "Audit could not finish." };
  let audit;
  try { audit = await api(route(`audits/${id}`)); }
  catch (error) {
    if (current === context) {
      status.textContent = error.message;
      button.disabled = false;
    }
    return;
  }
  if (current !== context) return;
  status.dataset.state = audit.state;
  status.textContent = audit.detail || stateText[audit.state];
  if (audit.state === "queued" || audit.state === "running") {
    auditTimer = setTimeout(() => showAudit(id, current), 700);
    return;
  }
  workspaceView.audit = audit;
    renderConnections(audit);
    if (["complete", "partial"].includes(audit.state)) run(() => loadExplanation(audit.id, current));
  $("github-findings-empty").hidden = true;
  button.textContent = audit.state === "complete" ? "Audit saved"
    : audit.state === "partial" ? "Retry audit" : "Run audit again";
  button.disabled = audit.state === "complete";
  renderAuditReview(audit);
  $("github-total-findings").textContent = $("github-tab-finding-count").textContent;
  const coverage = $("github-audit-coverage");
  const entries = coverage.querySelector("ul");
  entries.replaceChildren();
  for (const item of audit.coverage) {
    const li = document.createElement("li");
    li.textContent = `${item.path || "Project"} · ${item.check} · ${item.outcome}: ${item.detail}`;
    entries.append(li);
  }
  coverage.hidden = !audit.coverage.length;
}

async function startAudit() {
  if (!workspaceView) return;
  const current = context;
  clearTimeout(explanationTimer); explanationEpoch++;
  reviewNotes.clear();
  renderFindingReport(selectedReview);
  $("github-review-summary").hidden = true;
  $("github-findings-empty").hidden = true;
  $("github-ai-panel").hidden = true; $("github-ai-results").replaceChildren();
  $("github-audit-run").disabled = true;
  $("github-audit-status").textContent = "Starting audit…";
  $("github-audit-status").dataset.state = "running";
  selectReviewTab("findings");
  $("github-audit-findings").replaceChildren();
  try {
    const audit = await api(route("audits"), { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ revision, base, retry: workspaceView.audit?.state === "partial" }) });
    if (current === context) await showAudit(audit.id, current);
  } catch (error) {
    if (current === context) {
      $("github-audit-status").textContent = error.message;
      $("github-audit-run").disabled = false;
    }
  }
}

async function refresh(id, selection = {}) {
  repos = await api(root);
  const select = $("github-repo");
  select.replaceChildren(...repos.map(item => new Option(item.source, item.id)));
  if (!repos.length) return;
  select.value = repos.some(item => item.id === id) ? id : repos[0].id;
  await showRepo(select.value, select.value === id ? selection : {});
}

async function importOrSync(button, url, body) {
  button.disabled = true;
  $("github-status").textContent = "Reading GitHub history…";
  $("github-status").dataset.state = "loading";
  const selected = repo?.id;
  const current = context;
  const selection = body ? {} : { revision, base };
  try {
    const item = await api(url, { method: "POST", headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined });
    if (body || (current === context && selected === repo?.id)) await refresh(item.id, selection);
    $("github-status").textContent = `${item.source} is saved at ${item.head.slice(0, 8)}.`;
    $("github-status").dataset.state = "success";
  } finally { button.disabled = false; }
}

$("connect-github").addEventListener("submit", event => {
  event.preventDefault();
  run(() => importOrSync(event.submitter, root, { source: $("github-source").value }));
});
$("github-sync").addEventListener("click", event => run(() => importOrSync(event.currentTarget, route("sync"))));
$("github-repo").addEventListener("change", event => run(() => showRepo(event.target.value)));
$("github-tip").addEventListener("change", event => run(() => showHistory(event.target.value)));
$("github-compare").addEventListener("click", () => run(() => showHistory(repo.head, repo.head, repo.previous_head)));
$("github-latest").addEventListener("click", () => run(() => showHistory(repo.head)));
$("github-more-commits").addEventListener("click", () => run(loadCommits));
$("github-more-files").addEventListener("click", () => run(() => loadMore("changes")));
$("github-more-tree").addEventListener("click", () => run(() => loadMore("inventory")));
$("github-pcb-more").addEventListener("click", () => run(loadBoardReview));
$("github-audit-run").addEventListener("click", () => run(startAudit));
$("github-explain").addEventListener("click", () => run(requestExplanation));
$("github-check-setup").addEventListener("toggle", () => {
  if ($("github-check-setup").open) run(loadSettings);
});
$("github-cad-form").addEventListener("submit", event => {
  event.preventDefault();
  run(() => addMapping("cad_pairs", {
    board_file: $("map-board").value.trim(), mesh_file: $("map-mesh").value.trim(), units: $("map-units").value,
    mesh_kind: $("map-role").value, board_axes: [...$("map-axes").value],
    cavity_mm: $("map-cavity").value.trim() ? $("map-cavity").value.split(",").map(Number) : null
  }));
});
$("github-pin-form").addEventListener("submit", event => {
  event.preventDefault();
  run(() => addMapping("pin_assignments", {
    firmware_file: $("map-code").value.trim(), firmware_symbol: $("map-symbol").value.trim(),
    netlist_file: $("map-netlist").value.trim(), schematic_net: $("map-net").value.trim(), mcu_ref: $("map-mcu").value.trim(),
    numbering: $("map-numbering").value,
    gpio_to_pad: Object.fromEntries($("map-gpio").value.split(",").filter(s => s.trim()).map(s => s.split(":").map(p => p.trim())))
  }));
});
$("github-bom-form").addEventListener("submit", event => {
  event.preventDefault();
  run(() => addMapping("boms", {
    bom_file: $("map-bom").value.trim(), schematic_file: $("map-assembly").value.trim(),
    reference_column: $("map-ref-column").value.trim(), part_column: $("map-part-column").value.trim(),
    quantity_column: $("map-qty-column").value.trim(), dnp_column: $("map-dnp-column").value.trim() || null,
    delimiter: $("map-delimiter").value === "tab" ? "\t" : $("map-delimiter").value
  }));
});
$("github-add").addEventListener("click", () => showImport($("github-import-panel").hidden));
  for (const name of reviewTabs) {
  const tab = $(`github-tab-${name}`);
  tab.addEventListener("click", () => selectReviewTab(name));
  tab.addEventListener("keydown", event => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
      const next = event.key === "Home" ? reviewTabs[0] : event.key === "End" ? reviewTabs.at(-1)
        : reviewTabs[(reviewTabs.indexOf(name) + (event.key === "ArrowRight" ? 1 : -1) + reviewTabs.length) % reviewTabs.length];
    selectReviewTab(next, true);
  });
}
const initial = new URLSearchParams(window.location.search);
run(() => refresh(initial.get("repo"), { revision: initial.get("revision"), base: initial.get("base") }));

async function loadArtifact(item, parent, sha, current, request) {
  try {
    const data = await api(route("artifact", { revision: sha, base: parent, path: item.path, previous_path: item.previous_path }));
    if (current !== context || request !== previewRequest) return;
    const a = data.before, b = data.after;
    const describe = (label, side) => {
      if (side.status !== "read") return `${label}: ${side.detail || "file absent"}`;
      const f = side.facts;
      if (f.dimensions) return `${label}: ${f.dimensions.map(n => Number(n.toFixed(3))).join(" × ")} ${f.unit}${f.solids != null ? ` · ${f.solids} solids · ${f.faces} faces` : ` · ${f.total_triangles} triangles`}`;
        if (f.constants) return `${label}: ${new Set(Object.values(f.constants).map(item => item.line)).size} declaration lines. Expressions and conditional values remain unverified.`;
      return `${label}: ${f.total_rows} CSV rows. Columns: ${f.columns.join(", ")}`;
    };
    $("github-artifact-summary").textContent = `${describe("Before", a)}. ${describe("After", b)}.`;
      if (data.csv_comparison) {
        const comparison = data.csv_comparison;
        $("github-artifact-summary").textContent = `${comparison.changed_cells} changed ${comparison.changed_cells === 1 ? "cell" : "cells"} · ${comparison.added} added rows · ${comparison.removed} removed rows. ${comparison.detail}${comparison.ambiguous ? ` ${comparison.ambiguous} rows could not be matched.` : ""}${comparison.added_columns?.length ? ` Added columns: ${comparison.added_columns.join(", ")}.` : ""}${comparison.removed_columns?.length ? ` Removed columns: ${comparison.removed_columns.join(", ")}.` : ""}`;
        renderCsvComparison($("github-artifact-facts"), comparison);
        return;
      }
    const selected = b.status === "read" ? b : a.status === "read" ? a : null;
    if (selected?.facts.triangles?.length && window.ExtrudeMesh) {
      disposeMesh = window.ExtrudeMesh.mount($("github-artifact-mesh"), selected.facts);
    }
    if (selected) {
      const pre = document.createElement("pre");
      const facts = selected.facts;
        if (facts.rows) {
          renderCsvComparison($("github-artifact-facts"), { columns: facts.columns, rows: facts.rows.map(row => ({status: "unverified", before: null, after: row, changes: []})), ambiguous: facts.rows.length });
          return;
        }
        pre.textContent = facts.constants ? JSON.stringify(facts.constants, null, 2)
        : `Units: ${facts.unit}\n${facts.source || "STL/OBJ does not establish physical units or usable inner cavity."}${facts.volume_mm3 != null ? `\nSolid volume: ${Number(facts.volume_mm3.toFixed(3))} mm³\n${facts.volume_scope || ""}` : ""}${facts.preview_unavailable ? `\n${facts.preview_unavailable}` : ""}`;
      $("github-artifact-facts").replaceChildren(pre);
    }
  } catch (error) {
    if (current === context && request === previewRequest) $("github-artifact-summary").textContent = error.message;
  }
}

function renderCsvComparison(container, comparison) {
  container.replaceChildren();
  const controls = document.createElement("div"); controls.className = "csv-controls";
  const label = document.createElement("label");
  const filter = document.createElement("input"); filter.type = "checkbox";
  filter.checked = comparison.rows.some(row => ["modified", "added", "removed"].includes(row.status));
  const text = document.createElement("span"); text.textContent = "Show changed rows only";
  label.append(filter, text);
  const count = document.createElement("span");
  controls.append(label, count);
  const wrap = document.createElement("div"); wrap.className = "csv-table-scroll";
  wrap.setAttribute("role", "region"); wrap.setAttribute("aria-label", "BOM cell comparison"); wrap.tabIndex = 0;
  const table = document.createElement("table"); table.className = "csv-review-table";
  const caption = document.createElement("caption"); caption.textContent = "Saved BOM values · highlighted cells show before → after";
  const head = document.createElement("thead"); const heading = document.createElement("tr");
  for (const column of ["Change", ...comparison.columns]) {
    const th = document.createElement("th"); th.scope = "col"; th.textContent = column; heading.append(th);
  }
  head.append(heading);
  const body = document.createElement("tbody"); table.append(caption, head, body); wrap.append(table);
  const more = document.createElement("button"); more.className = "button secondary csv-more"; more.type = "button"; more.textContent = "Show more rows";
  let limit = 100;
  const value = input => input === null || input === undefined ? "Not present" : input === "" ? "(empty)" : String(input);
  function draw() {
    body.replaceChildren();
    const rows = comparison.rows.filter(row => !filter.checked || row.status !== "unchanged");
    for (const row of rows.slice(0, limit)) {
      const tr = document.createElement("tr"); tr.dataset.status = row.status;
      const status = document.createElement("td"); status.className = "csv-status";
      status.textContent = ({modified: "Changed", added: "Added", removed: "Removed", unchanged: "Unchanged", unverified: "Unmatched"})[row.status];
      if (row.status === "unverified") status.textContent += row.after ? " · after" : " · before";
      tr.append(status);
      for (const column of comparison.columns) {
        const cell = document.createElement("td");
        const change = row.changes.find(change => change.column === column);
        if (change) {
          cell.className = "csv-cell-changed";
          const old = document.createElement("del"); old.textContent = value(change.before);
          const arrow = document.createElement("span"); arrow.className = "csv-arrow"; arrow.textContent = " → ";
          const current = document.createElement("ins"); current.textContent = value(change.after);
          cell.append(old, arrow, current);
        } else {
          cell.textContent = value((row.after || row.before)?.fields[column]);
        }
        tr.append(cell);
      }
      body.append(tr);
    }
    count.textContent = `${Math.min(limit, rows.length)} of ${rows.length} rows`;
    more.hidden = rows.length <= limit;
  }
  filter.addEventListener("change", () => { limit = 100; draw(); });
  more.addEventListener("click", () => { limit += 100; draw(); });
  container.append(controls, wrap, more); draw();
}

async function loadSettings() {
  if (!repo) return;
  const id = repo.id;
  $("github-settings-status").textContent = "Loading project mappings…";
  const settings = await api(route("settings"));
  if (repo?.id !== id) return;
  projectSettings = settings; settingsRepo = id;
  renderMappings();
  $("github-settings-status").textContent = "No files are modified. Each mapping scopes a check; bounding dimensions do not prove a complete fit.";
}

function renderMappings() {
  const list = $("github-mapping-list"); list.replaceChildren();
  for (const key of ["cad_pairs", "pin_assignments", "boms"]) {
    for (const [index, rule] of (projectSettings[key] || []).entries()) {
      const div = document.createElement("div"); div.className = "mapping-entry";
      const text = document.createElement("span");
      text.textContent = key === "cad_pairs" ? `${rule.board_file} → ${rule.mesh_file} · ${rule.units} · ${rule.board_axes.join(", ")}`
        : key === "pin_assignments" ? `${rule.firmware_symbol} in ${rule.firmware_file} → ${rule.mcu_ref} / ${rule.schematic_net}`
        : `${rule.bom_file} → ${rule.schematic_file}`;
      const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "Remove";
      remove.addEventListener("click", () => run(async () => {
        const next = JSON.parse(JSON.stringify(projectSettings)); next[key].splice(index, 1); await persistSettings(next);
      }));
      div.append(text, remove); list.append(div);
    }
  }
}

async function addMapping(key, rule) {
  const id = repo?.id;
  if (settingsRepo !== repo?.id || !projectSettings) await loadSettings();
  if (repo?.id !== id || settingsRepo !== id) return;
  const next = JSON.parse(JSON.stringify(projectSettings)); next[key].push(rule);
  await persistSettings(next);
}

async function persistSettings(next) {
  const id = repo.id;
  if (settingsRepo !== id) return;
  if (savingSettings) { $("github-settings-status").textContent = "A save is in progress. Wait for it to finish."; return; }
  savingSettings = true;
  $("github-settings-status").textContent = "Saving…";
  try {
    const saved = await api(route("settings"), { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(next) });
    if (repo?.id !== id) return;
    projectSettings = saved; settingsRepo = id; renderMappings();
    $("github-settings-status").textContent = "Saved. Run the audit to use these mappings for the selected commit pair.";
    await selectRevision(revision, base);
  } catch (error) { if (repo?.id === id) $("github-settings-status").textContent = error.message; }
  finally { savingSettings = false; }
}

function renderConnections(audit) {
  const container = $("github-connections"); container.replaceChildren();
  const links = (audit.relationships || []).filter(link => link.source.sha === audit.head_sha);
  $("github-tab-connection-count").textContent = String(links.length);
  if (!links.length) {
    const p = document.createElement("p"); p.className = "list-empty";
    p.textContent = "No scoped file connections were established at this commit. Review audit coverage or declare a relationship in Project check setup.";
    container.append(p); return;
  }
  const groups = new Map();
  for (const link of links) {
    const key = JSON.stringify([link.kind, link.status, link.source.path, link.target.path]);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(link);
  }
  for (const group of groups.values()) {
    const first = group[0];
    const card = document.createElement("article"); card.className = "connection-card";
    const nodes = document.createElement("div"); nodes.className = "connection-nodes";
    for (const [index, item] of [first.source, first.target].entries()) {
      if (index) { const arrow = document.createElement("span"); arrow.className = "connection-arrow"; arrow.textContent = "↔"; nodes.append(arrow); }
      const button = document.createElement("button"); button.className = "connection-node"; button.type = "button";
      button.textContent = item.path; button.addEventListener("click", () => run(() => showPreview({path:item.path}, null, {evidence:[first.source,first.target],related:[]}, item.sha)));
      nodes.append(button);
    }
    const description = document.createElement("p");
    description.textContent = `${first.status} · ${group.length} ${first.kind === "board_enclosure" ? "declared enclosure link" : "component/pin links"}`;
    const details = document.createElement("details"); const summary = document.createElement("summary"); summary.textContent = "Inspect linked components";
    const list = document.createElement("ul"); list.className = "evidence-list";
    let offset = 0;
    const more = document.createElement("button"); more.type = "button"; more.className = "button secondary"; more.textContent = "Show more connections";
    function appendLinks() {
      for (const link of group.slice(offset, offset + 30)) {
        const pads = link.metadata.matching_pads;
        const detail = pads ? `${pads.length} pad/net matches · ${link.metadata.unmatched_pads.length} unresolved pad/net matches` : link.status;
        row(list, link.summary, detail, () => showPreview({path:link.target.path}, null, {evidence:[link.source,link.target],related:[]}, link.target.sha));
      }
      offset += 30; more.hidden = offset >= group.length;
    }
    more.addEventListener("click", appendLinks); appendLinks();
    details.append(summary, list, more); card.append(nodes, description, details); container.append(card);
  }
}

async function loadExplanation(id, current) {
  const epoch = explanationEpoch;
  try {
    const response = await api(route(`audits/${id}/explain`));
    if (current !== context || epoch !== explanationEpoch || !response.provider) return;
    $("github-ai-panel").hidden = false;
    $("github-ai-disclosure").textContent = response.provider.disclosure;
    const explanation = response.explanation;
    const button = $("github-explain");
    button.disabled = !response.provider.available || ["queued", "running", "complete"].includes(explanation?.state);
    button.hidden = explanation?.state === "complete";
    button.textContent = explanation?.state === "failed" ? "Retry AI review" : "Generate AI review";
    $("github-ai-status").textContent = explanation?.detail || (response.provider.available
      ? "Get a short list of the most useful checks and what to verify next."
      : "Model provider unavailable. Use the findings below for the saved check results.");
    if (explanation?.state === "queued" || explanation?.state === "running") {
      explanationTimer = setTimeout(() => loadExplanation(id, current), 700); return;
    }
    const output = $("github-ai-results"); output.replaceChildren();
    if (explanation?.state !== "complete") return;
    for (const note of Object.values(explanation.sections).flat()) reviewNotes.set(note.source_id, note);
    if (selectedReview) renderFindingReport(selectedReview);
    for (const [key, title] of [["what_changed", "Changes worth checking"], ["what_to_review", "Follow-up checks"], ["what_could_not_be_checked", "What limited this review"]]) {
      const items = explanation.sections[key];
      if (!items?.length) continue;
      const section = document.createElement("section");
      const heading = document.createElement("h3");
      heading.textContent = title;
      section.append(heading);
      for (const item of items) {
        const article = document.createElement("article");
        const name = document.createElement("h4");
        name.textContent = item.summary;
        article.append(name);
        appendReviewNote(article, item);
        if (item.evidence.length) {
          const list = document.createElement("ul");
          list.className = "evidence-list";
          for (const e of item.evidence) row(list, e.path, `${e.sha.slice(0, 8)} · ${e.locator}`,
            () => showPreview({ path: e.path }, null, { evidence: item.evidence, related: [] }, e.sha));
          article.append(list);
        }
        section.append(article);
      }
      output.append(section);
    }
  } catch (error) {
    if (current === context && epoch === explanationEpoch) $("github-ai-status").textContent = error.message;
  }
}

async function requestExplanation() {
  const id = workspaceView?.audit?.id;
  if (!id) return;
  const current = context;
  const epoch = explanationEpoch;
  $("github-explain").disabled = true;
  $("github-ai-status").textContent = "Preparing the AI review…";
  try {
    await api(route(`audits/${id}/explain`), {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({consent:true})});
    if (current === context && epoch === explanationEpoch) await loadExplanation(id, current);
  } catch (error) {
    if (current === context && epoch === explanationEpoch) { $("github-ai-status").textContent = error.message; $("github-explain").disabled = false; }
  }
}
