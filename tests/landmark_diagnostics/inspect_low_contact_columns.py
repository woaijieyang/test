"""Localized column/slope/merge-flag diagnosis on existing verified gap centerlines."""
import os,sys,json,struct,ast,math,datetime
from pathlib import Path
assert os.environ.get("CASE1_PROTECTION");os.environ["CUDA_VISIBLE_DEVICES"]="";os.environ["OPENBLAS_NUM_THREADS"]="1";os.environ["OMP_NUM_THREADS"]="1";os.nice(15)
R=Path.cwd();sys.path.insert(0,str(R/"scripts"))
from workspace import atomic_json,digest
import numpy as np
helper=R/"tests/landmark_diagnostics/inspect_1lx_gap_triangles.py";node=[n for n in ast.parse(helper.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=="clip"];assert len(node)==1;exec(compile(ast.Module(body=node,type_ignores=[]),str(helper),"exec"),globals())
B=R/"outputs/landmark-connectivity";root=B/"low-contact-stage-v1"
for scene,pairid in [("2azQ1b91cZZ",[0,2]),("ac26ZMwG7aT",[0,1])]:
 O=root/scene;D=O/"local-columns-v1";D.mkdir(exist_ok=False);control=json.loads((O/"native-control.json").read_text());assert control["status"]=="PASS_BYTE_CONTROL";cs,ch,H,climb,radius,region,bx,by,bz=control["config"]
 previous=B/"native-gap-geometry-v1/scenes"/(scene+".json");pair=next(p for p in json.loads(previous.read_text())["pairs"] if p["component_pair"]==pairid)
 raw=(O/"native-1.bin").read_bytes();nv,nt=struct.unpack("<ii",raw[:8]);vertices=np.frombuffer(raw,dtype="<f4",count=nv*3,offset=8).reshape(nv,3);indices=np.frombuffer(raw,dtype="<i4",count=nt*3,offset=8+12*nv).reshape(nt,3);tri=vertices[indices].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1)
 raw=(O/"native-1-low_hanging-raw.bin").read_bytes();n=struct.unpack("<i",raw[:4])[0];spans=np.frombuffer(raw,dtype="<i4",offset=4).reshape(n,5);rows=[]
 for sample in pair["samples"]:
  point=sample["position"];x=math.floor((point[0]-bx)/cs);z=math.floor((point[2]-bz)/cs);ss=spans[(spans[:,0]==x)&(spans[:,1]==z)];near=[r for r in ss if abs(by+r[3]*ch-point[1])<=.5]
  if not near:rows.append({"position":point,"cell_xz":[x,z],"status":"NO_SPAN_TOP_WITHIN_DIAGNOSTIC_HALF_METRE","all_spans":ss.tolist()});continue
  selected=min(near,key=lambda r:abs(by+r[3]*ch-point[1]));low=np.array([bx+x*cs,by+selected[2]*ch,bz+z*cs]);high=np.array([bx+(x+1)*cs,by+selected[3]*ch,bz+(z+1)*cs]);ids=np.flatnonzero(np.all(hi>=low,axis=1)&np.all(lo<=high,axis=1));faces=[]
  for j in ids:
   poly=list(tri[j])
   for axis in [0,1,2]:
    poly=clip(poly,axis,low[axis],True)
    if not poly:break
    poly=clip(poly,axis,high[axis],False)
    if not poly:break
   if not poly:continue
   normal=np.cross(tri[j,1]-tri[j,0],tri[j,2]-tri[j,0]);length=float(np.linalg.norm(normal));ny=float(normal[1]/length) if length else None;top=max(float(q[1]) for q in poly);bottom=min(float(q[1]) for q in poly)
   faces.append({"triangle":int(j),"normal_y":ny,"absolute_slope":math.degrees(math.acos(min(1,abs(ny)))) if ny is not None else None,"walkable_by_slope":ny is not None and ny>math.cos(math.pi/4),"clipped_y_min":bottom,"clipped_y_max":top,"top_voxel_estimate":math.ceil((top-by)/ch),"vertices":tri[j].tolist()})
  walking=[f for f in faces if f["walkable_by_slope"]];preceding=[r for r in ss if r[3]<=selected[2]]
  rows.append({"position":point,"cell_xz":[x,z],"selected_raw_span":selected.tolist(),"selected_top":float(by+selected[3]*ch),"point_top_difference":float(by+selected[3]*ch-point[1]),"all_spans":ss.tolist(),"faces":faces,"walkable_faces":len(walking),"walkable_face_near_span_top":sum(abs(int(selected[3])-f["top_voxel_estimate"])<=climb for f in walking),"preceding_spans": [r.tolist() for r in preceding]})
 atomic_json(D/"columns.json",rows)
 summary=[]
 for r in rows:
  summary.append({k:r[k] for k in ["cell_xz","status","selected_raw_span","point_top_difference","walkable_faces","walkable_face_near_span_top"] if k in r})
 atomic_json(D/"validation.json",{"status":"COMPLETE_LOCAL_COLUMNS_NOT_REPAIR","scene":scene,"pair":pairid,"samples":len(rows),"null_area_columns_with_nearby_walkable_face":[r["cell_xz"] for r in rows if "selected_raw_span" in r and r["selected_raw_span"][4]==0 and r["walkable_face_near_span_top"]],"summary":summary,"native_control_sha256":digest(O/"native-control.json"),"gap_source_sha256":digest(previous),"script_sha256":digest(__file__),"limits":"Columns selected near existing hypothetical centerline. Clipped native triangle faces are evidence for flag propagation hypotheses, not exact rasterizer replay or physical motion. No parameters, geometry or annotations changed.","time":datetime.datetime.now().isoformat()});print(scene,summary)
