$fn = 48;
wall = 2.0;
thickness = wall;

difference() {
    union() {
        cube([60, 10, thickness]);
        translate([0, 0, 0])
            rotate([0, 0, 90])
                cube([40, 10, thickness]);
    }
    translate([15, 15, -1]) cylinder(h = thickness + 2, r = 2.6);
    translate([45, 25, -1]) cylinder(h = thickness + 2, r = 2.6);
}
