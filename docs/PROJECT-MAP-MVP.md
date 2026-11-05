# Extrude project map: first testable version

## The first user loop

Open `/projects`, connect a folder containing a real hardware project, and leave the page open while working. The page scans saved files every five seconds. A changed firmware, KiCad, or CAD file lights up its area of the map, appears in the timeline, and creates a **possible effect** for connected areas. The effect is a review prompt, not a verified failure.

For a hands-on introduction, click **Explore a working demo**. The bundled robotic gripper has firmware, an exported KiCad netlist, a PCB file, OpenSCAD source, and an STL model. Click **Make a demo change** to toggle a real firmware pin value. The timeline shows its text diff and the configured pin check switches between passed and failed. This action edits only the demo copy under `data/demo-robot`.

The map shows real project files beneath each engineering area. Area nodes filter the tracked file list; file nodes open the inspector directly. Selecting a file shows source text or an interactive STL/OBJ preview with orbit, zoom, slow rotation, triangle count, and model bounds. Larger design files up to 128 MB are tracked; skipped files are reported in the UI. Text previews are capped at 100 KB and text diffs are captured for files at most 128 KB.

Possible effects stay visible until reviewed. Open **Investigate impact** to compare the source diff with a file in the affected area and see any available engineering checks. Record whether the effect was relevant and optionally write a note; the result appears in **Review decisions** after reload. A new edit replaces earlier effects for the same source. Failed pin checks remain active until the files agree; the check panel continues to show their exact pin values. The **Export handoff** button downloads a Markdown summary of findings, checks, changes, and review decisions without embedding source file contents or local absolute paths.

Extrude runs its netlist preflight on `.net` files and KiCad ERC/DRC on saved `.kicad_sch` and `.kicad_pcb` files when `kicad-cli` is available. The check panel distinguishes passed, failed, and unverified results. Files remain untouched. The project history is stored in local SQLite at `data/project-map.sqlite`; set `EXTRUDE_PROJECT_DB` to change that location.

For a real cross-file check, use the **Pin checks** form in the dashboard to map a firmware symbol to a KiCad exported netlist pin. The rules live in Atlas's local SQLite database and do not edit project files. An existing `extrude-project.json` manifest is also supported:

```json
{
  "pin_assignments": [
    {
      "firmware_file": "firmware/main.ino",
      "firmware_symbol": "SENSOR_PIN",
      "netlist_file": "electronics/robot.net",
      "schematic_net": "SENSOR",
      "mcu_ref": "U1"
    }
  ]
}
```

The symbol must have a numeric assignment such as `#define SENSOR_PIN 12` or `const int SENSOR_PIN = 12;`. The KiCad exported netlist must identify a physical pin on the named net. A mismatch is a verified failure; missing or unreadable inputs are unverified. Supported 3D preview formats are STL and OBJ. STEP/STP files are tracked and shown as source text, but their geometry is not rendered by this viewer. Mesh dimensions are reported in file units because STL and OBJ do not encode physical units.

## Two-week pilot plan

### Fifteen-minute test with each builder

1. Ask them to connect their own project folder without help. Record where setup stalls and how long it takes to reach the map.
2. Have them make one small real change in firmware, a KiCad file, or CAD. Confirm the change appears in the timeline and ask whether the suggested effects match what they would actually inspect.
3. Open one impact together. Have them compare the source diff with a target file, record a short review decision, then reload to verify the decision persists.
4. Export the handoff and give it to another team member. Ask whether they can understand what changed and what remains to check without a verbal explanation.
5. Record false alarms, missed dependencies, unavailable tools, and the one thing they wanted to do next. Use those observations to choose the next integration or check.

1. **First project:** connect one builder's real folder, export its KiCad netlist, configure one known pin relationship, and replay a past mismatch. Record whether the warning matches the real issue.
2. **Three projects:** onboard the two friends' individual projects and the collaborative project. Collect actual file changes and ask which effects were useful, missed, or noisy.
3. **Live integration next:** add GitHub push events and Onshape document events to the same project history. The current pilot reads local Git HEAD and stores an Onshape link, but does not yet sync either service or share changes across computers.
4. **Decision gate:** keep building only if builders use the map during real changes and confirm that at least one warning or check saved investigation or rework. Record false alarms and missing relationships before adding more automation.

## Current boundaries

This is a local pilot, served by the existing FastAPI app. The map groups files by engineering area; its ordinary edges are possible dependencies, not confirmed design relationships. A configured pin rule is shown as a verified relationship. Onshape is a link until its authenticated API adapter is built. The 3D viewer inspects CAD meshes; it is not a CAD editor. Git is read as a local HEAD reference, not synchronized across teammates. No source files are uploaded to an online database, no model trains on project data, and no suggested repair edits a file. Do not expose this local server to the public internet; it has no user authentication yet.

Run the app with `python -m uvicorn extrude.api.server:app --host 127.0.0.1 --port 8000` and open `http://127.0.0.1:8000/projects`.
