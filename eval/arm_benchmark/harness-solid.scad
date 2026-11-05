$fn = 64;

// Dimensions are in millimeters.
base_x = 90;
base_y = 75;
base_t = 6;

insert_spacing_x = 68;
insert_spacing_y = 52;
insert_pocket_d = 4.2;
insert_pocket_depth = 5.5;
insert_clearance_d = 3.2;

link1_length = 78;
link2_length = 68;
link3_length = 48;

shoulder_angle = -55;
elbow_angle = 75;
wrist_angle = -35;

module y_cylinder(h, r) {
    rotate([90, 0, 0])
        cylinder(h = h, r = r, center = true);
}

module base_plate() {
    difference() {
        translate([0, 0, base_t / 2])
            cube([base_x, base_y, base_t], center = true);

        for (x = [-insert_spacing_x / 2, insert_spacing_x / 2])
            for (y = [-insert_spacing_y / 2, insert_spacing_y / 2]) {
                translate([x, y, base_t - insert_pocket_depth / 2])
                    cylinder(d = insert_pocket_d, h = insert_pocket_depth, center = true);
                translate([x, y, 0.25])
                    cylinder(d = insert_clearance_d, h = 0.5, center = true);
            }
    }
}

module pedestal() {
    difference() {
        union() {
            for (y = [-10, 10])
                hull() {
                    translate([0, y, 14])
                        cube([24, 4, 16], center = true);
                    translate([0, y, 42])
                        y_cylinder(4, 14);
                }
        }
        translate([0, 0, 42])
            y_cylinder(30, 4.2);
    }
}

module arm_link(length) {
    difference() {
        union() {
            hull() {
                translate([8, 0, 0])
                    y_cylinder(14, 8);
                translate([length - 8, 0, 0])
                    y_cylinder(14, 8);
            }
            translate([0, 0, 0])
                y_cylinder(14, 13);
            translate([length, 0, 0])
                y_cylinder(14, 13);
        }

        translate([0, 0, 0])
            y_cylinder(16, 4.2);
        translate([length, 0, 0])
            y_cylinder(16, 4.2);
    }
}

module joint_detail() {
    color([0.22, 0.24, 0.27]) {
        y_cylinder(24, 3.7);

        for (side = [-1, 1]) {
            translate([0, side * 9, 0])
                y_cylinder(3, 9);
            translate([0, side * 11.5, 0])
                y_cylinder(3, 5.5);
        }
    }
}

module gripper() {
    color([0.18, 0.20, 0.23]) {
        // Palm and mounting block
        translate([9, 0, 0])
            cube([18, 24, 18], center = true);

        // Two opposing fingers
        for (side = [-1, 1]) {
            translate([31, 0, side * 8])
                cube([32, 8, 6], center = true);
            translate([47, 0, side * 8])
                cube([8, 12, 10], center = true);
        }
    }
}

module robot_arm() {
    color([0.24, 0.27, 0.30]) {
        base_plate();
        pedestal();
    }

    color([0.82, 0.32, 0.12]) {
        translate([0, 0, 42])
            joint_detail();

        translate([0, 0, 42])
            rotate([0, shoulder_angle, 0]) {
                arm_link(link1_length);

                translate([link1_length, 0, 0]) {
                    joint_detail();

                    rotate([0, elbow_angle, 0]) {
                        arm_link(link2_length);

                        translate([link2_length, 0, 0]) {
                            joint_detail();

                            rotate([0, wrist_angle, 0]) {
                                arm_link(link3_length);

                                translate([link3_length, 0, 0]) {
                                    joint_detail();
                                    translate([5, 0, 0])
                                        gripper();
                                }
                            }
                        }
                    }
                }
            }
    }
}

robot_arm();