module base() {
    translate([-55, -45, 0])
        cube([110, 90, 8]);
    translate([0, 0, 8])
        cylinder(r=18, h=18);
    translate([0, 0, 26])
        cylinder(r=13, h=8);
}

module link1() {
    translate([0, -9, -5])
        cube([70, 18, 10]);
}

module link2() {
    translate([0, -8, -5])
        cube([58, 16, 10]);
}

module link3() {
    translate([0, -7, -4])
        cube([45, 14, 8]);
}

module joint1() {
    cylinder(r=12, h=16, center=true);
    translate([0, 0, 8])
        cylinder(r=7, h=3, center=true);
}

module joint2() {
    cylinder(r=10, h=14, center=true);
    translate([0, 0, 7])
        cylinder(r=6, h=3, center=true);
}

module joint3() {
    cylinder(r=9, h=12, center=true);
    translate([0, 0, 6])
        cylinder(r=5, h=3, center=true);
}

module gripper() {
    translate([0, -14, -5])
        cube([12, 28, 10]);
    translate([10, -12, -3])
        cube([24, 5, 6]);
    translate([10, 7, -3])
        cube([24, 5, 6]);
}

base();

translate([0, 0, 34])
    joint1();

translate([0, 0, 34])
rotate([0, 0, 15]) {
    link1();
    translate([70, 0, 0]) {
        joint2();
        rotate([0, 0, -40]) {
            link2();
            translate([58, 0, 0]) {
                joint3();
                rotate([0, 0, 55]) {
                    link3();
                    translate([45, 0, 0])
                        gripper();
                }
            }
        }
    }
}