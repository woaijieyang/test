"""Classify pre-ledge component frontier constraints; no navmesh or gate changes."""
import os,sys,json,struct,ast,collections,datetime,math
from pathlib import Path
assert os.environ.get("CASE1_PROTECTION");os.environ["CUDA_VISIBLE_DEVICES"]="";os.environ["OPENBLAS_NUM_THREADS"]="1";os.environ["OMP_NUM_THREADS"]="1";os.nice(15)
R=Path.cwd();sys.path[:0]=[str(R/"scripts"),str(R/".cache/geometry-tools")]
from workspace import atomic_json,digest
import numpy as np,psutil
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree
usage=psutil.cpu_percent(interval=1,percpu=True);os.sched_setaffinity(0,[min(sorted(os.sched_getaffinity(0))[:64],key=lambda i:usage[i])])
O=R/"outputs/landmark-connectivity/1lx-fine-stage-graphs-cpu-v1";D=O/"prefilter-frontier-v1";D.mkdir(exist_ok=False)
atomic_json(D/"process.json",{"pid":os.getpid(),"start_ticks":Path("/proc/self/stat").read_text().rsplit(")",1)[1].split()[19]})
v=json.loads((O/"validation.json").read_text());assert v["native_byte_control_match"]
cs,ch,H,climb,radius,region,bx,by,bz=v["native_build_config"];H=int(H);climb=int(climb)
helper=R/"tests/landmark_diagnostics/analyze_native_stage_graphs.py";ns={"np":np,"collections":collections,"O":O,"H":H,"climb":climb,"directions":[(-1,0),(0,1),(1,0),(0,-1)],"struct":struct}
tree=ast.parse(helper.read_text());exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ["read","reconstruct","adjacency"]],type_ignores=[]),str(helper),"exec"),ns)
try:
 atomic_json(D/"state.json",{"status":"RECONSTRUCTING_PREFILTER_GRAPH"})
 g=ns["reconstruct"](ns["read"]("native-1-low_hanging-raw.bin",5));adj=ns["adjacency"](g);valid=np.flatnonzero(g[:,5]!=0);dense=np.full(len(g),-1,dtype=np.int32);dense[valid]=np.arange(len(valid));start=np.repeat(valid,4);end=adj[valid].reshape(-1);mask=end>=0;start,end=start[mask],end[mask];mask=g[end,5]!=0;start,end=dense[start[mask]],dense[end[mask]]
 matrix=csr_matrix((np.ones(len(start),dtype=np.uint8),(start,end)),shape=(len(valid),len(valid)));count,labels=connected_components(matrix,directed=True,connection="weak")
 prior=json.loads((O/"stage-attribution/before_ledge.json").read_text());assert len(valid)==prior["valid_spans"] and count==prior["weak_components"]
 first=prior["candidate_pose_conflicts"][0];A,B=[set(s) for s in first["per_member_components"]];assert A and B and not A&B
 idsA=valid[np.isin(labels,list(A))];idsB=valid[np.isin(labels,list(B))];positions=np.column_stack((bx+(g[:,1]+.5)*cs,by+g[:,3]*ch,bz+(g[:,2]+.5)*cs))
 atomic_json(D/"state.json",{"status":"CHECKING_FRONTIER","spans_a":len(idsA),"spans_b":len(idsB)})
 cells=collections.defaultdict(list)
 for j in idsB:cells[tuple(map(int,g[j,1:3]))].append(int(j))
 rows=[];counts=collections.Counter()
 for ii in idsA:
  i=int(ii);x,z,y,h=map(int,g[i,[1,2,3,4]])
  for direction,(dx,dz) in enumerate(ns["directions"]):
   for j in cells.get((x+dx,z+dz),[]):
    yy,hh=map(int,g[j,[3,4]]);step=abs(y-yy);clearance=min(y+h,yy+hh)-max(y,yy)
    reason="CLIMB_AND_CLEARANCE" if step>climb and clearance<H else "CLIMB" if step>climb else "CLEARANCE" if clearance<H else "ELIGIBLE_BUT_DIFFERENT_SELECTED_LAYER"
    counts[reason]+=1;rows.append({"span_a":i,"span_b":j,"position_a":positions[i].tolist(),"position_b":positions[j].tolist(),"step_voxels":step,"overlap_voxels":clearance,"step_m":step*ch,"overlap_m":clearance*ch,"reason":reason})
 distances,idx=cKDTree(positions[idsB]).query(positions[idsA],k=1,workers=1);k=int(np.argmin(distances));nearest={"distance_m":float(distances[k]),"span_a":int(idsA[k]),"span_b":int(idsB[idx[k]]),"position_a":positions[idsA[k]].tolist(),"position_b":positions[idsB[idx[k]]].tolist()}
 atomic_json(D/"adjacent-column-pairs.json",rows)
 best=sorted(rows,key=lambda r:(max(0,r["step_voxels"]-climb)+max(0,H-r["overlap_voxels"]),r["step_voxels"],-r["overlap_voxels"]))[:20]
 atomic_json(D/"validation.json",{"status":"COMPLETE_PREFILTER_FRONTIER_DIAGNOSIS_NOT_REPAIR","focused_tasks":48,"spans_a":len(idsA),"spans_b":len(idsB),"adjacent_column_pairs":len(rows),"constraint_counts":dict(counts),"nearest_voxel_centers":nearest,"least_constraint_violation_pairs":best,"body_height_m":1.5,"radius_m":.1,"climb_voxels":climb,"height_voxels":H,"native_config":v["native_build_config"],"prior_stage_sha256":digest(O/"stage-attribution/before_ledge.json"),"raw_sha256":digest(O/"native-1-low_hanging-raw.bin"),"script_sha256":digest(__file__),"helper_sha256":digest(helper),"limits":"Known fine05 build graph. Adjacent column tests use existing height/climb; nonadjacent voids or source geometry need separate audit. Weak graph and voxel centers are not physical-motion proof. No thresholds changed or records deleted.","time":datetime.datetime.now().isoformat()});atomic_json(D/"state.json",{"status":"COMPLETE"})
except Exception as e:atomic_json(D/"state.json",{"status":"FAILED","error":repr(e)});raise
