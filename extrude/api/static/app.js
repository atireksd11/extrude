const EXAMPLES = [
  { label: "Simple cube", text: "Make a 20mm cube in OpenSCAD" },
  { label: "Laser mount plate", text: "Laser-cut an 80x60 mm acrylic mounting plate with 4 M3 clearance holes inset 10 mm from each corner." },
  { label: "Robotic arm", text: "Build a desktop robotic arm in OpenSCAD with 3 links and a gripper. PETG base with 4 M3 inserts. 2mm joint walls." },
  { label: "Voltage divider", text: "10k/10k divider 5 V to 3.3 V" },
  { label: "Buck converter", text: "5V to 3.3V buck 2A" },
];

const promptEl = document.getElementById("prompt");
const artifactEl = document.getElementById("artifact");
const filamentEl = document.getElementById("filament");
const offlineEl = document.getElementById("offline");
const runBtn = document.getElementById("run");
const toolsEl = document.getElementById("tools");
const examplesEl = document.getElementById("examples");
const metaEl = document.getElementById("meta");
const emptyEl = document.getElementById("empty");
const resultsEl = document.getElementById("results");
const noticeEl = document.getElementById("notice");
const loadingEl = document.getElementById("loading");
let ignoredSentence = false;

function scoreClass(percent) {
  if (percent == null) return "";
  if (percent >= 85) return "good";
  if (percent >= 50) return "mid";
  return "bad";
}

function formatScore(lane) {
  if (lane.percent == null) return "—";
  const ratio = lane.out_of ? ` · ${lane.passed}/${lane.out_of}` : "";
  return `${lane.percent}%${ratio}`;
}

function renderTools(tools) {
  toolsEl.replaceChildren();
  for (const [name, ok] of Object.entries(tools || {})) {
    const row = document.createElement("div");
    row.className = "tool-row";
    const label = document.createElement("span"); label.textContent = name;
    const dot = document.createElement("span"); dot.className = `dot ${ok ? "ok" : "off"}`; dot.title = ok ? "ready" : "missing";
    row.append(label, dot);
    toolsEl.appendChild(row);
  }
}

function renderExamples() {
  examplesEl.innerHTML = "";
  for (const item of EXAMPLES) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "example-btn";
    btn.textContent = item.label;
    btn.addEventListener("click", () => {
      promptEl.value = item.text;
      artifactEl.value = "";
    });
    examplesEl.appendChild(btn);
  }
}

function setPreview(panel, lane) {
  const box = panel.querySelector(".preview-box");
  const media = panel.querySelector(".preview-media");
  const placeholder = panel.querySelector(".preview-placeholder");
  media.innerHTML = "";
  box.classList.remove("has-preview");

  const url = lane.preview_url || lane.svg_url;
  if (!url) {
    placeholder.style.display = "flex";
    placeholder.textContent = lane.detail || "No render — OpenSCAD may be missing or compile failed.";
    return;
  }

  const bust = `${url}${url.includes("?") ? "&" : "?"}t=${Date.now()}`;
  if (lane.preview_url) {
    const img = document.createElement("img");
    img.alt = "OpenSCAD render";
    img.src = bust;
    img.onload = () => {
      box.classList.add("has-preview");
      placeholder.style.display = "none";
    };
    img.onerror = () => {
      placeholder.style.display = "flex";
      placeholder.textContent = `Render failed to load: ${url}`;
    };
    media.appendChild(img);
  } else {
    const img = document.createElement("img");
    img.alt = "SVG profile";
    img.src = bust;
    img.onload = () => {
      box.classList.add("has-preview");
      placeholder.style.display = "none";
    };
    img.onerror = () => {
      placeholder.style.display = "flex";
      placeholder.textContent = `SVG failed to load: ${url}`;
    };
    media.appendChild(img);
  }
}

function renderLane(panel, lane) {
  const ring = panel.querySelector(".score-ring");
  ring.textContent = formatScore(lane);
  ring.className = `score-ring ${scoreClass(lane.percent)}`;
  panel.querySelector(".lane-status").textContent = lane.status || "";

  setPreview(panel, lane);

  const checkList = panel.querySelector(".check-list");
  checkList.innerHTML = "";
  const checks = lane.checks || [];
  if (!checks.length) {
    checkList.innerHTML = "<li class='muted-line'>No verifier checks ran for this lane.</li>";
  }
  for (const row of checks) {
    const li = document.createElement("li");
    const icon = document.createElement("span");
    icon.className = `check-icon ${row.passed == null ? "unverified" : row.passed ? "pass" : "fail"}`;
    icon.textContent = row.passed == null ? "?" : row.passed ? "✓" : "✕";
    const body = document.createElement("div");
    const name = document.createElement("div"); name.className = "check-name"; name.textContent = row.id;
    body.append(name);
    if (row.detail) { const detail = document.createElement("div"); detail.className = "check-detail"; detail.textContent = row.detail; body.append(detail); }
    li.append(icon, body);
    checkList.appendChild(li);
  }

  const missesEl = panel.querySelector(".misses-list");
  missesEl.innerHTML = "";
  for (const miss of lane.misses || []) {
    const li = document.createElement("li");
    li.textContent = miss.detail || miss.check_id || JSON.stringify(miss);
    missesEl.appendChild(li);
  }
  panel.querySelector(".misses-block").style.display = (lane.misses || []).length ? "block" : "none";

  const codeEl = panel.querySelector(".code-block");
  const output = lane.code || lane.netlist || "";
  codeEl.textContent = output || lane.detail || "(no output yet)";
}

