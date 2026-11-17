"""Audit all voxel connector centers and linear edges; no navmesh edits or motion claims."""
import os,sys,json,struct,math,datetime
from pathlib import Path
assert os.environ.get("CASE1_PROTECTION")
os.environ["CUDA_VISIBLE_DEVICES"]=""
os.environ["OPENBLAS_NUM_THREADS"]="1"
os.environ["OMP_NUM_THREADS"]="1"
os.nice(15)
R=Path.cwd();sys.path[:0]=[str(R/"scripts"),str(R/"tests/landmark_diagnostics")]
import numpy as np,psutil
from workspace import atomic_json,digest
from swept_cylinder_reference import triangle_linear_sweep_distance
from cylinder_contact_height import contact_height_range
cpu=psutil.cpu_percent(interval=1,percpu=True)
os.sched_setaffinity(0,[min(sorted(os.sched_getaffinity(0))[:64],key=lambda c:cpu[c])])
O=R/"outputs/landmark-connectivity/v2x-fine-stage-graphs-cpu-v1"
S=O/"erosion-connectors-avoid-support-v1"
D=S/"whole-path-source-audit-v1";D.mkdir(exist_ok=False)
atomic_json(D/"process.json",{"pid":os.getpid(),"start_ticks":Path("/proc/self/stat").read_text().rsplit(")",1)[1].split()[19]})
v=json.loads((S/"validation.json").read_text())
assert v["tasks"]==66 and v["unique_removed_centers"]==5
raw=(O/"native-1.bin").read_bytes();nv,nt=struct.unpack("<ii",raw[:8])
verts=np.frombuffer(raw,dtype="<f4",count=nv*3,offset=8).reshape(nv,3)
inds=np.frombuffer(raw,dtype="<i4",count=nt*3,offset=8+12*nv).reshape(nt,3)
tri=verts[inds].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1)
point_cache={};edge_cache={};support_cache={}
def collision(a,b,point=False):
 a=np.array(a);b=np.array(b)
 lower=np.minimum(a,b)+[-.1,1e-5,-.1];upper=np.maximum(a,b)+[.1,1.5,.1]
 ids=np.flatnonzero(np.all(hi>=lower,axis=1)&np.all(lo<=upper,axis=1))
 hits=[]
 for j in ids:
  dist=triangle_linear_sweep_distance(tri[j],a,b)
  if dist<.1-1e-6:
   r={"triangle":int(j),"radial_distance":dist}
   if point:r["contact_height_range"]=contact_height_range(tri[j],a)
   hits.append(r)
 return {"candidate_triangles":len(ids),"contacts":hits,"contact_count":len(hits)}
def support(p):
 p=np.array(p);rows=[]
 for i in range(9):
  q=p.copy()
  if i:q[[0,2]]+=.1*np.array([math.cos((i-1)*math.pi/4),math.sin((i-1)*math.pi/4)])
  ids=np.flatnonzero((lo[:,0]<=q[0])&(hi[:,0]>=q[0])&(lo[:,2]<=q[2])&(hi[:,2]>=q[2])&(lo[:,1]<=q[1]+1e-5))
  found=[]
  for j in ids:
   t=tri[j];u=t[1]-t[0];w=t[2]-t[0];normal=np.cross(u,w);norm=np.linalg.norm(normal)
   if not norm or abs(normal[1])/norm<math.cos(math.pi/4):continue
   matrix=np.array([[u[0],w[0]],[u[2],w[2]]]);det=np.linalg.det(matrix)
   if abs(det)<1e-14:continue
   uv=np.linalg.solve(matrix,q[[0,2]]-t[0,[0,2]])
   if min(uv)<-1e-9 or sum(uv)>1+1e-9:continue
   y=float(t[0,1]+uv[0]*u[1]+uv[1]*w[1])
   if y<=q[1]+1e-5:found.append((y,int(j)))
  top=max(found) if found else None
  rows.append({"sample":i,"xz":q[[0,2]].tolist(),"source_y":top[0] if top else None,"triangle":top[1] if top else None,"vertical_gap":float(q[1]-top[0]) if top else None})
 center=rows[0]["source_y"]
 return {"position":p.tolist(),"samples":rows,"max_source_ground_drop_from_center":max((center-r["source_y"] for r in rows if center is not None and r["source_y"] is not None),default=None),"missing_support_samples":sum(r["source_y"] is None for r in rows)}
reports=[]
try:
 for group in v["groups"]:
  source=S/(group["group_id"]+".json");assert digest(source)==group["receipt_sha256"]
  g=json.loads(source.read_text());path=g["path"];points=[];edges=[]
  for n in path:
   key=n["span_id"]
   if key not in point_cache:point_cache[key]={**n,**collision(n["position"],n["position"],True)}
   points.append(point_cache[key])
   if n["removed_by_erosion"] and key not in support_cache:support_cache[key]=support(n["position"])
  for a,b in zip(path,path[1:]):
   key=tuple(sorted([a["span_id"],b["span_id"]]))
   if key not in edge_cache:edge_cache[key]={"spans":list(key),"start":a["position"],"end":b["position"],**collision(a["position"],b["position"])}
   edges.append(edge_cache[key])
  row={"group_id":g["group_id"],"task_keys":g["task_keys"],"path_points":len(points),"path_edges":len(edges),"source_contact_points":sum(r["contact_count"]>0 for r in points),"source_contact_edges":sum(r["contact_count"]>0 for r in edges),"continuous_only_edges":sum(e["contact_count"]>0 and not a["contact_count"] and not b["contact_count"] for e,a,b in zip(edges,points,points[1:])),"points":points,"edges":edges,"source_receipt_sha256":digest(source)}
  atomic_json(D/(g["group_id"]+".json"),row)
  reports.append({k:row[k] for k in ["group_id","path_points","path_edges","source_contact_points","source_contact_edges","continuous_only_edges"]})
  atomic_json(D/"state.json",{"status":"RUNNING","groups_complete":len(reports)})
 atomic_json(D/"removed-cell-support.json",{"records":[{"span_id":k,**r} for k,r in support_cache.items()],"limits":"Nine vertical rays with absolute source-normal slope at most45 degrees are diagnostic only; no full-disk support certificate or changed motion criterion."})
 atomic_json(D/"validation.json",{"status":"COMPLETE_DIAGNOSTIC_NOT_REPAIR","tasks":66,"groups":reports,"unique_points":len(point_cache),"unique_edges":len(edge_cache),"contact_points":sum(r["contact_count"]>0 for r in point_cache.values()),"contact_edges":sum(r["contact_count"]>0 for r in edge_cache.values()),"native_input_sha256":digest(O/"native-1.bin"),"parent_validation_sha256":digest(S/"validation.json"),"script_sha256":digest(__file__),"sweep_helper_sha256":digest(R/"tests/landmark_diagnostics/swept_cylinder_reference.py"),"projection_helper_sha256":digest(R/"tests/landmark_diagnostics/projected_distance_reference.py"),"limits":"Voxel centers/straight segments are hypothetical diagnostics, not executed native actions. Same1.5m height,.1m radius,1e-5 foot and1e-6 radial tolerance. No cells restored, no body/gate changed; all66 remain unresolved and all33954 retained.","time":datetime.datetime.now().isoformat()})
 atomic_json(D/"state.json",{"status":"COMPLETE"})
except Exception as e:atomic_json(D/"state.json",{"status":"FAILED","error":repr(e)});raise
