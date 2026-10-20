"""Classify stored native-mesh point contacts by source-triangle slope and center coverage."""
from pathlib import Path
import json,struct,math,hashlib,collections
O=Path("outputs/landmark-connectivity/v2x-fine-stage-graphs-cpu-v1")
D=O/"actual-mesh-height-audit-v1"
raw=(O/"native-1.bin").read_bytes();nv,nt=struct.unpack_from("<ii",raw)
rows=json.loads((D/"points.json").read_text());out=[]
def dot(a,b):return sum(x*y for x,y in zip(a,b))
for r in rows:
 if not r["same_xz_query"] or not r["native_point_contacts"]:continue
 p=r["native_snap_position"];hits=[]
 for h in r["contacts"]:
  ids=struct.unpack_from("<iii",raw,8+12*nv+12*h["triangle"])
  a,b,c=[struct.unpack_from("<fff",raw,8+12*i) for i in ids]
  u=[b[k]-a[k] for k in range(3)];v=[c[k]-a[k] for k in range(3)]
  n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]];length=math.sqrt(dot(n,n));slope=math.degrees(math.acos(min(1,abs(n[1])/length))) if length else None
  det=u[0]*v[2]-u[2]*v[0];center=False;source_y=None
  if abs(det)>1e-14:
   dx=p[0]-a[0];dz=p[2]-a[2];alpha=(dx*v[2]-dz*v[0])/det;beta=(u[0]*dz-u[2]*dx)/det
   center=min(alpha,beta,1-alpha-beta)>=-1e-9
   if center:source_y=a[1]+alpha*u[1]+beta*v[1]
  hits.append({"triangle":h["triangle"],"absolute_normal_slope_degrees":slope,"xz_contains_center":center,"plane_at_center_minus_foot":source_y-p[1] if source_y is not None else None,"maximum_actual_contact_height":h["contact_height_range"]["maximum_height"] if h.get("contact_height_range") else None})
 out.append({"span_id":r["span_id"],"native_position":p,"contacts":hits})
summary={"points":len(out),"points_with_slope_le45_contacts":sum(any(h["absolute_normal_slope_degrees"] is not None and h["absolute_normal_slope_degrees"]<=45 for h in r["contacts"]) for r in out),"points_with_slope_gt45_contacts":sum(any(h["absolute_normal_slope_degrees"] is not None and h["absolute_normal_slope_degrees"]>45 for h in r["contacts"]) for r in out),"points_with_contacting_triangle_under_center":sum(any(h["xz_contains_center"] for h in r["contacts"]) for r in out),"max_contact_height":max(h["maximum_actual_contact_height"] for r in out for h in r["contacts"] if h["maximum_actual_contact_height"] is not None)}
receipt={"summary":summary,"records":out,"parent_sha256":hashlib.sha256((D/"points.json").read_bytes()).hexdigest(),"script_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),"limits":"Triangle slope is geometric, not semantic floor/wall labeling. Categories overlap. Native mesh point queries, not actual motion. No contact ignored or corrected."}
f=D/"contact-surface-classification.json";assert not f.exists();f.write_text(json.dumps(receipt,indent=2)+"\n");print(summary)