function bindTabs(panel) {
  const tabs = panel.querySelectorAll(".tab");
  const checksPane = panel.querySelector(".pane-checks");
  const codePane = panel.querySelector(".pane-code");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      const view = tab.dataset.view;
      checksPane.style.display = view === "checks" ? "block" : "none";
      codePane.style.display = view === "code" ? "block" : "none";
    });
  });
}

function renderResults(data) {
  emptyEl.style.display = "none";
  resultsEl.style.display = "grid";

  const noticeParts = [];
  if (ignoredSentence) {
    noticeParts.push("The second box was a sentence, not code, so it was not audited. The design used the main prompt.");
  }
  if (data.notice) noticeParts.push(data.notice);
  if (data.question) noticeParts.push(data.question);
  if (data.harness_edited && !data.notice) {
    noticeParts.push("Left is the first sample. Right is the harness output.");
  }
  if (data.missing_tools?.length) {
    noticeParts.push(`Missing tools: ${data.missing_tools.join(", ")}`);
  }
  noticeEl.textContent = noticeParts.join(" · ");
  noticeEl.style.display = noticeParts.length ? "block" : "none";

  const chip = (value, extra = "") => { const node = document.createElement("span"); node.className = `chip ${extra}`; node.textContent = value; return node; };
  metaEl.replaceChildren(chip(`${data.domain} · ${data.task_class}`, "accent"), chip(data.mode),
    chip(data.status, ["checked", "stopped", "needs_info"].includes(data.status) ? `status-${data.status}` : ""));
  if (data.lift_points != null) metaEl.append(chip(`${data.lift_points > 0 ? "+" : ""}${data.lift_points} pt lift`, data.lift_points > 0 ? "lift-positive" : ""));
  metaEl.append(chip(`${(data.seconds ?? 0).toFixed(1)}s`));
  if (data.cost_usd) metaEl.append(chip(`$${data.cost_usd.toFixed(4)}`));

  renderLane(document.getElementById("panel-raw"), data.raw);
  renderLane(document.getElementById("panel-harness"), data.harness);
}

async function loadStatus() {
  try {
    const res = await fetch("/v1/status");
    const data = await res.json();
    renderTools(data.tools);
    const model = document.createElement("div");
    model.className = "tool-row";
    const label = document.createElement("span"); label.textContent = data.model || "model";
    const dot = document.createElement("span"); dot.className = `dot ${data.model_configured ? "ok" : "off"}`; dot.title = data.model_configured ? "key loaded" : "no key";
    model.append(label, dot);
    toolsEl.prepend(model);
  } catch {
    toolsEl.innerHTML = "<span class='chip'>API offline</span>";
  }
}

function looksLikeSource(text) {
  const lowered = text.toLowerCase();
  if (lowered.includes("(export") || lowered.trim().startsWith("(kicad")) return true;
  return ["cube(", "sphere(", "cylinder(", "square(", "circle(", "difference(", "union(", "module ", "polygon(", "hull("]
    .some((marker) => lowered.includes(marker));
}

async function runCompare() {
  const sentence = promptEl.value.trim();
  const artifact = artifactEl.value.trim();
  if (!sentence && !artifact) {
    noticeEl.textContent = "Type a design prompt first.";
    noticeEl.style.display = "block";
    return;
  }

  runBtn.disabled = true;
  runBtn.textContent = "Working…";
  noticeEl.style.display = "none";
  resultsEl.style.display = "none";
  emptyEl.style.display = "none";
  loadingEl.hidden = false;
  document.getElementById("loading-detail").textContent = offlineEl.checked
    ? "Building the local sample, running engineering checks, and rendering the preview."
    : "Generating a draft, running engineering checks, and rendering the preview.";

  ignoredSentence = Boolean(artifact && sentence && artifact !== sentence && !looksLikeSource(artifact));
  const body = {
    text: sentence || artifact,
    filament: filamentEl.value,
    offline: offlineEl.checked,
  };
  if (artifact && looksLikeSource(artifact)) {
    body.artifact = artifact;
    body.filename = artifact.toLowerCase().includes("(export") ? "board.net" : "part.scad";
  }

  try {
    const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 90000);
  let res;
  try {
    res = await fetch("/v1/compare", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (err) {
    if (err.name === "AbortError") {
      throw new Error("The comparison took longer than 90 seconds. Try a smaller design or check that the required tools are available.");
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
    if (!res.ok) {
      let detail = `Server error ${res.status}`;
      try { const problem = await res.json(); detail = typeof problem.detail === "string" ? problem.detail : detail; } catch { /* Keep the status code. */ }
      throw new Error(detail);
    }
    const data = await res.json();
    loadingEl.hidden = true;
    emptyEl.style.display = "none";
    renderResults(data);
  } catch (err) {
    loadingEl.hidden = true;
    noticeEl.textContent = String(err);
    noticeEl.style.display = "block";
    emptyEl.style.display = "block";
    emptyEl.innerHTML = "<h3>Compare stopped</h3><p>Read the message above, adjust the prompt or tool settings, and try again.</p>";
  } finally {
    runBtn.disabled = false;
    runBtn.textContent = "Generate & Compare";
  }
}

document.getElementById("form").addEventListener("submit", (e) => {
  e.preventDefault();
  runCompare();
});

renderExamples();
loadStatus();
