$fn = 48;
wall = 1.0;
thickness = wall;

difference() {
    union() {
        cube([60, 10, thickness]);
        translate([0, 0, 0])
            cube([10, 40, thickness]);
    }
    translate([15, 15, -1]) cylinder(h = thickness + 2, r = 4.0);
    translate([45, 25, -1]) cylinder(h = thickness + 2, r = 4.0);
}
