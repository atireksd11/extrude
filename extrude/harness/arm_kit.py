"""Parametric standing serial arm. Used when the request is an articulated manipulator."""

from extrude.verify.models import SolidVerifySpec

_ARM_WORDS = ("arm", "robot", "gripper", "manipulator", "joint", "servo")


def is_articulated_arm(sentence: str) -> bool:
    lowered = sentence.lower()
    return any(word in lowered for word in _ARM_WORDS)


def emit_articulated_arm(verify: SolidVerifySpec) -> str:
    """Desktop 4-axis arm: floor plate, turret, pitched beams, parallel jaws."""
    insert_d = 4.2
    if verify.insert_min_mm is not None and verify.insert_max_mm is not None:
        insert_d = (float(verify.insert_min_mm) + float(verify.insert_max_mm)) / 2
    wall = max(float(verify.min_wall_mm or 8.0), 8.0)
    holes = max(int(verify.insert_count or 4), 4)
    return f"""$fn = 64;
$vpr = [62, 0, 28];
$vpt = [20, 0, 70];
$vpd = 420;

plate_x = 140;
plate_y = 118;
plate_z = 8;
insert_d = {insert_d:g};
insert_r = insert_d / 2;
inset = 14;
column_h = 42;
beam_t = {wall:g};
reach_a = 84;
reach_b = 70;
reach_c = 52;
yaw = 18;
shoulder = -52;
elbow = 118;
wrist = 22;

module rounded_base() {{
    color([0.18, 0.20, 0.23])
        difference() {{
            hull() {{
                for (x = [-plate_x / 2 + 10, plate_x / 2 - 10], y = [-plate_y / 2 + 10, plate_y / 2 - 10])
                    translate([x, y, 0])
                        cylinder(h = plate_z, r = 10);
            }}
            for (x = [-plate_x / 2 + inset, plate_x / 2 - inset], y = [-plate_y / 2 + inset, plate_y / 2 - inset])
                translate([x, y, -1])
                    cylinder(h = plate_z + 2, r = insert_r);
        }}
    color([0.28, 0.30, 0.34])
        translate([0, 0, plate_z])
            cylinder(h = 6, r = 28);
}}

module hinge_stack(radius) {{
    color([0.14, 0.16, 0.18])
        cylinder(h = 16, r = radius, center = true);
    color([0.92, 0.42, 0.12])
        translate([0, 0, 8])
            cylinder(h = 4, r = radius * 0.72);
    color([0.82, 0.84, 0.86])
        for (a = [0 : 90 : 270])
            rotate([0, 0, a])
                translate([radius * 0.78, 0, 10])
                    cylinder(h = 2, r = 1.6);
}}

module arm_link(length, width = 24, thickness = beam_t) {{
    color([0.76, 0.79, 0.82])
        hull() {{
            translate([width / 2, 0, 0])
                cylinder(h = thickness, r = width / 2, center = true);
            translate([length - width / 2, 0, 0])
                cylinder(h = thickness, r = width / 2 * 0.82, center = true);
        }}
    color([0.93, 0.45, 0.16])
        hull() {{
            translate([width / 2 + 6, 0, thickness / 2])
                cube([8, 6, 2], center = true);
            translate([length - width / 2 - 6, 0, thickness / 2])
                cube([8, 5, 2], center = true);
        }}
    color([0.16, 0.17, 0.19])
        translate([length / 2, 0, 0])
            cube([length * 0.55, 3.2, thickness * 0.45], center = true);
}}

module jaw_pair() {{
    color([0.16, 0.18, 0.21])
        cube([18, 36, 14], center = true);
    color([0.90, 0.40, 0.12])
        translate([0, 0, 8])
            cube([14, 38, 2], center = true);
    for (side = [-1, 1]) {{
        translate([12, side * 11, 0]) {{
            color([0.78, 0.81, 0.84])
                hull() {{
                    cylinder(h = 8, r = 5, center = true);
                    translate([28, 0, 0])
                        cylinder(h = 7, r = 3.4, center = true);
                }}
            color([0.12, 0.12, 0.14])
                translate([32, 0, 0])
                    cube([8, 3.2, 10], center = true);
        }}
    }}
}}

module robot_arm() {{
    rounded_base();
    color([0.34, 0.37, 0.41])
        translate([0, 0, plate_z + 6])
            cylinder(h = column_h - 10, r1 = 22, r2 = 16);
    color([0.14, 0.16, 0.18])
        translate([0, 0, plate_z + column_h])
            cylinder(h = 10, r = 18);

    translate([0, 0, plate_z + column_h + 8])
        rotate([0, 0, yaw]) {{
            hinge_stack(16);
            rotate([0, shoulder, 0]) {{
                arm_link(reach_a, 26, beam_t);
                translate([reach_a, 0, 0]) {{
                    hinge_stack(13);
                    rotate([0, elbow, 0]) {{
                        arm_link(reach_b, 22, beam_t);
                        translate([reach_b, 0, 0]) {{
                            hinge_stack(11);
                            rotate([0, 0, wrist]) {{
                                arm_link(reach_c, 18, 8);
                                translate([reach_c + 8, 0, 0]) {{
                                    hinge_stack(9);
                                    jaw_pair();
                                }}
                            }}
                        }}
                    }}
                }}
            }}
        }}
}}

robot_arm();
// {holes} mounting holes at insert_d
"""
