"""Structural wall thickness ignores decorative ridges."""

import os
import shutil
from pathlib import Path

import pytest

from eval.arm_benchmark.solid_score import score_solid
from eval.arm_benchmark.spec_card import load_spec

_ROOT = Path(__file__).resolve().parents[1] / "eval" / "arm_benchmark"


@pytest.mark.skipif(shutil.which("openscad") is None and not os.environ.get("OPENSCAD_PATH"), reason="openscad is not installed")
def test_off_scad_joint_wall_measures_structural_thickness(tmp_path):
    spec = load_spec()
    scored = score_solid(_ROOT / "off.scad", spec, tmp_path)
    assert scored["checks"]["joint_wall"] is True
    assert scored["facts"]["min_thickness"] >= 2.0
