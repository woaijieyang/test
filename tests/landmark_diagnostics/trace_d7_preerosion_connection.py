"""Shortest-hop compact graph witness from the D7 small island to retained region146."""
import os,sys,json,struct,collections,datetime
from pathlib import Path
assert os.environ.get("CASE1_PROTECTION");os.environ["CUDA_VISIBLE_DEVICES"]="";os.environ["OPENBLAS_NUM_THREADS"]="1";os.environ["OMP_NUM_THREADS"]="1";os.nice(15)
R=Path.cwd();sys.path.insert(0,str(R/"scripts"))
from workspace import atomic_json,digest
import numpy as np,psutil
usage=psutil.cpu_percent(interval=1,percpu=True);os.sched_setaffinity(0,[min(sorted(os.sched_getaffinity(0))[:64],key=lambda i:usage[i])])
O=R/"outputs/landmark-connectivity/d7-fine-stage-v1";D=O/"preerosion-connection-v1";D.mkdir(exist_ok=False)
atomic_json(D/"process.json",{"pid":os.getpid(),"start_ticks":Path("/proc/self/stat").read_text().rsplit(")",1)[1].split()[19]})
def read(name):
 raw=(O/name).read_bytes();n=struct.unpack("<i",raw[:4])[0];return np.frombuffer(raw,dtype="<i4",offset=4).reshape(n,11)
g=read("native-1-compacted-graph.bin");eroded=read("native-1-eroded-graph.bin");final=read("native-1-regions-graph.bin");assert np.array_equal(g[:,:5],final[:,:5]) and np.array_equal(g[:,7:],final[:,7:]);width=int(g[:,1].max())+1;keys=g[:,2].astype(np.int64)*width+g[:,1];assert np.all(keys[1:]>=keys[:-1]);cs,ch,H,climb,radius,region,bx,by,bz=json.loads((O/"native-control.json").read_text())["config"]
local=json.loads((O/"missing-anchor-v1/eroded.json").read_text());seeds=sorted({int(r["span"][0]) for r in local if r["span"][5] and r["anchor_distance"]<=.5});assert len(seeds)==826;goal=(final[:,5]!=0)&(final[:,6]==146);assert goal.any();parents=np.full(len(g),-2,dtype=np.int32);queue=collections.deque(seeds)
for i in seeds:parents[i]=-1
end=None;expanded=0;dirs=[(-1,0),(0,1),(1,0),(0,-1)]
while queue:
 i=queue.popleft();expanded+=1
 if goal[i]:end=i;break
 x,z=map(int,g[i,1:3])
 for d,(dx,dz) in enumerate(dirs):
  con=int(g[i,7+d])
  if con==63:continue
  nx,nz=x+dx,z+dz;j=int(np.searchsorted(keys,nz*width+nx))+con;assert j<len(g) and g[j,1]==nx and g[j,2]==nz
  if g[j,5] and parents[j]==-2:parents[j]=i;queue.append(j)
path=[]
if end is not None:
 while end>=0:path.append(int(end));end=int(parents[end])
 path.reverse()
records=[{"span_id":i,"cell_xz":g[i,1:3].tolist(),"position":[bx+(g[i,1]+.5)*cs,by+g[i,3]*ch,bz+(g[i,2]+.5)*cs],"headroom_voxels":int(g[i,4]),"eroded_area":int(eroded[i,5]),"final_region":int(final[i,6])} for i in path]
atomic_json(D/"validation.json",{"status":"COMPLETE_COMPACT_GRAPH_DIAGNOSIS_NOT_REPAIR","source_sphere_seed_count":len(seeds),"target_region":146,"expanded_spans":expanded,"path_found":bool(path),"path_spans":len(path),"spans_removed_by_erosion":sum(r["eroded_area"]==0 for r in records),"path":records,"compact_sha256":digest(O/"native-1-compacted-graph.bin"),"eroded_sha256":digest(O/"native-1-eroded-graph.bin"),"region_sha256":digest(O/"native-1-regions-graph.bin"),"script_sha256":digest(__file__),"limits":"Unchanged directed native adjacency beforeerosion. Shortesthop graph witness is neither actualDetour path nor physicalroute. No cells restored, geometry/thresholds changed or tasks accepted.","time":datetime.datetime.now().isoformat()});print({"path_found":bool(path),"path_spans":len(path),"expanded_spans":expanded,"removed":sum(r["eroded_area"]==0 for r in records)})
