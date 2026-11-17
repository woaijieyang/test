"""Query actual native surfaces inside the unchanged camera cylinder/slab; diagnostic only."""
import os,sys,json,math,datetime,collections
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import atomic_json,digest
from bounded_camera_seed import select_camera_seed
from bounded_triangle_projection import triangle_closest
from cylinder_contact_height import clip_y
import numpy as np,habitat_sim,psutil
u=psutil.cpu_percent(interval=1,percpu=True);available=[i for i in sorted(os.sched_getaffinity(0))[:64] if u[i]<25];assert available;os.sched_setaffinity(0,[min(available,key=lambda i:u[i])])
B=R/'outputs/landmark-connectivity';O=B/'camera-surface-domain-v1';O.mkdir(exist_ok=False);atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]});identity_path=B/'published-identity-nodes.json';nodes=[r for r in json.loads(identity_path.read_text())['nodes'] if r['method']=='UNRESOLVED_no_direct_identity'];assert len(nodes)==96;parent=B/'full-native-v11/manifest.json';m=json.loads(parent.read_text());profile=json.loads(Path(m['profile_path']).read_text());held=set(json.loads((B/'constraint-blockers.json').read_text())['task_keys']);affected=collections.defaultdict(list)
for t in m['tasks']:
 for node in set(t['original_viewpoint_path']):affected[(t['scene'],node)].append({'task_key':t['task_key'],'status':t['status'],'held114':t['task_key'] in held})
rows=[]
for sc in sorted({n['scene'] for n in nodes}):
 asset=profile['assets'][f'mp3d/{sc}/{sc}.glb'];assert digest(asset['navmesh_path'])==asset['navmesh_sha256'];pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(asset['navmesh_path']);vertices=np.asarray(pf.build_navmesh_vertices(),float);indices=np.asarray(pf.build_navmesh_vertex_indices(),int).reshape(-1,3);tri=vertices[indices];lo=tri.min(axis=1);hi=tri.max(axis=1)
 for node in [n for n in nodes if n['scene']==sc]:
  cam=np.array(node['camera_position']);delta=np.maximum(np.maximum(lo[:,[0,2]]-cam[[0,2]],cam[[0,2]]-hi[:,[0,2]]),0);ids=np.flatnonzero((np.sum(delta**2,axis=1)<.25)&(lo[:,1]<=cam[1])&(hi[:,1]>=cam[1]-2));found={};degenerate=0;tested=0
  def consider(q,index,method):
   if not np.isfinite(q).all():return
   snap=np.array(pf.snap_point(q))
   if not np.isfinite(snap).all() or not pf.is_navigable(snap) or np.linalg.norm(q-snap)>1e-5:return
   h=math.hypot(snap[0]-cam[0],snap[2]-cam[2]);drop=cam[1]-snap[1]
   if h>=.5 or not 0<=drop<=2:return
   key=tuple(float(v) for v in snap);found.setdefault(key,{'position':snap.tolist(),'triangle':int(index),'method':method,'horizontal_displacement':h,'drop':drop})
  for index in ids:
   poly=clip_y(clip_y(list(tri[index]),cam[1]-2,True),cam[1],False)
   if len(poly)<3:continue
   for j in range(1,len(poly)-1):
    face=np.array([poly[0],poly[j],poly[j+1]]);flat=face.copy();flat[:,1]=0;anchor=np.array([cam[0],0,cam[2]]);qflat=triangle_closest(anchor,flat);E=np.column_stack((flat[1]-flat[0],flat[2]-flat[0]));uv,res,rank,sv=np.linalg.lstsq(E,qflat-flat[0],rcond=None)
    if rank<2:degenerate+=1;continue
    q=face[0]+uv[0]*(face[1]-face[0])+uv[1]*(face[2]-face[0]);consider(q,index,'closest_horizontal_point_on_height_clipped_native_triangle');consider(q+1e-4*(face.mean(axis=0)-q),index,'interior_witness');tested+=2
   for q in poly:consider(q,index,'clipped_vertex');tested+=1
  candidates=sorted(found.values(),key=lambda r:(r['horizontal_displacement'],-r['drop']));old=select_camera_seed(pf,cam.tolist());row={'scene':sc,'node':node['node'],'raw_camera_position':cam.tolist(),'old_vertical_query_seed':old,'surface_candidates':candidates,'new_seed_exists_when_old_missing':old is None and bool(candidates),'triangles_considered':len(ids),'point_queries':tested,'degenerate_projected_triangles_not_classified':degenerate,'affected_tasks':affected[(sc,node['node'])],'mesh_sha256':asset['navmesh_sha256']};rows.append(row);atomic_json(O/'state.json',{'status':'RUNNING','nodes':len(rows),'expected':96,'new_missing_seed_nodes':sum(r['new_seed_exists_when_old_missing'] for r in rows)})
novel=[r for r in rows if r['new_seed_exists_when_old_missing']];keys={t['task_key'] for r in novel for t in r['affected_tasks']};atomic_json(O/'validation.json',{'status':'COMPLETE_CAMERA_DOMAIN_QUERY_NOT_MAPPING_ACCEPTANCE','nodes':96,'new_missing_seed_nodes':len(novel),'affected_unique_tasks':len(keys),'affected_task_keys':sorted(keys),'rows':rows,'profile_sha256':m['profile_sha256'],'parent_manifest_sha256':digest(parent),'identity_sha256':digest(identity_path),'script_sha256':digest(__file__),'helper_hashes':{n:digest(R/'tests/landmark_diagnostics'/n) for n in ['bounded_camera_seed.py','bounded_triangle_projection.py','cylinder_contact_height.py']},'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'limits':'Same raw camera horizontal<0.5m/down0..2m. Surface query is a seed diagnostic only, not a new source-anchor rule or permission to move a target. Source body/support, floor/landmark semantics, full-route and actual motion gates remain. Degenerate projected surfaces explicitly not resolved. held114 original records/evidence and all active inputs unchanged.'});atomic_json(O/'state.json',{'status':'COMPLETE','nodes':96,'new_missing_seed_nodes':len(novel),'affected_unique_tasks':len(keys)});print('complete',len(novel),len(keys))
