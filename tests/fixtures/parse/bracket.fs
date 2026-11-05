annotation { "FeatureScript 1"; }
export const holeDia = 4.2 * millimeter;
// M3
skCircle(center, holeDia);
opFillet(id, { radius: 1 * millimeter });
// extrude-wall rib 1.2 0.2
