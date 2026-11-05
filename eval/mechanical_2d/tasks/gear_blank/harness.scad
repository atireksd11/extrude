$fn = 72;
difference() {
    circle(d = 50);
    for (angle = [0:60:300])
        rotate(angle) translate([20, 0]) circle(d = 2.4);
}
