include <core.scad>

X = 50; // Females 43-60   Males 49-69
Y = X/51*36; // Females 29-43   Males 34..49

$fn = $preview ? 20 : 100;

cd = 2; // curve diameter for champhoring

subtractDrillHole=1;

difference()
{
    minkowski()
    {   
        union()
        {
            scale([1,Y/X,1]) difference()
            {
              cylinder(d=X+15,h=30, center=true);
              cylinder(d=X+5+ cd,h=31, center=true);
              translate([0,-500,0]) cube([1000,1000,1000], center=true);
            }
            
            difference()
            {
              union()
              {
                translate([0,-Y/4,0,]) cube([X+15,Y/2,30], center=true);
                translate([0,-Y/2+1,0,]) cube([X+55,2,30], center=true);
              }
              translate([0,-Y/4,0,]) cube([X+7,Y/2,31], center=true);
            }
        
        }
        sphere(r = cd);
    }
    translate([0,Y/2+2.5+2,-12]) rotate([90,0,0])female(false);
    translate([0,Y/2+2.5+2,12]) rotate([-90,0,0])female(false);
    
  if(subtractDrillHole) for (x = [-X/2-20, X/2+20]) translate([x,-Y/2+5,0]) rotate([-90,0,0])
  {
    cylinder(d = 6.5, h = 15, center = true);
    translate([0, 0, 5]) cylinder(d = 16.5, h = 15, center = true);
  }
}