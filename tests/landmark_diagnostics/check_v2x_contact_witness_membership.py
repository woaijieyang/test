"""Independently decode and verify stored point-contact witnesses, not all clear geometry."""
import json,struct,math,hashlib
from pathlib import Path
P=Path("outputs/landmark-connectivity/v2x-fine-stage-graphs-cpu-v1/erosion-connectors-avoid-support-v1/whole-path-source-audit-v1")
receipt=json.loads((P/"positive-witness-membership.json").read_text())
assert hashlib.sha256((P/"validation.json").read_bytes()).hexdigest()==receipt["parent_validation_sha256"]
rows=[json.loads(f.read_text()) for f in P.glob("*.json") if len(f.stem)==16]
assert len(rows)==4
points={r["span_id"]:r for g in rows for r in g["points"]}
raw=(P.parents[1]/"native-1.bin").read_bytes();nv,nt=struct.unpack_from("<ii",raw)
def vert(i):return struct.unpack_from("<fff",raw,8+12*i)
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def sub(a,b):return [x-y for x,y in zip(a,b)]
checked=0;max_residual=0.
for r in points.values():
 foot=r["position"]
 for h in r["contacts"]:
  w=h.get("contact_height_range")
  if not w:continue
  ids=struct.unpack_from("<iii",raw,8+12*nv+12*h["triangle"]);a,b,c=[vert(i) for i in ids];u=sub(b,a);v=sub(c,a);den=dot(u,u)*dot(v,v)-dot(u,v)**2
  for name in ["minimum_point","maximum_point"]:
   x=w[name];z=sub(x,a);alpha=(dot(v,v)*dot(z,u)-dot(u,v)*dot(z,v))/den;beta=(dot(u,u)*dot(z,v)-dot(u,v)*dot(z,u))/den
   residual=math.sqrt(sum((a[k]+alpha*u[k]+beta*v[k]-x[k])**2 for k in range(3)));max_residual=max(max_residual,residual)
   radial=math.hypot(x[0]-foot[0],x[2]-foot[2]);height=x[1]-foot[1]
   assert min(alpha,beta,1-alpha-beta)>=-1e-7 and residual<=1e-7
   assert radial<=.1-1e-6+1e-8 and 1e-5-1e-8<=height<=1.5+1e-8
   checked+=1
assert checked==receipt["witnesses_checked"]==1800
assert len({k for g in rows for k in g["task_keys"]})==receipt["unique_task_keys"]==66
assert abs(max_residual-receipt["maximum_triangle_residual"])<1e-15
print(json.dumps({"status":"PASS","point_contact_witnesses":checked,"tasks":66,"scope":"positive point witnesses only; no independent negative/sweep certification"}))
