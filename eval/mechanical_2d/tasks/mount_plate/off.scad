$fn = 48;
difference() {
    square([80, 60]);
    for (xy = [[10, 10], [70, 10], [10, 50], [70, 50]])
        translate(xy) circle(d = 2.5);
}
