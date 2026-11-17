"""Fresh bounded downward projection for formerly unresolved camera seeds."""
import math

def select_camera_seed(pf,camera):
 candidates={}
 for i in range(101):
  q=list(pf.snap_point([camera[0],camera[1]-.02*i,camera[2]]))
  if not all(math.isfinite(v) for v in q) or not pf.is_navigable(q):continue
  horizontal=math.hypot(q[0]-camera[0],q[2]-camera[2]);drop=camera[1]-q[1]
  if horizontal>=.5 or not 0<=drop<=2:continue
  if math.dist(q,list(pf.snap_point(q)))>1e-5:continue
  candidates[tuple(q)]=(horizontal,-drop,q)
 return min(candidates.values())[2] if candidates else None
