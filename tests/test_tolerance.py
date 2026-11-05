"""Print tolerance numbers. No model."""

from extrude.checks.tolerance import HoleCheck, WallCheck, check_tolerance


def test_an_m3_petg_hole_that_is_too_small_fails():
    report = check_tolerance(
        holes=[HoleCheck(name="M3_mount_1", diameter_mm=3.5, intended_insert="M3")],
        walls=[],
        filament="PETG",
    )
    assert "hole_undersized_for_insert:M3_mount_1" in report.blocking
    assert report.measurements[0].limit_mm == 4.05
    assert report.measurements[0].measured_mm == 3.5


def test_a_correct_m3_petg_hole_passes():
    report = check_tolerance(
        holes=[HoleCheck(name="M3_mount_1", diameter_mm=4.2, intended_insert="M3")],
        walls=[WallCheck(name="side", thickness_mm=2.0, normal_z=1.0)],
        filament="petg",
    )
    assert report.blocking == []
    assert report.warnings == []


def test_a_thin_wall_fails_and_a_steep_overhang_blocks():
    report = check_tolerance(
        holes=[],
        walls=[WallCheck(name="rib", thickness_mm=0.8, normal_z=0.1)],
        filament="PLA",
    )
    assert "wall_below_min:rib" in report.blocking
    assert "overhang_risk:rib" in report.blocking


def test_a_mild_overhang_is_only_a_warning():
    report = check_tolerance(
        holes=[],
        walls=[WallCheck(name="lip", thickness_mm=2.0, normal_z=0.4)],
        filament="PLA",
    )
    assert report.blocking == []
    assert report.warnings == ["overhang_risk:lip"]


def test_an_unknown_filament_blocks_before_geometry():
    report = check_tolerance(
        holes=[HoleCheck(name="M2", diameter_mm=3.2, intended_insert="M2")],
        walls=[],
        filament="ABS",
    )
    assert report.blocking == ["unknown_filament:ABS"]


def test_edges_insert_case_and_the_m4_wall_floor():
    on_low = check_tolerance(
        holes=[HoleCheck(name="edge", diameter_mm=4.05, intended_insert="m3")],
        walls=[],
        filament="PETG",
    )
    over = check_tolerance(
        holes=[HoleCheck(name="wide", diameter_mm=4.36, intended_insert="M3")],
        walls=[WallCheck(name="boss", thickness_mm=1.6, normal_z=0.5)],
        filament="PLA",
    )
    raised = check_tolerance(
        holes=[HoleCheck(name="wide", diameter_mm=5.0, intended_insert="M4")],
        walls=[WallCheck(name="boss", thickness_mm=1.6, normal_z=0.5)],
        filament="PLA",
    )
    assert on_low.blocking == []
    assert "hole_oversized_for_insert:wide" in over.blocking
    assert over.blocking == ["hole_oversized_for_insert:wide"]
    assert "wall_below_min:boss" in raised.blocking
    assert raised.measurements[0].limit_mm == 2.0


def test_a_mild_overhang_is_measured_and_a_bad_normal_blocks():
    mild = check_tolerance(
        holes=[],
        walls=[WallCheck(name="lip", thickness_mm=2.0, normal_z=0.3)],
        filament="PLA",
    )
    broken = check_tolerance(
        holes=[],
        walls=[
            WallCheck(name="lip", thickness_mm=2.0, normal_z=1.4),
            WallCheck(name="lip", thickness_mm=2.0, normal_z=1.0),
            WallCheck(name="  ", thickness_mm=2.0),
        ],
        filament="PLA",
    )
    assert mild.blocking == []
    assert mild.warnings == ["overhang_risk:lip"]
    assert mild.measurements[0].severity == "warn"
    assert mild.measurements[0].limit_mm == 0.5
    assert "overhang_normal_invalid:lip" in broken.blocking
    assert "duplicate_feature:lip" in broken.blocking
    assert "unnamed_feature:wall" in broken.blocking


def test_pla_and_petg_use_different_m2_targets():
    pla = check_tolerance(
        holes=[HoleCheck(name="a", diameter_mm=3.2, intended_insert="M2")],
        walls=[],
        filament="PLA",
    )
    petg = check_tolerance(
        holes=[HoleCheck(name="a", diameter_mm=3.2, intended_insert="M2")],
        walls=[],
        filament="PETG",
    )
    assert pla.blocking == []
    assert "hole_undersized_for_insert:a" in petg.blocking
