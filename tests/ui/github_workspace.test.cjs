// Verify revision races and evidence routing without a browser or network.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

class Element {
  constructor(tag = "div") {
    this.tag = tag;
    this.children = [];
    this.dataset = {};
    this.hidden = false;
    this.attributes = {};
    this.listeners = {};
    this.textContent = "";
    this.value = "";
  }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = items; }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener(event, callback) { this.listeners[event] = callback; }
  querySelector(selector) {
    return this.children.find(child => child.tag === selector) || (() => {
      const child = new Element(selector);
      this.append(child);
      return child;
    })();
  }
  querySelectorAll() { return []; }
}

const html = fs.readFileSync("extrude/api/static/github.html", "utf8");
const nodes = new Map([...html.matchAll(/id="([^"]+)"/g)].map(match => [match[1], new Element()]));
const calls = [];
let respond = async () => [];
const sandbox = {
  document: {
    getElementById(id) { assert(nodes.has(id), `Missing HTML element ${id}`); return nodes.get(id); },
    createElement(tag) { return new Element(tag); },
  },
  Option: function(label, value) { const node = new Element("option"); node.textContent = label; node.value = value; return node; },
  URLSearchParams,
  window: { location: { search: "" }, history: { replaceState() {} } },
  setTimeout, clearTimeout,
  fetch: async (url, options) => {
    calls.push({ url, options });
    const body = await respond(url, options);
    return { ok: true, json: async () => body };
  },
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync("extrude/api/static/github.js", "utf8"), sandbox);
const execute = code => vm.runInContext(code, sandbox);
const head = "b".repeat(40);
const base = "a".repeat(40);
const page = sha => ({ head_sha: sha, base_sha: base, audit: null,
  inventory: { total: 1, next_offset: null, files: [{ path: "docs/setup.md", domain: "docs", kind: "docs" }] },
  changes: { total: 0, next_offset: null, files: [] } });

async function main() {
  await new Promise(resolve => setImmediate(resolve));
  execute(`repo = { id: "fixture", head: "${head}" }; revision = "${head}";`);
  let release;
  const delayed = new Promise(resolve => { release = resolve; });
  respond = async url => new URL(url, "http://local").searchParams.get("revision") === base ? delayed : page(head);
  const stale = execute(`selectRevision("${base}")`);
  await execute(`selectRevision("${head}")`);
  release(page(base));
  await stale;
  assert.equal(execute("revision"), head);
  assert.equal(execute("workspaceView.head_sha"), head);
  assert.equal(nodes.get("github-revision").textContent, `${base.slice(0, 8)} → ${head.slice(0, 8)}`);

  respond = async url => {
    const params = new URL(url, "http://local").searchParams;
    return { text: `${params.get("revision")}:${params.get("path")}` };
  };
  await execute(`showPreview({path:"docs/removed.md", status:"D"}, "${base}")`);
  assert.equal(nodes.get("github-before").querySelector("pre").textContent, `${base}:docs/removed.md`);
  assert.equal(nodes.get("github-after").textContent, "File was not present.");
  await execute(`showPreview({path:"docs/new.md", previous_path:"docs/old.md", status:"R"}, "${base}")`);
  assert.equal(nodes.get("github-before").querySelector("pre").textContent, `${base}:docs/old.md`);
  assert.equal(nodes.get("github-after").textContent, `${head}:docs/new.md`);
  await execute('showPreview({path:"docs/setup.md"}, null)');
  assert(nodes.get("github-before").hidden);
  assert.equal(nodes.get("github-after").textContent, `${head}:docs/setup.md`);

  let releasePreview;
  const slowPreview = new Promise(resolve => { releasePreview = resolve; });
  respond = url => new URL(url, "http://local").searchParams.get("path") === "slow.txt"
    ? slowPreview : { text: "Latest file" };
  const oldPreview = execute('showPreview({path:"slow.txt"}, null)');
  await execute('showPreview({path:"latest.txt"}, null)');
  releasePreview({ text: "Old file" });
  await oldPreview;
  assert.equal(nodes.get("github-after").textContent, "Latest file");
  assert.equal(nodes.get("github-file-name").textContent, "latest.txt");

  respond = async () => ({ state: "partial", findings: [], coverage: [
    { path: "firmware/main.ino", check: "File analysis", outcome: "unsupported", detail: "Adapter pending" },
  ] });
  await execute('showAudit("saved", context)');
  assert.equal(nodes.get("github-audit-run").textContent, "Retry audit");
  assert(!nodes.get("github-audit-coverage").hidden);
  assert.equal(nodes.get("github-audit-coverage").querySelector("ul").children.length, 1);
  assert.equal(execute("workspaceView.audit.state"), "partial");

  // Native findings use engineering lifecycle labels, not a fake before/after
  // placement string. The report remains readable when the checker has no
  // baseline, and resolved findings retain their source evidence.
  const nativeFinding = { rule_id: "kicad.drc.tracks_crossing", domain: "pcb", status: "verified",
    severity: "error", summary: "Tracks cross on F.Cu", lifecycle: "existing",
    evidence: [{ sha: base, path: "board.kicad_pcb", locator: "Track UUID 123" },
      { sha: head, path: "board.kicad_pcb", locator: "Track UUID 123" }], related: [] };
  respond = async () => ({ state: "partial", base_sha: base, head_sha: head,
    findings: [nativeFinding], coverage: [] });
  await execute('showAudit("native", context)');
  const nativeRow = nodes.get("github-audit-findings").children[0].children[0];
  assert.equal(nativeRow.children[0].textContent, "Tracks cross on F.Cu");
  assert(nativeRow.children[1].textContent.includes("Already present"));
  assert(!nativeRow.children[1].textContent.includes("undefined"));

  // Schematic comparisons reuse the inspector and the correct saved commit.
  respond = async url => url.includes("/schematic?")
    ? { status: "compared", total: 1, next_offset: null,
      before: { status: "read", sha: base, symbols: 1 }, after: { status: "read", sha: head, symbols: 1 },
      changes: [{ kind: "value_changed", reference: "U1", before: "Old", after: "New" }] }
    : { text: "Saved schematic" };
  await execute(`showPreview({path:"board.kicad_sch", status:"M"}, "${base}")`);
  await new Promise(resolve => setImmediate(resolve));
  assert(!nodes.get("github-pcb").hidden);
  assert.equal(nodes.get("github-hardware-title").textContent, "Inside the schematic");
  assert(nodes.get("github-pcb-summary").textContent.includes("1 symbols"));
  assert.equal(nodes.get("github-pcb-changes").children.length, 1);

  // STEP metadata is shown as measured units, and a slow old asset cannot
  // overwrite the next selection's geometry details.
  const artifact = width => ({ before: { status: "absent" }, after: { status: "read", sha: head,
    facts: { dimensions: [width, 60, 20], unit: "mm", solids: 2, faces: 12,
      source: "STEP BREP", volume_mm3: 120000 } } });
  let releaseCad;
  const slowCad = new Promise(resolve => { releaseCad = resolve; });
  respond = async url => {
    if (url.includes("/artifact?")) return url.includes("slow.step") ? slowCad : artifact(100);
    return { text: "STEP source" };
  };
  await execute('showPreview({path:"slow.step"}, null)');
  await execute('showPreview({path:"fast.step"}, null)');
  await new Promise(resolve => setImmediate(resolve));
  releaseCad(artifact(999));
  await new Promise(resolve => setImmediate(resolve));
  assert(nodes.get("github-artifact-summary").textContent.includes("100 × 60 × 20 mm"));
  assert(!nodes.get("github-artifact-summary").textContent.includes("999"));

  const columns = ["Item", "Qty", "Total Cost"];
  const oldShipping = { line: 3, fields: { Item: "Estimated total shipping", Qty: "1", "Total Cost": "$3.70" } };
  const newShipping = { line: 3, fields: { Item: "Estimated total shipping", Qty: "1", "Total Cost": "$3.72" } };
  respond = async url => url.includes("/artifact?") ? {
    before: { status: "read", sha: base, facts: { columns, total_rows: 2, rows: [oldShipping] } },
    after: { status: "read", sha: head, facts: { columns, total_rows: 2, rows: [newShipping] } },
    csv_comparison: { columns, key_column: "Item", changed_cells: 1, added: 0, removed: 0, ambiguous: 0,
      detail: "Rows matched by exact unique Item.", rows: [
        { status: "modified", before: oldShipping, after: newShipping,
          changes: [{ column: "Total Cost", before: "$3.70", after: "$3.72" }] },
        { status: "unchanged", before: oldShipping, after: oldShipping, changes: [] }
      ] }
  } : { text: "CSV source" };
  await execute(`showPreview({path:"BOM.csv", status:"M"}, "${base}")`);
  await new Promise(resolve => setImmediate(resolve));
  assert(nodes.get("github-artifact-summary").textContent.includes("1 changed cell"));
  const csvView = nodes.get("github-artifact-facts");
  const csvBody = csvView.children[1].children[0].children[2];
  assert.equal(csvBody.children.length, 1);
  const changedCell = csvBody.children[0].children[3];
  assert.equal(changedCell.children[0].tag, "del");
  assert.equal(changedCell.children[0].textContent, "$3.70");
  assert.equal(changedCell.children[2].textContent, "$3.72");
  const changedFilter = csvView.children[0].children[0].children[0];
  changedFilter.checked = false; changedFilter.listeners.change();
  assert.equal(csvBody.children.length, 2);

  let savedMappings;
  respond = async (url, options) => {
    if (url.includes("/settings?")) {
      if (options?.method === "PUT") savedMappings = JSON.parse(options.body);
      return savedMappings || { version: 1, cad_pairs: [], pin_assignments: [], boms: [] };
    }
    return page(head);
  };
  await execute('loadSettings()');
  await execute('addMapping("cad_pairs", {board_file:"main.kicad_pcb", mesh_file:"shell.step", units:"mm", mesh_kind:"exterior", board_axes:["x","y"], cavity_mm:null})');
  assert.equal(savedMappings.cad_pairs.length, 1);
  assert.equal(nodes.get("github-mapping-list").children.length, 1);
  assert(nodes.get("github-settings-status").textContent.includes("Saved"));

  const source = { id: "source", sha: head, path: "main.kicad_sch", locator: "U1" };
  const target = { id: "target", sha: head, path: "main.kicad_pcb", locator: "U1" };
  sandbox.connections = [{ id: "link", kind: "schematic_pcb_component", status: "confirmed", source, target,
    summary: "U1 reference matched", metadata: { matching_pads: [{pad:"1"}], unmatched_pads: [] } }];
  execute(`renderConnections({head_sha:"${head}", relationships:connections})`);
  assert.equal(nodes.get("github-tab-connection-count").textContent, "1");
  assert.equal(nodes.get("github-connections").children.length, 1);
  execute('selectReviewTab("connections")');
  assert(!nodes.get("github-connections-panel").hidden);
  assert(nodes.get("github-findings-panel").hidden);
  const explainPosts = calls.filter(call => call.options?.method === "POST" && call.url.includes("/explain")).length;
  let explainRequested = false;
  respond = async (url, options) => {
    if (url.includes("/explain")) {
      if (options?.method === "POST") {
        assert.equal(JSON.parse(options.body).consent, true); explainRequested = true; return {state:"complete"};
      }
      return { provider: {available:true, disclosure:"Selected evidence goes to the configured provider."},
        explanation: explainRequested ? {state:"complete",detail:"Saved explanation",sections:{what_changed:[
          {source_id:"F0", summary:"U1 moved",detail:"Observed placement change",certainty:"observed",evidence:[source,target]}
        ],what_to_review:[],what_could_not_be_checked:[]}} : null };
    }
    return {text:"source"};
  };
  execute('workspaceView.audit = {id:"saved"}');
  await execute('loadExplanation("saved", context)');
  assert(!explainRequested);
  await execute('requestExplanation()');
  assert.equal(calls.filter(call => call.options?.method === "POST" && call.url.includes("/explain")).length, explainPosts + 1);
  assert.equal(nodes.get("github-ai-results").children.length, 3);
  assert(nodes.get("github-explain").disabled);
  let releaseOldExplanation;
  const oldExplanation = new Promise(resolve => { releaseOldExplanation = resolve; });
  respond = async () => oldExplanation;
  const oldRequest = execute('loadExplanation("saved", context)');
  execute('explanationEpoch++; $("github-ai-status").textContent = "New audit context";');
  releaseOldExplanation({provider:{available:true,disclosure:"Old provider"},explanation:{state:"complete",detail:"Old explanation",sections:{}}});
  await oldRequest;
  assert.equal(nodes.get("github-ai-status").textContent, "New audit context");

  const newHead = "c".repeat(40);
  const synced = { id: "fixture", head: newHead, previous_head: head, source: "builder/robot",
    url: "https://github.com/builder/robot", saved_tips: [head, newHead] };
  respond = async url => {
    if (url === "/sync-fixture") return synced;
    if (url === "/v1/github/repositories") return [synced];
    if (url.includes("/commits?")) return { revision: newHead, commits: [], next_offset: null };
    const params = new URL(url, "http://local").searchParams;
    return page(params.get("revision"));
  };
  const syncButton = new Element("button");
  sandbox.syncButton = syncButton;
  await execute('importOrSync(syncButton, "/sync-fixture")');
  assert.equal(execute("revision"), head);
  assert.equal(execute("repo.head"), newHead);
  assert(!nodes.get("github-latest").hidden);
  assert.equal(execute("workspaceView.head_sha"), head);
  assert(!syncButton.disabled);
  assert(nodes.get("github-import-panel").hidden);
  assert(nodes.get("github-welcome").hidden);
  assert(!nodes.get("github-add").hidden);
  assert.equal(nodes.get("github-total-files").textContent, "1");
  execute('selectReviewTab("findings")');
  assert(nodes.get("github-changes-panel").hidden);
  assert(!nodes.get("github-findings-panel").hidden);
  assert.equal(nodes.get("github-tab-findings").attributes["aria-selected"], "true");
  assert.equal(nodes.get("github-tab-changes").tabIndex, -1);
  let prevented = false;
  nodes.get("github-tab-findings").listeners.keydown({ key: "ArrowLeft", preventDefault() { prevented = true; } });
  assert(prevented);
  assert(!nodes.get("github-changes-panel").hidden);
  execute('showImport(true)');
  assert(!nodes.get("github-import-panel").hidden);
  assert.equal(nodes.get("github-add").attributes["aria-expanded"], "true");
  console.log("PASS review races, evidence routing, saved coverage, sync selection, review tabs, counts, import disclosure");
}
main().catch(error => { console.error(error); process.exitCode = 1; });
