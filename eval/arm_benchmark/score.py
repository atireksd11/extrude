"""Frozen score for one robotic-arm OpenSCAD file. Both runs use this."""

import re

from extrude.parse.openscad import parse_openscad

PROMPT = (
    "Build a full 3D model of a desktop robotic arm in OpenSCAD. "
    "Include a base plate, three arm links, three rotary joints, and a two-finger gripper. "
    "Use millimeters. Output only the OpenSCAD code."
)

def strip_fences(text: str) -> str:
    stripped = text.strip()
    match = re.search(r"```(?:openscad|scad)?\s*([\s\S]*?)```", stripped, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return stripped


def score_arm(text: str) -> dict:
    code = strip_fences(text)
    design = parse_openscad(code)
    cylinders = len(re.findall(r"\bcylinder\s*\(", code, re.IGNORECASE))
    cubes = len(re.findall(r"\bcube\s*\(", code, re.IGNORECASE))
    translates = len(re.findall(r"\btranslate\s*\(", code, re.IGNORECASE))
    numbers = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", code)]
    checks = {
        "openscad_geometry": bool(re.search(r"\b(?:cube|cylinder|sphere|polyhedron)\s*\(", code, re.IGNORECASE)),
        "braces_balance": code.count("{") == code.count("}") and "{" in code,
        "base_module": re.search(r"\bmodule\s+base\b", code, re.IGNORECASE) is not None,
        "three_links": len(re.findall(r"\bmodule\s+link[123]\b", code, re.IGNORECASE)) >= 3,
        "three_joints": len(re.findall(r"\bmodule\s+joint[123]\b", code, re.IGNORECASE)) >= 3,
        "gripper_two_fingers": re.search(r"\bmodule\s+gripper\b", code, re.IGNORECASE) is not None
        and len(re.findall(r"\bfinger\b", code, re.IGNORECASE)) >= 2,
        "millimeter_scale": any(number >= 20 for number in numbers),
        "enough_parts": cylinders + cubes >= 6,
        "parts_are_placed": translates >= 3,
        "cylinders_were_readable": cylinders > 0
        and not any(item.startswith("unparsed_cylinder") for item in design.warnings),
    }
    passed = sum(1 for item in checks.values() if item)
    return {
        "percent": round(100 * passed / len(checks), 1),
        "passed": passed,
        "out_of": len(checks),
        "checks": checks,
    }
