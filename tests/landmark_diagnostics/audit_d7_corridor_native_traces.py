"""Recompute strict source clearance of immutable actual native traces near theD7corridor."""
import os,sys,json,gzip,struct,datetime,collections,math
from pathlib import Path
assert os.environ.get("CASE1_PROTECTION");os.environ["CUDA_VISIBLE_DEVICES"]="";os.environ["OPENBLAS_NUM_THREADS"]="1";os.environ["OMP_NUM_THREADS"]="1";os.nice(15)
R=Path.cwd();sys.path[:0]=[str(R/"scripts"),str(R/"tests/landmark_diagnostics")]
from workspace import atomic_json,digest
from swept_cylinder_reference import triangle_linear_sweep_distance
from cylinder_contact_height import contact_height_range
import numpy as np,psutil
u=psutil.cpu_percent(interval=1,percpu=True);os.sched_setaffinity(0,[min(sorted(os.sched_getaffinity(0))[:64],key=lambda i:u[i])])
B=R/"outputs/landmark-connectivity";O=B/"d7-fine-stage-v1";D=O/"actual-corridor-clearance-v1";D.mkdir(exist_ok=False);reg=set(json.loads((B/"D7-grounded-fine05-v1/static-transition-audit.json").read_text())["regressed"]);audit_path=B/"full-native-source-exact-v1/scenes/D7N2EKCX4Sj/validation.json";old=json.loads(audit_path.read_text());rows=[r for r in old["rows"] if r["task_key"] in reg];assert len(rows)==15
raw=(O/"native-1.bin").read_bytes();assert digest(O/"native-1.bin")==old["native_geometry_sha256"];nv,nt=struct.unpack("<ii",raw[:8]);vv=np.frombuffer(raw,dtype="<f4",count=nv*3,offset=8).reshape(nv,3);ii=np.frombuffer(raw,dtype="<i4",count=nt*3,offset=8+nv*12).reshape(nt,3);tri=vv[ii].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1)
path=json.loads((O/"preerosion-connection-v1/validation.json").read_text())["path"];pos=np.array([r["position"] for r in path]);bounds_lo=pos.min(axis=0)-[.25,.5,.25];bounds_hi=pos.max(axis=0)+[.25,.5,.25];cache={}
def inspect(a,b):
 key=tuple(sorted((tuple(a),tuple(b))))
 if key in cache:return cache[key]
 a=np.array(a);b=np.array(b);lower=np.minimum(a,b)+[-.2,1e-5,-.2];upper=np.maximum(a,b)+[.2,1.5,.2];ids=np.flatnonzero(np.all(hi>=lower,axis=1)&np.all(lo<=upper,axis=1));hits=[];best=math.inf;best_id=None
 for j in ids:
  distance=triangle_linear_sweep_distance(tri[j],a,b)
  if distance<best:best=float(distance);best_id=int(j)
  if distance<.1-1e-6:hits.append({"triangle":int(j),"distance":float(distance)})
 result={"contacts":hits,"minimum_swept_radial_distance_within_point2m_broadphase":best if math.isfinite(best) else None,"nearest_triangle":best_id,"minimum_distance_is_lower_bounded_by_point2_if_no_nearby_triangle":not math.isfinite(best)};cache[key]=result;return result
reports=[]
for row in rows:
 assert digest(row["trace_path"])==row["trace_sha256"];trace=json.loads(gzip.decompress(Path(row["trace_path"]).read_bytes()));assert trace["task_key"]==row["task_key"] and len(trace["positions"])==len(trace["actions"])+1;segments=[]
 for i,(a,b) in enumerate(zip(trace["positions"],trace["positions"][1:])):
  if not (np.all(np.array(a)>=bounds_lo) and np.all(np.array(a)<=bounds_hi) and np.all(np.array(b)>=bounds_lo) and np.all(np.array(b)<=bounds_hi)):continue
  if a==b:continue
  segments.append({"action_index":i,"action":trace["actions"][i],"start":a,"end":b,**inspect(a,b)})
 reports.append({"task_key":row["task_key"],"whole_trace_original_status":row["status"],"selected_moving_segments":segments,"selected_contact_segments":sum(bool(r["contacts"]) for r in segments),"trace_path":row["trace_path"],"trace_sha256":row["trace_sha256"],"stored_native_replay_error":trace["max_replay_error"]})
 atomic_json(D/(row["task_key"].replace(":","-")+".json"),reports[-1])
atomic_json(D/"validation.json",{"status":"COMPLETE_LOCAL_ACTUAL_TRACE_SOURCE_AUDIT_NOT_ROUTE_ACCEPTANCE","tasks":15,"selection_bbox_min":bounds_lo.tolist(),"selection_bbox_max":bounds_hi.tolist(),"selected_moving_segments":sum(len(r["selected_moving_segments"]) for r in reports),"unique_sweep_queries":len(cache),"tasks_with_selected_contact_segments":sum(r["selected_contact_segments"]>0 for r in reports),"tasks_with_nonempty_clear_selected_segments":sum(bool(r["selected_moving_segments"]) and not r["selected_contact_segments"] for r in reports),"minimum_finite_swept_distance":min((r["minimum_swept_radial_distance_within_point2m_broadphase"] for r in cache.values() if r["minimum_swept_radial_distance_within_point2m_broadphase"] is not None),default=None),"original_audit_sha256":digest(audit_path),"native_geometry_sha256":digest(O/"native-1.bin"),"script_sha256":digest(__file__),"limits":"Actualstoredoriginalv11coarser-mesh motions rechecked againstsame nativegeometry andstrict straightcylinder. Localbbox selectedbeforechecking. No newepisode/replay, no whole-route success or fine-mesh pathclaim. All original failures retained.","time":datetime.datetime.now().isoformat()});print(json.loads((D/"validation.json").read_text()))
