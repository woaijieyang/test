"""Inspect native source triangles at the localized early-rasterization gap."""
import os,sys,json,struct,math,datetime
from pathlib import Path
assert os.environ.get("CASE1_PROTECTION");os.environ["OPENBLAS_NUM_THREADS"]="1";os.environ["OMP_NUM_THREADS"]="1";os.environ["CUDA_VISIBLE_DEVICES"]="";os.nice(15)
R=Path.cwd();sys.path[:0]=[str(R/"scripts"),str(R/"tests/landmark_diagnostics")]
from workspace import atomic_json,digest
from swept_cylinder_reference import triangle_linear_sweep_distance
import numpy as np
O=R/"outputs/landmark-connectivity/1lx-fine-stage-graphs-cpu-v1";D=O/"gap-source-triangles-v1";D.mkdir(exist_ok=False)
v=json.loads((O/"validation.json").read_text());cs,ch,H,climb,radius,region,bx,by,bz=v["native_build_config"]
raw=(O/"native-1.bin").read_bytes();nv,nt=struct.unpack("<ii",raw[:8]);verts=np.frombuffer(raw,dtype="<f4",count=nv*3,offset=8).reshape(nv,3);idx=np.frombuffer(raw,dtype="<i4",count=nt*3,offset=8+nv*12).reshape(nt,3);tri=verts[idx].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1)
def clip(poly,axis,bound,above):
 result=[]
 for a,b in zip(poly,poly[1:]+poly[:1]):
  aa=a[axis]>=bound if above else a[axis]<=bound;bb=b[axis]>=bound if above else b[axis]<=bound
  if aa:result.append(a)
  if aa!=bb:result.append(a+(b-a)*((bound-a[axis])/(b[axis]-a[axis])))
 return result
rows=[]
for x in range(362,366):
 for z in range(296,301):
  low=np.array([bx+x*cs,-.5,bz+z*cs]);high=low+np.array([cs,1.,cs]);ids=np.flatnonzero(np.all(hi>=low,axis=1)&np.all(lo<=high,axis=1));faces=[]
  for j in ids:
   poly=list(tri[j])
   for axis in [0,2]:
    poly=clip(poly,axis,low[axis],True)
    if not poly:break
    poly=clip(poly,axis,high[axis],False)
    if not poly:break
   if not poly:continue
   normal=np.cross(tri[j,1]-tri[j,0],tri[j,2]-tri[j,0]);length=float(np.linalg.norm(normal));ny=float(normal[1]/length) if length else None
   faces.append({"triangle":int(j),"vertices":tri[j].tolist(),"normal_y":ny,"slope_absolute":math.degrees(math.acos(min(1,abs(ny)))) if ny is not None else None,"recast_slope_walkable":bool(ny is not None and ny>math.cos(math.pi/4)),"clipped_y_min":min(float(q[1]) for q in poly),"clipped_y_max":max(float(q[1]) for q in poly)})
  rows.append({"cell_xz":[x,z],"bounds_xz":[low[[0,2]].tolist(),high[[0,2]].tolist()],"triangles":faces})
atomic_json(D/"cells.json",rows)
raw=(O/"native-1-low_hanging-raw.bin").read_bytes();n=struct.unpack("<i",raw[:4])[0];spans=np.frombuffer(raw,dtype="<i4",offset=4).reshape(n,5)
summary=[]
for r in rows:
 x,z=r["cell_xz"];ss=spans[(spans[:,0]==x)&(spans[:,1]==z)&(spans[:,3]>=54)&(spans[:,2]<=72)];faces=r["triangles"]
 summary.append({"cell_xz":[x,z],"raw_spans":ss.tolist(),"triangles":len(faces),"walkable_faces":sum(t["recast_slope_walkable"] for t in faces),"downward_gentle_faces":sum(t["normal_y"] is not None and t["normal_y"]<0 and t["slope_absolute"]<=45 for t in faces),"steep_faces":sum(t["slope_absolute"] is not None and t["slope_absolute"]>45 for t in faces),"absolute_slope_range":[min((t["slope_absolute"] for t in faces if t["slope_absolute"] is not None),default=None),max((t["slope_absolute"] for t in faces if t["slope_absolute"] is not None),default=None)]})
atomic_json(D/"validation.json",{"status":"COMPLETE_LOCAL_TRIANGLE_DIAGNOSIS_NOT_REPAIR","cells":summary,"native_input_sha256":digest(O/"native-1.bin"),"raw_spans_sha256":digest(O/"native-1-low_hanging-raw.bin"),"script_sha256":digest(__file__),"time":datetime.datetime.now().isoformat(),"limits":"Local20cells andsource triangles only. Slope classification uses currentpositiveY normal and45degrees; no normals/winding/scene/threshold modified. Clippedtriangle ranges are not exact rcRasterize reproduction or physicalroute certification."})
print(json.dumps(summary))
