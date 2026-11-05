module gear_stick() {
    circle(r = 3);
    for (a = [0:90:270])
        rotate(a) translate([8, 0]) circle(r = 2);
}
gear_stick();
