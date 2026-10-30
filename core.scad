$fn = $preview ? 12 : 40;

cd = 2; // curve diameter for champhoring

module male()
{
  scale([3, 1, 1]) sphere(d = 6);
  hull()
  {
    translate([0, -6, 0]) rotate([90, 0, 0]) scale([2, 2, 1])
      cylinder(d1 = 3, d2 = 5, h = 12, center = true);
    translate([0, -6, 4]) rotate([75, 0, 0]) scale([1, 1, 3]) sphere(d = 5);
  }
}

module face(l, w = 50)
{
  minkowski()
  {
    cube([w -cd, l -cd, 10 -cd], center = true);
    sphere(r = cd);
  }
}

module female(locked = true)
{
  render()
  {
    for(a = [-90:($preview ? 10:2):90])
    {
      rotate([a, 0, 0]) scale(1.1) male();
    }
    if(locked) for(a = [-10:($preview ? 10:2):10])
    {
      rotate([0, a, 0]) scale(1.1) male();
    }

    if(!locked)
    {
      for(i = [0:($preview ? 10:2):90])
      {
        translate([0, -i / 10, -i / 20]) rotate([90 + i / 5, 0, i]) scale(1.02)
          male();
      }
    }
  }
}

module link(subtractFemale = true, subtractDrillHole = true,
            femaleLocked = true)
{
  translate([-0, 45, 0]) male();

  difference()
  {
    union()
    {
      translate([0, 14, 0]) face(l = 40);
    }
    if(subtractFemale) female(femaleLocked);
    translate([0, 18, 0])
    {
      if(subtractDrillHole)
      {
        cylinder(d = 6.5, h = 15, center = true);
        translate([0, 0, 5]) cylinder(d = 16.5, h = 15, center = true);
      }

      translate([18, -3, 0]) cube([12, 39, 8], center = true);
      translate([-18, -3, 0]) cube([12, 39, 8], center = true);
    }
  }
}

module strap(segCount)
{
  for(i = [0:1:segCount])
  {
    translate([0, i * 45, 0]) link(i > 0);
  }

  translate([0, -17, 0]) rotate([0, 0, 180]) male();
}

module joiner2()
{
  difference()
  {
    face(l = 40);

    translate([0, -12, 0]) female(locked = false);
    translate([0, 12, 0]) rotate([0, 0, 180]) female(locked = false);
  }
}

module joiner4()
{
  difference()
  {
    face(l = 40);

    translate([0, -13, 0]) female(locked = false);
    translate([0, 13, 0]) rotate([0, 0, 180]) female(locked = false);

    translate([-18, 0, 0]) rotate([0, 0, -90]) female(locked = false);
    translate([18, 0, 0]) rotate([0, 0, 90]) female(locked = false);
  }
}

module joinerHouse()
{
  difference()
  {
    hull()
    {
      face(l = 40);
      translate([0,20,0]) face(l = 50,w=5);
    }

    translate([0, -13, 0]) female(locked = false);

    translate([-18, 0, 0]) rotate([0, 0, -90]) female(locked = false);
    translate([18, 0, 0]) rotate([0, 0, 90]) female(locked = false);

    translate([-10, 28, 0]) rotate([0, 0, 225]) female(locked = false);
    translate([10, 28, 0]) rotate([0, 0, -225]) female(locked = false);
  }
}


module joinerLimb(c = 2)
{
  difference()
  {
    w = 40 + 80 * c;

    face(w);
    translate([0, -10 -40 * c, 0]) rotate([0, 0, 0]) female(locked = false);
    translate([0, 10 + 40 * c, 0]) rotate([0, 0, 180]) female(locked = false);

    for(a = [0:1:c])
    {
      translate([15, 70 * a -35 * c, 0]) rotate([0, 0, 90])
        female(locked = false);
      translate([-15, 70 * a -35 * c, 0]) rotate([0, 0, -90])
        female(locked = false);
    }

    cube([10, 150, 7], center = true);

    translate([0, 0, 5]) linear_extrude(3) rotate([0, 0, 90])
      text("KinkyCastle.XXX", halign = "center", valign = "center", size = 8);
  }
}

