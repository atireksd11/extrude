$fn = 48;

// Desktop robotic arm — all dimensions are in millimeters.
base_length = 130;
base_width  = 110;
base_thickness = 8;

link1_length = 88;
link2_length = 76;
link3_length = 58;

shoulder_height = 44;
shoulder_angle = 25;
elbow_angle = -55;
wrist_angle = 30;

module rounded_base() {
    difference() {
        hull() {
            for (x = [-57, 57], y = [-47, 47])
                translate([x, y, 0])
                    cylinder(h = base_thickness, r = 8);
        }
        for (x = [-53, 53], y = [-43, 43])
            translate([x, y, -1])
                cylinder(h = base_thickness + 2, r = 2.1);
    }
}

module rotary_joint(radius = 13) {
    color([0.16, 0.19, 0.23])
        translate([0, 0, -5])
            cylinder(h = 10, r = radius);

    color([0.86, 0.30, 0.12])
        translate([0, 0, 5])
            cylinder(h = 3, r = radius * 0.72);

    color([0.76, 0.79, 0.82])
        for (a = [0 : 90 : 270])
            rotate([0, 0, a])
                translate([radius * 0.78, 0, 8])
                    cylinder(h = 1.2, r = 1.35);
}

module link_shape(length, width, thickness) {
    hull() {
        translate([width / 2, 0, -thickness / 2])
            cylinder(h = thickness, r = width / 2);
        translate([length - width / 2, 0, -thickness / 2])
            cylinder(h = thickness, r = width / 2);
    }
}

module arm_link(length, width = 22, thickness = 8) {
    color([0.78, 0.81, 0.84])
        link_shape(length, width, thickness);

    color([0.93, 0.45, 0.18])
        translate([0, 0, thickness / 2])
            hull() {
                translate([width / 2 + 3, 0, 0])
                    cylinder(h = 1, r = 3.2);
                translate([length - width / 2 - 3, 0, 0])
                    cylinder(h = 1, r = 3.2);
            }
}

module gripper() {
    // Wrist adapter and palm
    color([0.18, 0.21, 0.25])
        translate([2, -15, -5])
            cube([22, 30, 10]);

    color([0.85, 0.35, 0.14])
        translate([7, -17, 4.5])
            cube([13, 34, 1.2]);

    // Two parallel fingers
    for (side = [-1, 1]) {
        color([0.76, 0.79, 0.82])
            translate([20, side * 10, 0])
                link_shape(31, 7, 7);

        color([0.16, 0.19, 0.23])
            translate([47, side * 10, -3.7])
                cube([5, 2.2, 7.4]);

        color([0.86, 0.30, 0.12])
            translate([20, side * 10, -5])
                cylinder(h = 10, r = 4);
    }
}

module robot_arm() {
    // Base plate and pedestal
    color([0.22, 0.25, 0.29])
        rounded_base();

    color([0.34, 0.38, 0.43])
        translate([0, 0, base_thickness])
            cylinder(h = 28, r1 = 18, r2 = 15);

    color([0.16, 0.19, 0.23])
        translate([0, 0, base_thickness + 28])
            cylinder(h = 8, r = 17);

    // Shoulder joint and articulated links
    translate([0, 0, shoulder_height])
        rotary_joint(15);

    translate([0, 0, shoulder_height])
        rotate([0, 0, shoulder_angle]) {
            arm_link(link1_length);

            translate([link1_length, 0, 0])
                rotary_joint(12);

            translate([link1_length, 0, 0])
                rotate([0, 0, elbow_angle]) {
                    arm_link(link2_length);

                    translate([link2_length, 0, 0])
                        rotary_joint(10);

                    translate([link2_length, 0, 0])
                        rotate([0, 0, wrist_angle]) {
                            arm_link(link3_length, 19, 7);

                            translate([link3_length, 0, 0]) {
                                rotary_joint(8);
                                gripper();
                            }
                        }
                }
        }
}

robot_arm();