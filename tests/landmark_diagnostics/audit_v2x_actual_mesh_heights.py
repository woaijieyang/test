"""Compare hypothetical compact-span centers against existing final native mesh, CPU only."""
import os,sys,json,struct,ast,math,datetime
from pathlib import Path
assert os.environ.get("CASE1_PROTECTION")
os.environ["CUDA_VISIBLE_DEVICES"]="";os.environ["OPENBLAS_NUM_THREADS"]="1";os.environ["OMP_NUM_THREADS"]="1";os.nice(15)
R=Path.cwd();sys.path[:0]=[str(R/"scripts"),str(R/"tests/landmark_diagnostics")]
import numpy as np,psutil,habitat_sim
from workspace import atomic_json,digest
from swept_cylinder_reference import triangle_linear_sweep_distance
from cylinder_contact_height import contact_height_range
cpu=psutil.cpu_percent(interval=1,percpu=True);os.sched_setaffinity(0,[min(sorted(os.sched_getaffinity(0))[:64],key=lambda c:cpu[c])])
O=R/"outputs/landmark-connectivity/v2x-fine-stage-graphs-cpu-v1";S=O/"erosion-connectors-avoid-support-v1/whole-path-source-audit-v1";D=O/"actual-mesh-height-audit-v1";D.mkdir(exist_ok=False)
atomic_json(D/"process.json",{"pid":os.getpid(),"start_ticks":Path("/proc/self/stat").read_text().rsplit(")",1)[1].split()[19]})
profile=R/"data/derived/navmeshes/landmark-v2x-fine05-grounded-v20/profile.json";asset=json.loads(profile.read_text())["assets"]["mp3d/V2XKFyX4ASd/V2XKFyX4ASd.glb"];assert digest(asset["navmesh_path"])==asset["navmesh_sha256"]
pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(asset["navmesh_path"])
raw=(O/"native-1.bin").read_bytes();nv,nt=struct.unpack("<ii",raw[:8]);verts=np.frombuffer(raw,dtype="<f4",count=nv*3,offset=8).reshape(nv,3);inds=np.frombuffer(raw,dtype="<i4",count=nt*3,offset=8+12*nv).reshape(nt,3);tri=verts[inds].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1)
helper=R/"tests/landmark_diagnostics/audit_v2x_alternative_path_geometry.py";node=[n for n in ast.parse(helper.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=="collision"];assert len(node)==1;exec(compile(ast.Module(body=node,type_ignores=[]),str(helper),"exec"),globals())
v=json.loads((S/"validation.json").read_text());groups=[json.loads((S/(g["group_id"]+".json")).read_text()) for g in v["groups"]];original={r["span_id"]:r for g in groups for r in g["points"]};rows=[]
try:
 for key,r in original.items():
  p=np.array(r["position"]);q=np.array(pf.snap_point(p),dtype=float);finite=bool(np.all(np.isfinite(q)));xz=float(np.linalg.norm((q-p)[[0,2]])) if finite else None;dy=float(q[1]-p[1]) if finite else None
  same=finite and xz<=1e-5 and abs(dy)<=.5
  check=collision(q,q,True) if same else None
  rows.append({"span_id":key,"span_position":p.tolist(),"eroded":r["removed_by_erosion"],"span_contacts":r["contact_count"],"native_snap_position":q.tolist() if finite else None,"horizontal_projection":xz,"vertical_difference":dy,"same_xz_query":same,"native_point_contacts":check["contact_count"] if check else None,"contacts":check["contacts"] if check else None})
 atomic_json(D/"points.json",rows)
 same=[r for r in rows if r["same_xz_query"]];transitions={}
 for r in same:
  key=("contact" if r["span_contacts"] else "clear")+"->"+("contact" if r["native_point_contacts"] else "clear");transitions[key]=transitions.get(key,0)+1
 d={"status":"COMPLETE_NATIVE_HEIGHT_DIAGNOSTIC","tasks":66,"points":len(rows),"same_xz_points":len(same),"other_projections":len(rows)-len(same),"same_xz_contact_transitions":transitions,"same_xz_y_delta_min":min(r["vertical_difference"] for r in same),"same_xz_y_delta_max":max(r["vertical_difference"] for r in same),"eroded_same_xz":sum(r["eroded"] for r in same),"native_mesh_sha256":asset["navmesh_sha256"],"profile_sha256":digest(profile),"native_input_sha256":digest(O/"native-1.bin"),"parent_validation_sha256":digest(S/"validation.json"),"script_sha256":digest(__file__),"helper_sha256":digest(helper),"limits":"Existing rejected fine05 candidate mesh. snap_point queried without accepting horizontal projections; sameXZ numerical criterion only diagnoses heights. No motion run, no restoration of erased cells, no changed thresholds/coordinates/profile. Compact-span path is not final Detour path.","time":datetime.datetime.now().isoformat()};atomic_json(D/"validation.json",d);atomic_json(D/"state.json",{"status":"COMPLETE"})
except Exception as e:atomic_json(D/"state.json",{"status":"FAILED","error":repr(e)});raise
