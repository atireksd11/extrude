difference() {
  cube([40, 30, 8]);
  // M3 heat-set
  translate([10, 10, 0]) cylinder(h=8, d=3.5);
  // M4
  translate([30, 15, 0]) cylinder(h=8, r=2.6);
}
// extrude-wall side 2.0 1.0
