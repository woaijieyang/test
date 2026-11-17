"""Trace surviving cells near D7 anchor before region deletion, with unchanged directed adjacency."""
import os,sys,json,struct,collections,datetime
from pathlib import Path
assert os.environ.get("CASE1_PROTECTION");os.environ["CUDA_VISIBLE_DEVICES"]="";os.environ["OPENBLAS_NUM_THREADS"]="1";os.environ["OMP_NUM_THREADS"]="1";os.nice(15)
R=Path.cwd();sys.path.insert(0,str(R/"scripts"))
from workspace import atomic_json,digest
import numpy as np,psutil
usage=psutil.cpu_percent(interval=1,percpu=True);os.sched_setaffinity(0,[min(sorted(os.sched_getaffinity(0))[:64],key=lambda i:usage[i])])
O=R/"outputs/landmark-connectivity/d7-fine-stage-v1";D=O/"eroded-islands-v1";D.mkdir(exist_ok=False)
def read(name):
 data=(O/name).read_bytes();n=struct.unpack("<i",data[:4])[0];return np.frombuffer(data,dtype="<i4",offset=4).reshape(n,11)
g=read("native-1-eroded-graph.bin");final=read("native-1-regions-graph.bin");assert np.array_equal(g[:,:5],final[:,:5]) and np.array_equal(g[:,7:],final[:,7:]);width=int(g[:,1].max())+1;keys=g[:,2].astype(np.int64)*width+g[:,1];assert np.all(keys[1:]>=keys[:-1]);v=json.loads((O/"native-control.json").read_text());cs,ch,H,climb,radius,region,bx,by,bz=v["config"]
local=json.loads((O/"missing-anchor-v1/eroded.json").read_text());seeds=[int(r["span"][0]) for r in local if r["span"][5] and r["anchor_distance"]<=.5];assert seeds
regions=[];seen=set();dirs=[(-1,0),(0,1),(1,0),(0,-1)]
for seed in seeds:
 if seed in seen:continue
 reached={seed};queue=collections.deque([seed])
 while queue:
  i=queue.popleft();x,z=map(int,g[i,1:3])
  for d,(dx,dz) in enumerate(dirs):
   con=int(g[i,7+d])
   if con==63:continue
   nx,nz=x+dx,z+dz;first=int(np.searchsorted(keys,nz*width+nx));j=first+con
   assert j<len(g) and int(g[j,1])==nx and int(g[j,2])==nz
   if g[j,5] and j not in reached:reached.add(j);queue.append(j)
 seen.update(reached);ids=np.array(sorted(reached));pos=np.column_stack((bx+(g[ids,1]+.5)*cs,by+g[ids,3]*ch,bz+(g[ids,2]+.5)*cs));low=pos.min(axis=0);high=pos.max(axis=0)
 hrows=np.array(json.loads((O/"equal-clearance-screen.json").read_text())["rows"],dtype=float);hpos=np.column_stack((bx+(hrows[:,0]+.5)*cs,by+hrows[:,3]*ch,bz+(hrows[:,1]+.5)*cs));delta=np.maximum(np.maximum(low-hpos,hpos-high),0);near=(np.linalg.norm(delta[:,[0,2]],axis=1)<=cs*(radius+2))&(delta[:,1]<=ch*(climb+2))
 regions.append({"seed":seed,"spans":len(ids),"source_sphere_seed_count":sum(s in reached for s in seeds),"retained_after_region_removal":int(np.count_nonzero((final[ids,5]!=0)&(final[ids,6]!=0))),"bbox_min":low.tolist(),"bbox_max":high.tolist(),"grid_projected_area_m2":len({tuple(r) for r in g[ids,1:3]})*cs*cs,"nearest_equal_clearance_span_bbox_distance_m":float(np.min(np.linalg.norm(delta,axis=1))),"equal_clearance_spans_within_conservative_radius_climb_margin":int(np.count_nonzero(near)),"near_equal_clearance_raw_spans":hrows[near].astype(int).tolist()})
assert all(s in seen for s in seeds)
# All15 affected routes require other anchors outside the small surviving components.
B=R/"outputs/landmark-connectivity";proposal=json.loads((B/"D7-grounded-fine05-v1/validation.json").read_text());catalog={(r["node"],None if r["original_target"] is None else tuple(r["original_target"])):r for r in proposal["nodes"]};tasks=json.loads((B/"D7-grounded-fine05-v1/candidate_tasks.json").read_text())["tasks"];regressed=set(json.loads((B/"D7-grounded-fine05-v1/static-transition-audit.json").read_text())["regressed"]);taskrows=[]
for t in tasks:
 if t["task_key"] not in regressed:continue
 anchors=[catalog[(node,tuple(q))]["anchor"] for node,q in zip(t["original_viewpoint_path"],t["targets"])];outside=[]
 for island in regions:
  lo=np.array(island["bbox_min"])[[0,2]]-cs*2;hi=np.array(island["bbox_max"])[[0,2]]+cs*2;dist=[float(np.linalg.norm(np.maximum(np.maximum(lo-np.array(a)[[0,2]],np.array(a)[[0,2]]-hi),0))) for a in anchors];outside.append(max(dist))
 taskrows.append({"task_key":t["task_key"],"maximum_required_anchor_horizontal_distance_to_each_expanded_island_bbox":outside})
assert len(taskrows)==15
atomic_json(D/"validation.json",{"status":"COMPLETE_ERODED_COMPONENT_DIAGNOSIS_NOT_REPAIR","source_sphere_seed_count":len(seeds),"components":regions,"tasks":taskrows,"all15_have_required_anchor_outside_each_island_source_sphere":all(all(d>.5 for d in r["maximum_required_anchor_horizontal_distance_to_each_expanded_island_bbox"]) for r in taskrows),"eroded_sha256":digest(O/"native-1-eroded-graph.bin"),"region_sha256":digest(O/"native-1-regions-graph.bin"),"script_sha256":digest(__file__),"limits":"Directed construction graph and generous bbox distance only. Restoring an isolated component is not a route repair. Equal-clearance locality is investigative evidence, not proof that an unexecuted patch cannot affect other regions. Body/geometry/annotation unchanged.","time":datetime.datetime.now().isoformat()});print(regions);print("ALL15_OTHER_ANCHORS_OUTSIDE",all(all(d>.5 for d in r["maximum_required_anchor_horizontal_distance_to_each_expanded_island_bbox"]) for r in taskrows))
