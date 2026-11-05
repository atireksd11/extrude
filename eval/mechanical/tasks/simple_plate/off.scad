$fn = 48;
difference() {
    cube([80, 60, 4]);
    for (x = [12, 68], y = [12, 48])
        translate([x, y, -1])
            cylinder(h = 6, r = 2.1);
}
