const kinds = ["firmware", "schematic", "pcb", "cad", "docs"];
const positions = { firmware: [112, 112], schematic: [365, 80], pcb: [365, 300], cad: [610, 116], docs: [610, 350] };
const labels = { firmware: "Firmware", schematic: "Schematic", pcb: "PCB", cad: "CAD", docs: "Documents" };
const $ = (id) => document.getElementById(id);
const ns = "http://www.w3.org/2000/svg";
const state = { selected: null, scanning: false, latest: null, activeKind: null, selectedFile: null,
  selectedFileModified: null, optionsKey: null, mesh: null, viewerObserver: null, viewerFrame: null, review: null, pendingScan: false };

function el(tag, className = "", text = null) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== null) node.textContent = text;
  return node;
}
function empty(target, message) { target.replaceChildren(el("p", "empty", message)); }
function formatBytes(bytes) { return bytes < 1024 ? `${bytes} B` : bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1048576).toFixed(1)} MB`; }
function formatTime(value) { return new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }); }
function relativeTime(value) {
  const seconds = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  return formatTime(value);
}
async function api(path, options = {}) {
  const response = await fetch(path, options);
  let body;
  try { body = await response.json(); } catch { body = null; }
  if (!response.ok) throw new Error(body?.detail || `Request failed (${response.status})`);
  return body;
}
function setMonitor(message, detail = "") {
  $("monitor-state").textContent = message;
  $("monitor-detail").textContent = detail;
}
function svg(tag, attributes) {
  const node = document.createElementNS(ns, tag);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  return node;
}

function renderGraph(data) {
  const graph = $("graph");
  graph.replaceChildren();
  const active = new Set(data.files.map((file) => file.kind));
  if (data.project.onshape_url) active.add("cad");
  const visible = kinds.filter((kind) => active.has(kind));
  if (!visible.length) {
    const message = svg("text", { x: 380, y: 210, "text-anchor": "middle", class: "graph-empty" });
    message.textContent = "No supported design files found yet";
    graph.append(message);
    return;
  }
  const mobile = window.innerWidth <= 560;
  const points = mobile
    ? Object.fromEntries(visible.map((kind, index) => [kind, [180, 72 + index * 154]]))
    : visible.length === 1 ? { ...positions, [visible[0]]: [380, 210] } : positions;
  graph.setAttribute("viewBox", mobile ? `0 0 360 ${Math.max(190, visible.length * 154 + 20)}` : "0 0 760 500");
  for (const link of data.relationships || []) {
    if (!active.has(link.from) || !active.has(link.to)) continue;
    const [x1, y1] = points[link.from];
    const [x2, y2] = points[link.to];
    const bend = mobile ? 0 : Math.min(80, Math.abs(x2 - x1) * .35);
    const path = svg("path", {
      d: `M ${x1} ${y1} C ${x1 + (x2 >= x1 ? bend : -bend)} ${y1}, ${x2 - (x2 >= x1 ? bend : -bend)} ${y2}, ${x2} ${y2}`,
      class: `edge ${link.confidence}`,
    });
    graph.append(path);
  }
  const recent = new Set(data.changes.slice(0, 8).map((change) => change.path));
  const failed = new Set(data.checks.filter((check) => check.status === "failed").map((check) => check.file));
  for (const kind of visible) {
    const [x, y] = points[kind];
    const files = data.files.filter((file) => file.kind === kind).sort((a, b) => Number(recent.has(b.path)) - Number(recent.has(a.path)) || a.path.localeCompare(b.path));
    const changed = files.some((file) => recent.has(file.path));
    const group = svg("g", { class: `graph-node ${changed ? "recent" : ""} ${state.activeKind === kind ? "selected" : ""}`, role: "button", tabindex: "0", "aria-label": `Filter to ${labels[kind]}` });
    group.dataset.kind = kind;
    group.append(svg("rect", { x: x - 86, y: y - 39, width: 172, height: 78, rx: 10, class: "node" }));
    group.append(svg("rect", { x: x - 86, y: y - 39, width: 4, height: 78, rx: 2, class: "node-rail" }));
    const tag = svg("text", { x: x - 68, y: y - 15, class: "node-tag" }); tag.textContent = `${String(kinds.indexOf(kind) + 1).padStart(2, "0")} / AREA`;
    const label = svg("text", { x: x - 68, y: y + 7, class: "node-label" }); label.textContent = labels[kind];
    const count = svg("text", { x: x - 68, y: y + 27, class: "node-count" });
    count.textContent = files.length ? `${files.length} file${files.length === 1 ? "" : "s"}` : "Onshape link";
    group.append(tag, label, count);
    group.addEventListener("click", () => selectKind(kind));
    group.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectKind(kind); } });
    graph.append(group);
    for (const [index, file] of files.slice(0, 2).entries()) {
      const fileY = y + 50 + index * 31;
      const fileGroup = svg("g", { class: `graph-file ${recent.has(file.path) ? "recent" : ""} ${failed.has(file.path) ? "failed" : ""} ${state.selectedFile === file.path ? "selected" : ""}`, role: "button", tabindex: "0", "aria-label": `Inspect ${file.path}` });
      fileGroup.append(svg("rect", { x: x - 86, y: fileY - 13, width: 172, height: 27, rx: 6, class: "file-node" }));
      fileGroup.append(svg("circle", { cx: x - 71, cy: fileY, r: 3, class: "file-node-mark" }));
      const name = svg("text", { x: x - 61, y: fileY + 4, class: "file-node-label" });
      const base = file.path.split("/").at(-1);
      name.textContent = base.length > 20 ? `${base.slice(0, 17)}…` : base;
      const title = svg("title", {}); title.textContent = file.path;
      fileGroup.append(name, title);
      fileGroup.addEventListener("click", () => { state.activeKind = kind; inspectFile(file.path).then(() => $("file-inspector").scrollIntoView({ behavior: "smooth", block: "center" })); });
      fileGroup.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); fileGroup.dispatchEvent(new MouseEvent("click")); } });
      graph.append(fileGroup);
    }
    if (files.length > 2) {
      const more = svg("text", { x: x - 76, y: y + 121, class: "node-more" });
      more.textContent = `+ ${files.length - 2} more in the file browser`;
      graph.append(more);
    }
  }
}
function selectKind(kind) {
  state.activeKind = state.activeKind === kind ? null : kind;
  if (state.latest) { renderGraph(state.latest); renderAreaDetails(state.latest); renderFileList(state.latest); }
}
function renderAreaDetails(data) {
  const target = $("area-details");
  target.replaceChildren();
  const kind = state.activeKind;
  if (!kind) {
    target.append(el("span", "area-bullet", "↗"), el("p", "", "Select an area to filter the project, or select a file to open its preview."));
    return;
  }
  const files = data.files.filter((file) => file.kind === kind);
  const links = (data.relationships || []).filter((link) => link.from === kind || link.to === kind);
  const heading = el("div", "area-heading");
  heading.append(el("strong", "", labels[kind]), el("span", "", `${files.length} files · ${links.length} connections`));
  const clear = el("button", "area-clear", "Show all areas ×"); clear.type = "button"; clear.addEventListener("click", () => selectKind(kind));
  target.append(heading, clear);
  const details = el("p", "", links.some((link) => link.confidence === "configured")
    ? "A pin relationship is configured here. Other lines indicate review paths, not verified dependencies."
    : "Connections indicate possible design dependencies. Configure a pin check below to verify one.");
  target.append(details);
}
function createBadge(status) { return el("span", `badge ${status}`, status); }
function feedItem(title, status, detail, suggestion, onInspect = null, onReview = null) {
  const box = el("article", "item");
  if (status) box.append(createBadge(status));
  box.append(el("strong", "", title));
  if (detail) box.append(el("p", "", detail));
  if (suggestion) box.append(el("p", "suggestion", `Next step: ${suggestion}`));
  if (onInspect) { const button = el("button", "item-action", "Inspect source ↗"); button.type = "button"; button.addEventListener("click", onInspect); box.append(button); }
  if (onReview) { const button = el("button", "item-action review-action", "Investigate impact ↗"); button.type = "button"; button.addEventListener("click", onReview); box.append(button); }
  return box;
}
function openReview(impact) {
  state.review = impact;
  const dialog = $("review-dialog");
  $("review-heading").textContent = impact.status === "failed" ? "Verified mismatch" : "Investigate possible impact";
  $("review-context").replaceChildren(createBadge(impact.status), el("strong", "", `${impact.source} → ${labels[impact.target] || impact.target}`), el("p", "", impact.detail));
  $("review-source-title").textContent = impact.source;
  const change = state.latest.changes.find((item) => item.path === impact.source);
  $("review-diff").textContent = change?.diff || "A text diff is unavailable. Open the source file to inspect its current contents.";
  const options = state.latest.files.filter((file) => file.kind === impact.target);
  const select = $("review-target"); select.replaceChildren();
  for (const file of options) { const option = el("option", "", file.path); option.value = file.path; select.append(option); }
  select.disabled = !options.length;
  const checks = state.latest.checks.filter((check) => check.file === impact.source || options.some((file) => file.path === check.file));
  $("review-checks").replaceChildren(el("strong", "", "Available engineering checks"));
  if (checks.length) for (const check of checks) {
    const row = el("div", "review-check-row"); row.append(createBadge(check.status), el("span", "", `${check.name} · ${check.detail}`)); $("review-checks").append(row);
  } else $("review-checks").append(el("p", "", "No automated check covers this relationship yet. Compare the files and record your conclusion."));
  $("review-note").value = ""; $("review-error").textContent = "";
  const verified = impact.status === "failed";
  $("review-done").hidden = verified; $("review-irrelevant").hidden = verified;
  $("review-guidance").textContent = verified ? "Fix the mismatch in your project files. Atlas will clear this when the check passes." : "Your decision is saved in the review log.";
  if (!dialog.open) dialog.showModal();
  loadReviewTarget();
}
async function loadReviewTarget() {
  const path = $("review-target").value;
  const target = $("review-target-preview");
  if (!path) { empty(target, "No file is available in this area. The relationship is unverified."); return; }
  empty(target, "Loading file preview…");
  try {
    const data = await api(`/v1/projects/${state.selected}/preview?path=${encodeURIComponent(path)}`);
    if (!state.review || $("review-target").value !== path) return;
    target.replaceChildren();
    if (data.type === "text") {
      target.append(el("pre", "review-code", data.text.slice(0, 8000) || "This file is empty."));
      if (data.truncated || data.text.length > 8000) target.append(el("small", "", "Showing the first part of this file."));
    } else target.append(el("p", "", data.type === "mesh" ? `${data.mesh.total_triangles} triangles · ${data.mesh.dimensions.join(" × ")} file units. Open the file browser to rotate it.` : data.note));
    const open = el("button", "review-open-file", "Open full file preview ↗"); open.type = "button";
    open.addEventListener("click", async () => { $("review-dialog").close(); state.review = null; state.activeKind = null; await inspectFile(path); $("file-inspector").scrollIntoView({ behavior: "smooth", block: "center" }); });
    target.append(open);
  } catch (error) { empty(target, error.message); }
}
async function submitReview(outcome) {
  if (!state.review) return;
  const id = state.review.id;
  $("review-error").textContent = "";
  for (const button of [$("review-done"), $("review-irrelevant")]) button.disabled = true;
  try {
    const result = await api(`/v1/projects/${state.selected}/findings/${id}/review`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ outcome, note: $("review-note").value, target_file: $("review-target").value || null }),
    });
    $("review-dialog").close(); state.review = null; render(result);
  } catch (error) { $("review-error").textContent = error.message; }
  finally { for (const button of [$("review-done"), $("review-irrelevant")]) button.disabled = false; }
}
function renderReviewHistory(data) {
  const target = $("review-history"); target.replaceChildren();
  if (!data.review_history?.length) { empty(target, "No decisions yet. Investigate a possible effect to start the project memory."); return; }
  for (const entry of data.review_history.slice(0, 8)) {
    const row = el("article", "review-history-row");
    const heading = el("div", ""); heading.append(createBadge(entry.review_outcome === "not_relevant" ? "not relevant" : "reviewed"), el("strong", "", `${entry.source} → ${entry.review_target || labels[entry.target] || entry.target}`), el("time", "", relativeTime(entry.resolved_at)));
    row.append(heading);
    if (entry.review_note) row.append(el("p", "", entry.review_note));
    target.append(row);
  }
}
function renderFeeds(data) {
  const impacts = $("impacts"); impacts.replaceChildren();
  if (!data.impacts.length) empty(impacts, "Nothing needs review. Saved changes will appear here.");
  for (const impact of data.impacts) impacts.append(feedItem(`${impact.source} → ${labels[impact.target] || impact.target}`, impact.status,
    impact.detail, impact.suggestion, () => inspectFile(impact.source), () => openReview(impact)));
  const checks = $("checks"); checks.replaceChildren();
  if (!data.checks.length) empty(checks, "No checks available. Add a KiCad netlist or configure a pin relationship.");
  for (const check of data.checks) checks.append(feedItem(check.name, check.status, `${check.file} · ${check.detail}`, null,
    data.files.some((file) => file.path === check.file) ? () => inspectFile(check.file) : null));
  const changes = $("changes"); changes.replaceChildren();
  if (!data.changes.length) empty(changes, "Baseline captured. Make a change to see its history here.");
  for (const change of data.changes) {
    const box = el("details", "change-entry");
    const summary = el("summary", "");
    summary.append(el("span", `change-action ${change.action}`, change.action), el("strong", "", change.path), el("time", "", relativeTime(change.seen_at)));
    box.append(summary);
    if (change.diff) box.append(el("pre", "diff-preview", change.diff));
    else box.append(el("p", "no-diff", "A text diff is unavailable for this file type or earlier history."));
    changes.append(box);
  }
}
function renderFileList(data) {
  const term = $("file-search").value.trim().toLowerCase();
  const rows = data.files.filter((file) => (!state.activeKind || file.kind === state.activeKind) && file.path.toLowerCase().includes(term));
  const files = $("files"); files.replaceChildren();
  $("file-filter-note").textContent = state.activeKind ? `${labels[state.activeKind].toUpperCase()} · ${rows.length}` : `ALL AREAS · ${rows.length}`;
  if (!rows.length) { empty(files, "No files match this view."); return; }
  for (const file of rows) {
    const button = el("button", `file-row ${state.selectedFile === file.path ? "active" : ""}`);
    button.type = "button";
    const icon = el("span", "file-icon", file.kind === "cad" ? "⬡" : file.kind === "pcb" ? "▦" : file.kind === "schematic" ? "⌁" : file.kind === "firmware" ? "⌘" : "≡");
    const title = el("span", "file-title"); title.append(el("strong", "", file.path), el("small", "", `${labels[file.kind]} · ${formatBytes(file.size)}`));
    button.append(icon, title, el("span", "file-arrow", "↗"));
    button.addEventListener("click", () => inspectFile(file.path));
    files.append(button);
  }
}
function renderPinRules(data) {
  const list = $("pin-rules"); list.replaceChildren();
  if (!data.pin_rules.length) empty(list, "No pin relationships configured yet.");
  for (const rule of data.pin_rules) {
    const row = el("div", "rule-row");
    const text = el("div", ""); text.append(el("strong", "", `${rule.firmware_symbol} ↔ ${rule.schematic_net}`),
      el("small", "", `${rule.firmware_file} → ${rule.netlist_file} · ${rule.mcu_ref}`));
    const button = el("button", "rule-remove", "×"); button.type = "button"; button.setAttribute("aria-label", `Remove pin check ${rule.firmware_symbol}`);
    button.addEventListener("click", async () => {
      button.disabled = true;
      try { render(await api(`/v1/projects/${state.selected}/pin-rules/${rule.id}`, { method: "DELETE" })); }
      catch (error) { $("rule-error").textContent = error.message; button.disabled = false; }
    });
    row.append(text, button); list.append(row);
  }
  const firmware = data.files.filter((file) => file.kind === "firmware").map((file) => file.path);
  const netlists = data.files.filter((file) => file.path.toLowerCase().endsWith(".net")).map((file) => file.path);
  const key = JSON.stringify([firmware, netlists]);
  if (key !== state.optionsKey) {
    state.optionsKey = key;
    for (const [name, paths] of [["firmware_file", firmware], ["netlist_file", netlists]]) {
      const select = $("pin-rule-form").elements.namedItem(name); select.replaceChildren();
      for (const path of paths) { const option = el("option", "", path); option.value = path; select.append(option); }
      select.disabled = !paths.length;
    }
  }
  $("pin-rule-form").querySelector("button[type=submit]").disabled = !firmware.length || !netlists.length;
}
function render(data) {
  const previous = state.latest;
  state.latest = data; state.selected = data.project.id;
  $("workspace").hidden = false; $("welcome").hidden = true;
  $("project-name").textContent = data.project.name;
  const meta = $("project-meta"); meta.replaceChildren(document.createTextNode(`${data.project.path} · Git ${data.git_head?.slice(0, 8) || "not connected"}`));
  if (data.project.onshape_url) { const link = el("a", "", " · Open Onshape ↗"); link.href = data.project.onshape_url; link.target = "_blank"; link.rel = "noopener noreferrer"; meta.append(link); }
  $("demo-change").hidden = !data.project.demo;
  $("export-handoff").href = `/v1/projects/${data.project.id}/handoff.md`;
  $("metric-files").textContent = data.files.length;
  $("metric-changes").textContent = data.changes.length;
  $("metric-checks").textContent = data.checks.filter((check) => check.status === "passed").length;
  const failed = data.checks.filter((check) => check.status === "failed").length;
  $("monitor-state").closest(".activity-strip").classList.toggle("attention", Boolean(failed));
  $("metric-sync").textContent = failed ? `${failed} to review` : "Up to date";
  $("metric-scan-time").textContent = `Scanned ${new Date(data.scanned_at).toLocaleTimeString()}`;
  $("file-count-note").textContent = `${data.files.length} FILES`;
  $("coverage-detail").textContent = data.skipped.length ? `${data.files.length} tracked · ${data.skipped.length} skipped` : `${data.files.length} files tracked`;
  setMonitor(failed ? "Attention needed" : "Monitoring project", failed ? `${failed} verified check${failed === 1 ? "" : "s"} failed.` : "Saved changes are checked every five seconds.");
  const next = [...data.impacts].sort((a, b) => Number(b.status === "failed") - Number(a.status === "failed"))[0];
  $("review-next").hidden = !next;
  $("review-next").dataset.finding = next?.id || "";
  $("next-title").textContent = next ? next.status === "failed" ? "A verified mismatch needs a fix" : "A change needs your judgement" : "All caught up";
  $("next-detail").textContent = next ? `${next.source} may affect ${labels[next.target] || next.target}. Open the review to see the file change and available checks.` : "No active findings. Atlas will watch for saved file changes.";
  $("next-title").closest(".next-action").classList.toggle("has-finding", Boolean(next));
  const skipped = $("skipped-note"); skipped.hidden = !data.skipped.length;
  skipped.textContent = data.skipped.length ? `${data.skipped.length} file${data.skipped.length === 1 ? "" : "s"} skipped: ${data.skipped.slice(0, 3).map((entry) => `${entry.path} (${entry.reason})`).join(", ")}` : "";
  renderGraph(data); renderAreaDetails(data); renderFeeds(data); renderFileList(data); renderPinRules(data); renderReviewHistory(data);
  if (state.selectedFile) {
    const current = data.files.find((file) => file.path === state.selectedFile);
    const old = previous?.files.find((file) => file.path === state.selectedFile);
    if (!current) { state.selectedFile = null; state.selectedFileModified = null; renderInspectorEmpty(); }
    else if (old && old.modified_ns !== current.modified_ns) inspectFile(current.path);
  }
}
function renderInspectorEmpty() {
  $("file-inspector").replaceChildren();
  const box = el("div", "inspector-empty"); box.append(el("span", "", "↗"), el("strong", "", "Select a file to inspect"),
    el("p", "", "Read source previews and rotate STL or OBJ models right here."));
  $("file-inspector").append(box);
}
async function inspectFile(path) {
  const file = state.latest?.files.find((entry) => entry.path === path);
  if (!file) return;
  state.selectedFile = path;
  state.selectedFileModified = file.modified_ns;
  renderFileList(state.latest);
  renderGraph(state.latest);
  renderAreaDetails(state.latest);
  const inspector = $("file-inspector"); empty(inspector, "Loading preview…");
  state.viewerObserver?.disconnect(); state.viewerObserver = null;
  if (state.viewerFrame) cancelAnimationFrame(state.viewerFrame);
  state.viewerFrame = null;
  try {
    const data = await api(`/v1/projects/${state.selected}/preview?path=${encodeURIComponent(path)}`);
    if (state.selectedFile !== path) return;
    inspector.replaceChildren();
    const head = el("div", "inspector-head");
    const name = el("div", ""); name.append(el("span", "section-number", `${labels[data.kind].toUpperCase()} / FILE PREVIEW`), el("h3", "", data.path));
    const copy = el("button", "copy-path", "Copy path ↗"); copy.type = "button";
    copy.addEventListener("click", async () => { try { await navigator.clipboard.writeText(`${state.latest.project.path}/${data.path}`); copy.textContent = "Copied ✓"; } catch { copy.textContent = "Copy unavailable"; } });
    head.append(name, copy); inspector.append(head);
    inspector.append(el("p", "file-meta", `${formatBytes(data.size)} · Modified ${new Date(data.modified_ns / 1e6).toLocaleString()}`));
    if (data.type === "mesh") renderMesh(inspector, data.mesh);
    else if (data.type === "text") {
      inspector.append(el("pre", "code-preview", data.text || "This file is empty."));
      if (data.truncated) inspector.append(el("p", "preview-note", "Preview truncated at 100 KB."));
    } else inspector.append(el("p", "preview-note", data.note));
  } catch (error) { empty(inspector, error.message); }
}

function renderMesh(inspector, mesh) {
  state.viewerObserver?.disconnect();
  if (state.viewerFrame) cancelAnimationFrame(state.viewerFrame);
  const wrap = el("div", "mesh-wrap");
  const canvas = el("canvas", "mesh-canvas"); canvas.setAttribute("aria-label", "Interactive 3D model. Drag to rotate and scroll to zoom.");
  wrap.append(canvas, el("span", "mesh-hint", "DRAG TO ORBIT · SCROLL TO ZOOM")); inspector.append(wrap);
  const info = el("div", "mesh-info");
  info.append(el("span", "", `${mesh.total_triangles.toLocaleString()} triangles`),
    el("span", "", `${mesh.dimensions.join(" × ")} ${mesh.unit}`));
  const reset = el("button", "", "Reset view ↺"); reset.type = "button"; info.append(reset); inspector.append(info);
  const view = { yaw: -.55, pitch: -.36, zoom: 1, dragging: false, lastX: 0, lastY: 0, lastFrame: 0 };
  const center = mesh.bounds.map(([low, high]) => (low + high) / 2);
  const size = Math.max(...mesh.dimensions, 1);
  function draw() {
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(100, rect.width), height = Math.max(100, rect.height);
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
      canvas.width = Math.round(width * dpr); canvas.height = Math.round(height * dpr);
    }
    const ctx = canvas.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    const shadow = ctx.createRadialGradient(width / 2, height * .78, 4, width / 2, height * .78, width * .29);
    shadow.addColorStop(0, "rgba(15, 69, 62, .23)"); shadow.addColorStop(1, "rgba(15, 69, 62, 0)");
    ctx.fillStyle = shadow; ctx.fillRect(0, height * .48, width, height * .5);
    const scale = Math.min(width, height) / (size * 1.65) * view.zoom;
    const cy = Math.cos(view.yaw), sy = Math.sin(view.yaw), cp = Math.cos(view.pitch), sp = Math.sin(view.pitch);
    function transform(x, y, z) {
      x -= center[0]; y -= center[1]; z -= center[2];
      const rx = x * cy + z * sy, rz = -x * sy + z * cy;
      const ry = y * cp - rz * sp, depth = y * sp + rz * cp;
      return [width / 2 + rx * scale, height / 2 - ry * scale, depth, rx, ry];
    }
    const faces = mesh.triangles.map((triangle) => {
      const a = transform(...triangle.slice(0, 3)), b = transform(...triangle.slice(3, 6)), c = transform(...triangle.slice(6, 9));
      const ux = b[3] - a[3], uy = b[4] - a[4], uz = b[2] - a[2];
      const vx = c[3] - a[3], vy = c[4] - a[4], vz = c[2] - a[2];
      const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
      const length = Math.hypot(nx, ny, nz) || 1;
      const light = Math.abs((nx * -.36 + ny * .71 + nz * .61) / length);
      return { points: [a, b, c], depth: (a[2] + b[2] + c[2]) / 3, shade: light };
    }).sort((a, b) => a.depth - b.depth);
    for (const face of faces) {
      const [a, b, c] = face.points;
      ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.lineTo(c[0], c[1]); ctx.closePath();
      ctx.fillStyle = `hsl(174 56% ${Math.round(37 + face.shade * 26)}%)`; ctx.fill();
      ctx.strokeStyle = "rgba(15, 79, 71, .29)"; ctx.lineWidth = .55; ctx.stroke();
    }
  }
  canvas.addEventListener("pointerdown", (event) => { view.dragging = true; view.lastX = event.clientX; view.lastY = event.clientY; canvas.setPointerCapture(event.pointerId); });
  canvas.addEventListener("pointermove", (event) => { if (!view.dragging) return; view.yaw += (event.clientX - view.lastX) * .012; view.pitch = Math.max(-1.45, Math.min(1.45, view.pitch + (event.clientY - view.lastY) * .012)); view.lastX = event.clientX; view.lastY = event.clientY; draw(); });
  canvas.addEventListener("pointerup", () => { view.dragging = false; });
  canvas.addEventListener("wheel", (event) => { event.preventDefault(); view.zoom = Math.max(.55, Math.min(2.7, view.zoom * (event.deltaY > 0 ? .9 : 1.1))); draw(); }, { passive: false });
  reset.addEventListener("click", () => { view.yaw = -.55; view.pitch = -.36; view.zoom = 1; draw(); });
  state.viewerObserver = new ResizeObserver(draw); state.viewerObserver.observe(canvas);
  draw();
  if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    function animate(time) {
      if (!canvas.isConnected) return;
      if (!view.dragging && time - view.lastFrame > 32) {
        view.yaw += .0025;
        view.lastFrame = time;
        draw();
      }
      state.viewerFrame = requestAnimationFrame(animate);
    }
    state.viewerFrame = requestAnimationFrame(animate);
  }
}

async function scan() {
  if (!state.selected || !$("welcome").hidden) return;
  if (state.scanning) { state.pendingScan = true; return; }
  const projectId = state.selected;
  state.scanning = true; $("metric-sync").textContent = "Scanning…";
  try { const data = await api(`/v1/projects/${projectId}/scan`, { method: "POST" }); if (projectId === state.selected) render(data); }
  catch (error) { if (projectId === state.selected) { $("metric-sync").textContent = "Scan failed"; setMonitor("Scan failed", error.message); $("metric-scan-time").textContent = error.message; } }
  finally {
    state.scanning = false;
    if (state.pendingScan) { state.pendingScan = false; scan(); }
  }
}
async function refreshProjectList(preferredId = null) {
  const projects = await api("/v1/projects");
  const select = $("project-select"); select.replaceChildren();
  for (const project of projects) { const option = el("option", "", project.name); option.value = project.id; select.append(option); }
  if (projects.length) {
    state.selected = preferredId || state.selected || projects[0].id;
    if (!projects.some((project) => project.id === state.selected)) state.selected = projects[0].id;
    select.value = String(state.selected);
    return projects;
  }
  return [];
}
async function openProject(data) {
  await refreshProjectList(data.project.id);
  $("project-select").value = String(data.project.id);
  state.activeKind = null; state.selectedFile = null; state.selectedFileModified = null; state.optionsKey = null;
  $("file-search").value = "";
  renderInspectorEmpty(); render(data);
  const model = data.files.find((file) => /\.(stl|obj)$/i.test(file.path));
  if (model) inspectFile(model.path);
  window.scrollTo({ top: 0, behavior: "smooth" });
}
$("new-project").addEventListener("submit", async (event) => {
  event.preventDefault(); $("form-error").textContent = "";
  const button = event.target.querySelector("button[type=submit]"); button.disabled = true; button.textContent = "Connecting…";
  try {
    const data = await api("/v1/projects", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(Object.fromEntries(new FormData(event.target))) });
    await openProject(data); event.target.reset();
  } catch (error) { $("form-error").textContent = error.message; }
  finally { button.disabled = false; button.textContent = "Create project map ↗"; }
});
$("explore-demo").addEventListener("click", async (event) => {
  const button = event.currentTarget; button.disabled = true; button.textContent = "Opening demo…";
  try { await openProject(await api("/v1/projects/demo", { method: "POST" })); }
  catch (error) { $("form-error").textContent = error.message; }
  finally { button.disabled = false; button.textContent = "Explore a working demo ↗"; }
});
$("demo-change").addEventListener("click", async (event) => {
  const button = event.currentTarget; button.disabled = true; button.textContent = "Applying change…";
  try { render(await api(`/v1/projects/${state.selected}/demo-change`, { method: "POST" })); }
  catch (error) { setMonitor("Demo change failed", error.message); }
  finally { button.disabled = false; button.textContent = "Make a demo change ↗"; }
});
$("pin-rule-form").addEventListener("submit", async (event) => {
  event.preventDefault(); $("rule-error").textContent = "";
  const button = event.target.querySelector("button[type=submit]"); button.disabled = true;
  try {
    const data = await api(`/v1/projects/${state.selected}/pin-rules`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(Object.fromEntries(new FormData(event.target))) });
    event.target.reset(); render(data);
  } catch (error) { $("rule-error").textContent = error.message; }
  finally { button.disabled = false; }
});
$("file-search").addEventListener("input", () => { if (state.latest) renderFileList(state.latest); });
$("review-next").addEventListener("click", () => { const finding = state.latest?.impacts.find((item) => item.id === Number($("review-next").dataset.finding)); if (finding) openReview(finding); });
$("review-target").addEventListener("change", loadReviewTarget);
$("review-done").addEventListener("click", () => submitReview("reviewed"));
$("review-irrelevant").addEventListener("click", () => submitReview("not_relevant"));
$("review-close").addEventListener("click", () => $("review-dialog").close());
$("review-dialog").addEventListener("close", () => { state.review = null; });
$("project-select").addEventListener("change", () => { if ($("review-dialog").open) $("review-dialog").close(); state.selected = Number($("project-select").value); state.activeKind = null; state.selectedFile = null; state.optionsKey = null; $("file-search").value = ""; renderInspectorEmpty(); scan(); });
$("refresh").addEventListener("click", scan);
$("add-project").addEventListener("click", () => { $("workspace").hidden = true; $("welcome").hidden = false; window.scrollTo({ top: 0, behavior: "smooth" }); });
window.addEventListener("resize", () => { if (state.latest) renderGraph(state.latest); });
(async () => {
  try {
    const projects = await refreshProjectList();
    if (projects.length) {
      $("workspace").hidden = false; $("welcome").hidden = true; await scan();
      const model = state.latest?.files.find((file) => /\.(stl|obj)$/i.test(file.path));
      if (model) inspectFile(model.path);
    }
  } catch (error) { $("form-error").textContent = `Could not load projects: ${error.message}`; }
})();
setInterval(scan, 5000);
