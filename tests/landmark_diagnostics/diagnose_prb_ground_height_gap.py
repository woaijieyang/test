"""Measure a source-derived minimal height gap without altering labels, mesh, motion or gates."""
import os,sys,json,struct,math,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.nice(15)
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import atomic_json,digest
from projected_distance_reference import projected_distance
import numpy as np,habitat_sim
B=R/'outputs/landmark-connectivity';O=B/'pRb-ground-height-gap-v1';O.mkdir(exist_ok=False);sc='pRbA3pwrgk9';node='0b6cc7b35ad04e5c91d137517f84eab5';native=json.loads((B/'native-mapping.json').read_text());anchor=next(r['native_candidates'][0] for r in native['nodes'] if r['scene']==sc and r['node']==node);m=json.loads((B/'full-native-v11/manifest.json').read_text());profile=json.loads(Path(m['profile_path']).read_text());asset=profile['assets'][f'mp3d/{sc}/{sc}.glb'];pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(asset['navmesh_path']);q=np.array(pf.snap_point(anchor));geo_path=B/f'full-source-native-{sc}-v1/validation.json';geo=json.loads(geo_path.read_text());p=Path(geo['native_geometry_path']);assert digest(p)==geo['native_geometry_sha256'];raw=p.read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);verts=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);ix=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);tri=verts[ix].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1)
def clip(poly,y,above):
 out=[]
 for a,b in zip(poly,poly[1:]+poly[:1]):
  aa=a[1]>=y if above else a[1]<=y;bb=b[1]>=y if above else b[1]<=y
  if aa:out.append(a)
  if aa!=bb:out.append(a+(y-a[1])/(b[1]-a[1])*(b-a))
 return out
def hits(q):
 ids=np.flatnonzero((lo[:,0]<q[0]+.1)&(hi[:,0]>q[0]-.1)&(lo[:,2]<q[2]+.1)&(hi[:,2]>q[2]-.1)&(lo[:,1]<q[1]+1.5)&(hi[:,1]>q[1]+1e-5));result=[]
 for j in ids:
  poly=clip(list(tri[j]),q[1]+1e-5,True)
  if len(poly)<3:continue
  poly=clip(poly,q[1]+1.5,False)
  if len(poly)>=3:
   distance=projected_distance(poly,q)
   if distance<.1-1e-6:result.append({'triangle':int(j),'distance':distance,'max_world_y':float(max(x[1] for x in poly)),'max_height':float(max(x[1] for x in poly)-q[1])})
 return result
original=hits(q);assert original;max_height=max(x['max_height'] for x in original);assert max_height<.02,'Not a millimeter-floor-only discrepancy';raised=q.copy();raised[1]=float(np.nextafter(np.float32(q[1]+max_height+2e-5),np.float32(np.inf)));new_hits=hits(raised);snapped=np.array(pf.snap_point(raised));affected=[t['task_key'] for t in m['tasks'] if t['scene']==sc and node in t['original_viewpoint_path']];assert len(affected)==78
atomic_json(O/'validation.json',{'status':'DIAGNOSTIC_GROUND_HEIGHT_GAP_NO_CORRECTION_APPLIED','scene':sc,'node':node,'affected_task_keys':affected,'official_anchor':anchor,'original_snap':q.tolist(),'original_contacts':original,'maximum_original_contact_height':max_height,'hypothetical_lifted_point':raised.tolist(),'lift_m':float(raised[1]-q[1]),'hypothetical_point_contacts':new_hits,'snap_of_hypothetical_point':snapped.tolist(),'snap_residual_m':float(np.linalg.norm(snapped-raised)),'exact_mesh_membership_pass':bool(np.linalg.norm(snapped-raised)<=1e-5),'source_anchor_distance':math.dist(anchor,raised.tolist()),'mesh_sha256':digest(asset['navmesh_path']),'native_geometry_sha256':digest(p),'script_sha256':digest(__file__),'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'limits':'Raised point is a geometric counterfactual only, not a valid adopted endpoint or actual trajectory. No new tolerance, annotation, scene or mesh write. A clean source-body point that fails exact mesh membership cannot be inserted into evaluation; source-ground/navmesh consistency remains unresolved.'});print('max_contact',max_height,'lift',raised[1]-q[1],'lift_contacts',len(new_hits),'snap_residual',np.linalg.norm(snapped-raised))
