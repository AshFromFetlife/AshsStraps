include <core.scad>

N = 1;

if (N == 1)
{
  corsetHalf();
}
else
{
  mirror([0,1,0]){corsetHalf();}
}
