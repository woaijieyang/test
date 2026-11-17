"""Single-voxel source-height diagnosis of hypothetical graph paths, not navmesh repair."""
import os,sys,json,struct,math,ast,datetime
from pathlib import Path
assert os.environ.get("CASE1_PROTECTION")
os.environ["CUDA_VISIBLE_DEVICES"]="";os.environ["OPENBLAS_NUM_THREADS"]="1";os.environ["OMP_NUM_THREADS"]="1";os.nice(15)
R=Path.cwd();sys.path[:0]=[str(R/"scripts"),str(R/"tests/landmark_diagnostics")]
import numpy as np,psutil
from workspace import atomic_json,digest
from swept_cylinder_reference import triangle_linear_sweep_distance
from cylinder_contact_height import contact_height_range
cpu=psutil.cpu_percent(interval=1,percpu=True);os.sched_setaffinity(0,[min(sorted(os.sched_getaffinity(0))[:64],key=lambda c:cpu[c])])
O=R/"outputs/landmark-connectivity/v2x-fine-stage-graphs-cpu-v1"
S=O/"erosion-connectors-avoid-support-v1/whole-path-source-audit-v1"
D=O/"voxel-height-alignment-v1";D.mkdir(exist_ok=False)
atomic_json(D/"process.json",{"pid":os.getpid(),"start_ticks":Path("/proc/self/stat").read_text().rsplit(")",1)[1].split()[19]})
raw=(O/"native-1.bin").read_bytes();nv,nt=struct.unpack("<ii",raw[:8]);verts=np.frombuffer(raw,dtype="<f4",count=nv*3,offset=8).reshape(nv,3);inds=np.frombuffer(raw,dtype="<i4",count=nt*3,offset=8+12*nv).reshape(nt,3);tri=verts[inds].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1)
helper=R/"tests/landmark_diagnostics/audit_v2x_alternative_path_geometry.py"
node=[n for n in ast.parse(helper.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=="collision"];assert len(node)==1
exec(compile(ast.Module(body=node,type_ignores=[]),str(helper),"exec"),globals())
config=json.loads((O/"validation.json").read_text())["native_build_config"];ch=config[1]
validation=json.loads((S/"validation.json").read_text());groups=[json.loads((S/(g["group_id"]+".json")).read_text()) for g in validation["groups"]]
original={r["span_id"]:r for g in groups for r in g["points"]};assert len(original)==125
points={};edge_cache={}
def floor_candidates(p):
 p=np.array(p);ids=np.flatnonzero((lo[:,0]<=p[0])&(hi[:,0]>=p[0])&(lo[:,2]<=p[2])&(hi[:,2]>=p[2])&(lo[:,1]<=p[1]+ch)&(hi[:,1]>=p[1]-ch));found=[]
 for j in ids:
  t=tri[j];u=t[1]-t[0];v=t[2]-t[0];normal=np.cross(u,v);norm=np.linalg.norm(normal)
  if not norm or abs(normal[1])/norm<math.cos(math.pi/4):continue
  matrix=np.array([[u[0],v[0]],[u[2],v[2]]])
  if abs(np.linalg.det(matrix))<1e-14:continue
  uv=np.linalg.solve(matrix,p[[0,2]]-t[0,[0,2]])
  if min(uv)<-1e-9 or sum(uv)>1+1e-9:continue
  y=float(t[0,1]+uv[0]*u[1]+uv[1]*v[1])
  if abs(y-p[1])<=ch:found.append({"triangle":int(j),"source_y":y,"delta_y":y-float(p[1]),"barycentric":[float(1-sum(uv)),float(uv[0]),float(uv[1])]})
 return sorted(found,key=lambda r:(abs(r["delta_y"]),r["triangle"]))
try:
 for key,r in original.items():
  candidates=floor_candidates(r["position"]);q=list(r["position"])
  if candidates:q[1]=candidates[0]["source_y"]
  check=collision(q,q,True)
  points[key]={"span_id":key,"original_position":r["position"],"original_contact_count":r["contact_count"],"source_candidates":candidates,"selected_position":q,"has_source_support_in_one_voxel":bool(candidates),"corrected_contact_count":check["contact_count"],"corrected_contacts":check["contacts"],"removed_by_erosion":r["removed_by_erosion"]}
 atomic_json(D/"points.json",list(points.values()))
 reports=[]
 for g in groups:
  edges=[]
  for a,b in zip(g["points"],g["points"][1:]):
   key=tuple(sorted((a["span_id"],b["span_id"])))
   if key not in edge_cache:
    aa=points[a["span_id"]]["selected_position"];bb=points[b["span_id"]]["selected_position"]
    edge_cache[key]={"spans":list(key),"start":aa,"end":bb,**collision(aa,bb)}
   edges.append(edge_cache[key])
  report={"group_id":g["group_id"],"task_keys":g["task_keys"],"edges":edges,"contact_edges":sum(r["contact_count"]>0 for r in edges)};atomic_json(D/(g["group_id"]+".json"),report);reports.append({k:report[k] for k in ["group_id","contact_edges"]})
 transitions={}
 for p in points.values():
  key=("contact" if p["original_contact_count"] else "clear")+"->"+("contact" if p["corrected_contact_count"] else "clear")
  transitions[key]=transitions.get(key,0)+1
 atomic_json(D/"validation.json",{"status":"COMPLETE_DIAGNOSTIC_NOT_REPAIR","tasks":66,"points":len(points),"points_with_source_floor":sum(p["has_source_support_in_one_voxel"] for p in points.values()),"point_transitions":transitions,"source_point_contacts":sum(p["corrected_contact_count"]>0 for p in points.values()),"source_edge_contacts":sum(e["contact_count"]>0 for e in edge_cache.values()),"edges":len(edge_cache),"groups":reports,"height_query_bound":ch,"native_input_sha256":digest(O/"native-1.bin"),"parent_validation_sha256":digest(S/"validation.json"),"script_sha256":digest(__file__),"helper_sha256":digest(helper),"limits":"Closest source support at identical XZ within one native vertical voxel, slope<=45. This is a hypothetical source-height diagnostic, not navigable positions or executed actions. No navmesh/annotation/body/threshold changes. All66 unresolved and33954 retained.","time":datetime.datetime.now().isoformat()})
 atomic_json(D/"state.json",{"status":"COMPLETE"})
except Exception as e:atomic_json(D/"state.json",{"status":"FAILED","error":repr(e)});raise
