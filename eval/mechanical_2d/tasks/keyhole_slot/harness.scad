$fn = 48;
difference() {
    square([40, 20]);
    translate([20, 10]) square([20, 8], center = true);
    translate([8, 10]) circle(d = 3.2);
    translate([32, 10]) circle(d = 3.2);
}
