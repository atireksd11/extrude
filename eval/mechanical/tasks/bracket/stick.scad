module link1() { cube([5, 5, 30]); }
module link2() { cube([5, 5, 25]); }
link1();
translate([10, 0, 0]) link2();
