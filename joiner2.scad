include <core.scad>;

$fn = $preview ? 12 : 25;
N = 1;
S = sqrt(N);

for(x = [0:1:S -1]) for(y = [0:1:S -1])
{
  translate([x * 55, y * 45, 0]) joiner2();
}
