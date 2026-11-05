"""Fixed read-only CadQuery task. Runs in a disposable process, never evals code."""

import json
import math
from pathlib import Path
import sys


def inspect_step(source: str, preview: bool) -> dict:
    import cadquery as cq

    imported = cq.importers.importStep(source, unit="MM")
    shapes = imported.vals()
    if not shapes:
        raise ValueError("STEP contains no transferable shapes.")
    compound = cq.Compound.makeCompound(shapes)
    if not compound.isValid():
        raise ValueError("STEP topology is invalid; physical measurements are unverified.")
    box = compound.BoundingBox()
    bounds = [[box.xmin, box.xmax], [box.ymin, box.ymax], [box.zmin, box.zmax]]
    dimensions = [b - a for a, b in bounds]
    if not all(math.isfinite(n) for pair in bounds for n in pair) or max(dimensions) <= 0:
        raise ValueError("STEP has no finite measurable geometry.")
    solids = compound.Solids()
    result = dict(bounds=bounds, dimensions=dimensions, unit="mm", solids=len(solids),
                  faces=len(compound.Faces()), topology_valid=True,
                  volume_mm3=sum(s.Volume() for s in solids) if solids else None,
                  volume_scope="sum of imported solids; overlapping volume is not removed",
                  source="STEP BREP via CadQuery; imported length units normalized to mm")
    if preview:
        vertices, faces = compound.tessellate(max(max(dimensions) * .002, .03), .65)
        if len(faces) > 200000 or len(vertices) > 400000:
            raise ValueError("STEP preview exceeds the tessellation limit; request measurements without preview.")
        if len(faces) > 12000:
            from OCP.BRepTools import BRepTools
            BRepTools.Clean_s(compound.wrapped)
            vertices, faces = compound.tessellate(max(max(dimensions) * .008, .08), 1.1)
        result["total_triangles"] = len(faces)
        if len(faces) <= 16000:
            # Keep every triangle of the coarse tessellation. Dropping random
            # triangles makes a solid enclosure appear to have holes.
            result["triangles"] = [[coordinate for idx in face for coordinate in vertices[idx].toTuple()] for face in faces]
            result["preview_sampled"] = False
        else:
            result["preview_unavailable"] = "Assembly remains too complex for the embedded preview. BREP measurements are available."
    return result


if __name__ == "__main__":
    try:
        result = inspect_step(sys.argv[1], sys.argv[3] == "preview")
        Path(sys.argv[2]).write_text(json.dumps(result, allow_nan=False), encoding="utf-8")
    except Exception:
        # Native logs are not a machine-readable success report. The parent
        # receives a fixed failure, never arbitrary kernel output or repo code.
        sys.exit(2)