module joinerTits()
{
  c = 3;
  difference()
  {
    union()
    {
      hull()
      {
        face(150, 20);
        translate([0, -75, 0]) face(150);
      }
      translate([0, 110, 0]) minkowski()
      {
        sphere(r = cd);
        cylinder(d = 100, h = 10 -cd, center = true);
      }
    }

    translate([20, -20, 0]) rotate([0, 0, 90]) female(locked = false);
    translate([-20, -20, 0]) rotate([0, 0, -90]) female(locked = false);

    translate([20, -70, 0]) rotate([0, 0, 90]) female(locked = false);
    translate([-20, -70, 0]) rotate([0, 0, -90]) female(locked = false);

    translate([20, -120, 0]) rotate([0, 0, 90]) female(locked = false);
    translate([-20, -120, 0]) rotate([0, 0, -90]) female(locked = false);

    translate([0, -145, 0]) female(locked = false);

    for(a = [90, 270, 135, 225])
    {
      translate([0, 110, 0]) rotate([0, 0, a]) translate([0, -45, 0])
        female(locked = false);
    }

    translate([0, 110, 0]) cylinder(d = 60, h = 7, center = true);
    translate([0, 95, 0]) cylinder(d = 50, h = 7, center = true);
    translate([0, -75, 0]) cube([10, 120, 7], center = true);
    translate([0, 90, 5]) linear_extrude(3) rotate([0, 0, 0])
      text("KinkyCastle.XXX", halign = "center", valign = "center", size = 8);

    translate([0, 20, 0]) cube([100, 2, 20], center = true);

    translate([0, 30, 0]) female(locked = true);
  }
  translate([0, 30, 0]) male();
  translate([0, 17, 0]) cube([40, 5, 12], center = true);
}

module joinerNAngle(n)
{
  assert(n >= 2);

  extra = n < 6 ? 0 : n * 5 -25;

  difference()
  {
    for(i = [0:360 / n:359]) rotate([0, 0, i])
    {
      translate([0, -80 -extra, 0]) link(true, false, false);

      difference()
      {
        translate([0, -16 -extra / 2,]) face(44 + extra);
        translate([0, -35 -extra, 0]) female();
      }
    }
    translate([0, 0, 5]) linear_extrude(3) rotate([0, 0, 45])
      text("KinkyCastle.XXX", halign = "center", valign = "center", size = 6);
  }
}

veryWideLinks = [-120, -30, 30, 120];

module veryWideStrap(additionalPannels = 6)
{

  for(i = [0:1:additionalPannels])
  {
    translate([0, 50 * i, 0]) union()
    {
      for(l = veryWideLinks) translate([l, i == 0 ?-14:0, 0])
        rotate([0, 0, i == 0 ? 180:0]) male();
      difference()
      {
        translate([0, 18, 0]) face(45, 300);
        if(i) for(l = veryWideLinks) translate([l, 0, 0]) female(true);

        translate([-75, 0, 0]) cube([60, 100, 3], center = true);
        translate([75, 0, 0]) cube([60, 100, 3], center = true);

        translate([0, 22, 0]) cube([80, 25, 9], center = true);

        translate([125, 22, 0]) cube([35, 25, 9], center = true);
        translate([-125, 22, 0]) cube([35, 25, 9], center = true);
      }
    }
  }

  for(l = veryWideLinks) translate([l, additionalPannels * 50 + 50, 0]) male();
}

module veryWideJoiner()
{
  $fn = $preview ? 24 : 60;
  fn2 = $preview ? 12 : 30;
  difference()
  {
    translate([0, 18, 0]) face(45, 300);
    for(l = veryWideLinks) translate([l, 35, 0]) rotate([0, 0, 180])
    {
      female(true);
      hull()
      {
        translate([0, 2, 0]) scale([3, 1, 1]) sphere(d = 6.1, $fn = fn2);
        translate([0, -2, 10]) scale([3, 1, 1]) sphere(d = 6.1, $fn = fn2);
      }
      hull()
      {
        translate([0, 2, 0]) scale([3, 1, 1]) sphere(d = 6.1, $fn = fn2);
        scale([3, 1, 1]) sphere(d = 6.1, $fn = fn2);
      }
    }
    for(l = veryWideLinks) translate([l, 0, 0])
    {
      female(true);
      hull()
      {
        translate([0, 2, 0]) scale([3, 1, 1]) sphere(d = 6.1, $fn = fn2);
        translate([0, -2, 10]) scale([3, 1, 1]) sphere(d = 6.1, $fn = fn2);
      }
      hull()
      {
        translate([0, 2, 0]) scale([3, 1, 1]) sphere(d = 6.1, $fn = fn2);
        scale([3, 1, 1]) sphere(d = 6.1, $fn = fn2);
      }
    }
    translate([-75, 0, 0]) cube([60, 100, 3], center = true);
    translate([75, 0, 0]) cube([60, 100, 3], center = true);

    for(x = [120, 0, -120]) translate([x, 18, 0])
    {
      cylinder(d = 6.5, h = 15, center = true);
      translate([0, 0, 5]) cylinder(d = 16.5, h = 15, center = true);
    }

    translate([144, 18, 0]) rotate([0, 0, 90]) female(false);
    translate([-144, 18, 0]) rotate([0, 0, -90]) female(false);
  }
}

//veryWideStrap(6);

//veryWideJoiner();
//female(false);
//joinerNAngle(6);
//joiner2();
//male();
//strap(7);
//joiner2x9();
//link();
//joinerLimb(2);
//joinerTits();
//joinerLimb(1);
//strap(4);
//female(false);
