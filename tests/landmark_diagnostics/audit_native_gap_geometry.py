"""Full existing gap-centerline audit against verified native inputs; no simulated motion."""
import os,sys,json,struct,datetime,argparse,collections
from pathlib import Path
assert os.environ.get("CASE1_PROTECTION");os.environ["CUDA_VISIBLE_DEVICES"]="";os.environ["OPENBLAS_NUM_THREADS"]="1";os.environ["OMP_NUM_THREADS"]="1";os.nice(15)
P=argparse.ArgumentParser();P.add_argument("--shard",type=int,required=True);P.add_argument("--shards",type=int,required=True);P.add_argument("--cpu",type=int,required=True);args=P.parse_args();assert 0<=args.shard<args.shards<=4;assert args.cpu in os.sched_getaffinity(0);os.sched_setaffinity(0,[args.cpu])
R=Path.cwd();sys.path[:0]=[str(R/"scripts"),str(R/"tests/landmark_diagnostics")]
from workspace import atomic_json,digest
from swept_cylinder_reference import triangle_linear_sweep_distance
from cylinder_contact_height import contact_height_range
import numpy as np
O=R/"outputs/landmark-connectivity/native-gap-geometry-v1";manifest=json.loads((O/"input.json").read_text());rows=manifest["scenes"][args.shard::args.shards];worker=O/("worker-"+str(args.shard));worker.mkdir(exist_ok=False)
atomic_json(worker/"process.json",{"pid":os.getpid(),"start_ticks":Path("/proc/self/stat").read_text().rsplit(")",1)[1].split()[19],"cpu":args.cpu})
try:
 for number,row in enumerate(rows):
  assert digest(row["input_path"])==row["input_sha256"];legacy=json.loads(Path(row["input_path"]).read_text());g=row["native_geometry"];assert digest(g["native_geometry_path"])==g["native_geometry_sha256"]
  raw=Path(g["native_geometry_path"]).read_bytes();nv,nt=struct.unpack("<ii",raw[:8]);vertices=np.frombuffer(raw,dtype="<f4",count=nv*3,offset=8).reshape(nv,3);indices=np.frombuffer(raw,dtype="<i4",count=nt*3,offset=8+12*nv).reshape(nt,3);tri=vertices[indices].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1);point_cache={};edge_cache={}
  def check(a,b,point):
   a=np.asarray(a,dtype=float);b=np.asarray(b,dtype=float);low=np.minimum(a,b)+[-.1,1e-5,-.1];high=np.maximum(a,b)+[.1,1.5,.1];ids=np.flatnonzero(np.all(hi>=low,axis=1)&np.all(lo<=high,axis=1));hits=[]
   for j in ids:
    dist=triangle_linear_sweep_distance(tri[j],a,b)
    if dist<.1-1e-6:
     hit={"triangle":int(j),"radial_distance":float(dist)}
     if point:hit["height_range"]=contact_height_range(tri[j],a)
     hits.append(hit)
   return {"contacts":hits,"count":len(hits)}
  pairs=[]
  for pair in legacy["pairs"]:
   samples=[]
   for sample in pair["samples"]:
    pos=sample["position"];key=tuple(pos)
    if key not in point_cache:point_cache[key]=check(pos,pos,True)
    samples.append({"position":pos,"fraction":sample["fraction"],**point_cache[key]})
   edges=[]
   for a,b in zip(samples,samples[1:]):
    key=tuple(sorted((tuple(a["position"]),tuple(b["position"]))))
    if key not in edge_cache:edge_cache[key]=check(a["position"],b["position"],False)
    edges.append({"start":a["position"],"end":b["position"],**edge_cache[key]})
   heights=[h["height_range"]["maximum_height"] for r in samples for h in r["contacts"] if h.get("height_range")]
   pairs.append({"component_pair":pair["component_pair"],"nodes":pair["nodes"],"vertex_gap":pair["vertex_gap"],"samples":samples,"edges":edges,"contact_samples":sum(r["count"]>0 for r in samples),"contact_edges":sum(r["count"]>0 for r in edges),"continuous_only_edges":sum(e["count"]>0 and not a["count"] and not b["count"] for e,a,b in zip(edges,samples,samples[1:])),"maximum_actual_point_contact_height":max(heights) if heights else None,"legacy_samples_with_high_contact":pair["samples_with_high_contact"],"legacy_samples_without_support_within_0point3m":pair["samples_without_support_within_0point3m"],"point_contact_over_0point3m":any(h>.3 for h in heights)})
  dest=O/"scenes"/(row["scene"]+".json");assert not dest.exists()
  atomic_json(dest,{"scene":row["scene"],"pairs":pairs,"unique_points":len(point_cache),"unique_edges":len(edge_cache),"native_geometry_sha256":g["native_geometry_sha256"],"input_sha256":row["input_sha256"],"navmesh_sha256":row["navmesh_sha256"],"script_sha256":digest(__file__),"sweep_helper_sha256":digest(R/"tests/landmark_diagnostics/swept_cylinder_reference.py"),"height_helper_sha256":digest(R/"tests/landmark_diagnostics/cylinder_contact_height.py"),"limits":"Existing diagnostic centerline samples, not actual agent motion or exhaustive alternate routes. All collision heights count as contacts;0.3m category is descriptive only. Legacy support flags not revalidated by this body audit; source and predicate changes cannot be attributed separately.","time":datetime.datetime.now().isoformat()})
  atomic_json(worker/"state.json",{"status":"RUNNING","completed_scenes":number+1,"expected_scenes":len(rows),"last_scene":row["scene"]})
 atomic_json(worker/"state.json",{"status":"COMPLETE","completed_scenes":len(rows)})
except Exception as e:atomic_json(worker/"state.json",{"status":"FAILED","error":repr(e)});raise
