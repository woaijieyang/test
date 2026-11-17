"""Exact-coordinate shared-edge orientation checks, without repairing or flipping source faces."""
import os,sys,json,struct,math,datetime
from pathlib import Path
assert os.environ.get("CASE1_PROTECTION");os.environ["CUDA_VISIBLE_DEVICES"]="";os.environ["OPENBLAS_NUM_THREADS"]="1";os.environ["OMP_NUM_THREADS"]="1"
R=Path.cwd();sys.path.insert(0,str(R/"scripts"))
from workspace import atomic_json,digest
import numpy as np
B=R/"outputs/landmark-connectivity/low-contact-stage-v1"
for scene in ["2azQ1b91cZZ","ac26ZMwG7aT"]:
 O=B/scene;columns=O/"local-columns-v1/columns.json";data=json.loads(columns.read_text());targets={f["triangle"]:f for r in data if r.get("selected_raw_span",[0,0,0,0,63])[4]==0 for f in r["faces"] if f["normal_y"] is not None and f["normal_y"]<0 and f["absolute_slope"]<=45}
 raw=(O/"native-1.bin").read_bytes();nv,nt=struct.unpack("<ii",raw[:8]);vv=np.frombuffer(raw,dtype="<f4",count=nv*3,offset=8).reshape(nv,3);ix=np.frombuffer(raw,dtype="<i4",count=nt*3,offset=8+12*nv).reshape(nt,3);records=[]
 for tid in sorted(targets):
  triangle=vv[ix[tid]];edges=[]
  for ia,ib in [(0,1),(1,2),(2,0)]:
   a=triangle[ia];b=triangle[ib];aids=np.flatnonzero(np.all(vv==a,axis=1));bids=np.flatnonzero(np.all(vv==b,axis=1));candidate=np.flatnonzero(np.any(np.isin(ix,aids),axis=1)&np.any(np.isin(ix,bids),axis=1));neighbors=[]
   for j in candidate:
    if j==tid:continue
    points=vv[ix[j]];signs=[]
    for k in range(3):
     p=points[k];q=points[(k+1)%3]
     if np.array_equal(p,a) and np.array_equal(q,b):signs.append("same_direction")
     elif np.array_equal(p,b) and np.array_equal(q,a):signs.append("opposite_direction")
    normal=np.cross((points[1]-points[0]).astype(float),(points[2]-points[0]).astype(float));n=float(np.linalg.norm(normal));neighbors.append({"triangle":int(j),"edge_directions":signs,"normal_y":float(normal[1]/n) if n else None,"same_native_index_edge":bool(np.isin(ix[tid,ia],ix[j]) and np.isin(ix[tid,ib],ix[j])),"vertices":points.tolist()})
   edges.append({"edge_vertices":[a.tolist(),b.tolist()],"exact_welded_vertex_counts":[len(aids),len(bids)],"neighbors":neighbors,"same_direction_neighbors":sum("same_direction" in n["edge_directions"] for n in neighbors),"opposite_direction_neighbors":sum("opposite_direction" in n["edge_directions"] for n in neighbors)})
  records.append({"triangle":int(tid),"normal_y":targets[tid]["normal_y"],"absolute_slope":targets[tid]["absolute_slope"],"edges":edges})
 result={"status":"COMPLETE_ORIENTATION_DIAGNOSIS_NOT_REPAIR","scene":scene,"faces":records,"source_sha256":digest(O/"native-1.bin"),"column_receipt_sha256":digest(columns),"script_sha256":digest(__file__),"limits":"Exact-coordinate welding only for shared-edge analysis. Sourcevertices/indices untouched; coherent local winding does not prove globalinside/outside; inconsistent or boundaryedges alone do not authorize face flipping or two-sided walkability.","time":datetime.datetime.now().isoformat()};dest=O/"local-columns-v1/orientation.json";assert not dest.exists();atomic_json(dest,result)
 print(scene,[{"triangle":r["triangle"],"edges":[{"same":e["same_direction_neighbors"],"opposite":e["opposite_direction_neighbors"],"neighbors":len(e["neighbors"])} for e in r["edges"]]} for r in records])
