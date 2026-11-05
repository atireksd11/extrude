"""Read inert STL/OBJ bytes. No paths, material assets, URLs, or CAD scripts."""

from io import BytesIO
import math
import struct
from collections import Counter

import numpy as np
import trimesh
from kicad_tools.core.board_outline import board_outline_bounds
from kicad_tools.sexp import parse_string

from extrude.parse.kicad_pcb import _PARSE_LOCK, MAX_BOARD_BYTES, _rows, _field, _string_field

MAX_MESH_BYTES = 8 * 1024 * 1024
MAX_FACES = 100000
MAX_PREVIEW_FACES = 1800
SCALE = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4}


def read_mesh(data: bytes, extension: str, preview=False) -> dict:
    if len(data) > MAX_MESH_BYTES:
        raise ValueError("Mesh exceeds the 8 MiB analysis limit.")
    kind = extension.lower().lstrip(".")
    if kind not in {"stl", "obj"}:
        raise ValueError("Export an STL or OBJ for measurement. STEP/BREP reading is not enabled in this phase.")
    if kind == "stl" and len(data) >= 84 and 84 + struct.unpack_from("<I", data, 80)[0] * 50 == len(data):
        if struct.unpack_from("<I", data, 80)[0] > MAX_FACES:
            raise ValueError("Mesh exceeds the 100,000-triangle analysis limit.")
    else:
        text = data.decode("utf-8-sig")
        count = 0
        for line in text.splitlines():
            tokens = line.split()
            if kind == "obj" and tokens and tokens[0] == "f":
                if len(tokens) > 1025:
                    raise ValueError("OBJ polygon exceeds the supported vertex limit.")
                count += max(0, len(tokens) - 3)
            elif kind == "stl" and tokens and tokens[0] == "facet":
                count += 1
            if count > MAX_FACES:
                raise ValueError("Mesh exceeds the 100,000-triangle analysis limit.")
    try:
        mesh = trimesh.load_mesh(BytesIO(data), file_type=kind, resolver={}, allow_remote=False,
                                 skip_materials=True, process=False, maintain_order=True)
        if (not isinstance(mesh, trimesh.Trimesh) or not len(mesh.faces) or len(mesh.faces) > MAX_FACES
                or not np.isfinite(mesh.vertices).all() or not np.isfinite(mesh.bounds).all()
                or not (mesh.area_faces > 0).any()):
            raise ValueError("Mesh has no finite, non-degenerate surface within the analysis limit.")
        # STL repeats vertices per facet. Merge identical positions before
        # measuring closure, without filling holes or repairing geometry.
        mesh.merge_vertices(digits_vertex=12)
        bounds = mesh.bounds.T.tolist()
        facts = {"bounds": bounds, "dimensions": mesh.extents.tolist(), "unit": "file units",
                 "total_triangles": len(mesh.faces), "watertight": bool(mesh.is_watertight)}
        if preview:
            step = max(1, math.ceil(len(mesh.faces) / MAX_PREVIEW_FACES))
            facts["triangles"] = mesh.triangles[::step].reshape((-1, 9)).tolist()
        return facts
    except (KeyError, IndexError, TypeError, OverflowError) as exc:
        raise ValueError("Could not read this STL/OBJ mesh.") from exc


def board_spans(data: bytes) -> dict:
    if len(data) > MAX_BOARD_BYTES:
        raise ValueError("Board exceeds the 8 MiB analysis limit.")
    with _PARSE_LOCK:
        root = parse_string(data.decode("utf-8-sig"))
    if root.name != "kicad_pcb":
        raise ValueError("Expected a native KiCad board.")
    endpoints = Counter()
    for node in root.children:
        if _string_field(node, "layer") != "Edge.Cuts":
            continue
        if node.name in {"gr_rect", "gr_circle", "gr_poly"}:
            continue
        if node.name not in {"gr_line", "gr_arc"} or (node.name == "gr_arc" and not _field(node, "mid")):
            raise ValueError("Unsupported outline closure; board dimensions remain unverified.")
        for name in ("start", "end"):
            point = _field(node, name)
            if len(point) != 2:
                raise ValueError("Outline endpoint is unreadable.")
            endpoints[tuple(round(float(v), 6) for v in point)] += 1
    if any(degree != 2 for degree in endpoints.values()):
        raise ValueError("Edge.Cuts contains open or branched paths; board dimensions remain unverified.")
    bounds = board_outline_bounds(root)
    if bounds is None or not all(math.isfinite(v) for v in bounds):
        raise ValueError("No readable Edge.Cuts outline; dimensions are unverified.")
    dimensions = [bounds[2] - bounds[0], bounds[3] - bounds[1]]
    if any(v <= 0 for v in dimensions):
        raise ValueError("Edge.Cuts does not provide two measurable board spans.")
    # Upstream bounds intentionally do not validate closure/topology. We report
    # spans only; they never establish collision-free enclosure fit.
    return {"bounds_mm": list(bounds), "dimensions_mm": dimensions,
            "scope": "Edge.Cuts axis-aligned spans; outline topology and mounted components unverified"}
