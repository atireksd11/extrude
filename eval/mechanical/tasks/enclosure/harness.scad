$fn = 48;
wall = 2.0;

difference() {
    cube([100, 80, 40]);
    translate([wall, wall, wall])
        cube([100 - 2 * wall, 80 - 2 * wall, 40 - wall]);
    for (x = [15, 85], y = [15, 65])
        translate([x, y, -1])
            cylinder(h = 42, r = 2.1);
}
