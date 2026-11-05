// Simple jaw plate, dimensions in millimeters.
$fn = 32;
module jaw() {
  union() {
    cube([44, 24, 5], center = true);
    translate([14, 0, 7]) cube([8, 24, 9], center = true);
  }
}
jaw();
