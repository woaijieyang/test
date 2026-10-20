"""Check source-geometry support samples against the frozen candidate navmesh.
No geometry, labels, profiles or acceptance bounds are changed.
"""
import os,sys,json,math,collections
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
assert os.environ.get('CASE1_PROTECTION')
os.environ['CUDA_VISIBLE_DEVICES']=''
os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[10:11]);os.nice(10)
import habitat_sim
base=ROOT/'outputs/landmark-connectivity'
source=base/'remaining-body-clearance.json'
manifest=base/'full-native-v4/manifest.json'
m=json.loads(manifest.read_text());profile=json.loads(Path(m['profile_path']).read_text())
rows=[];pfs={};totals=collections.Counter()
for record in json.loads(source.read_text())['records']:
 sc=record['scene'];asset=profile['assets'][f'mp3d/{sc}/{sc}.glb']
 if sc not in pfs:
  pf=habitat_sim.PathFinder();assert digest(asset['navmesh_path'])==asset['navmesh_sha256'];assert pf.load_nav_mesh(asset['navmesh_path']);pfs[sc]=pf
 pf=pfs[sc];camera=record['camera_position'];samples=[]
 for seed in record['closest_free_candidates']:
  q=list(pf.snap_point(seed));finite=all(math.isfinite(v) for v in q)
  horizontal=math.hypot(q[0]-camera[0],q[2]-camera[2]) if finite else None
  down=camera[1]-q[1] if finite else None
  valid=finite and pf.is_navigable(q) and horizontal<.5 and 0<=down<=2 and math.dist(q,list(pf.snap_point(q)))<=1e-5
  samples.append({'source_sample':seed,'navmesh_position':q if finite else None,'horizontal_camera_distance':horizontal,'down_from_camera':down,'source_surface_to_mesh_distance':math.dist(seed,q) if finite else None,'bounded_mesh_candidate':bool(valid)})
 count=sum(x['bounded_mesh_candidate'] for x in samples);totals['nodes']+=1;totals['nodes_with_bounded_mesh_candidate']+=bool(count)
 tasks=[t['task_key'] for t in m['tasks'] if t['scene']==sc and record['node'] in t['original_viewpoint_path']]
 rows.append({'scene':sc,'node':record['node'],'task_keys':tasks,'samples':samples,'bounded_candidates':count,'navmesh_sha256':asset['navmesh_sha256']})
 print(sc,record['node'],count,len(samples),flush=True)
atomic_json(base/'support-to-navmesh-diagnostic.json',{'status':'DIAGNOSTIC_ONLY','counts':dict(totals),'records':rows,'source_sha256':digest(source),'manifest_sha256':digest(manifest),'script_sha256':digest(__file__),'limits':'Only saved source-geometry samples inspected. A bounded mesh candidate is not whole-route or body-clearance acceptance; failed finite sampling does not prove continuous impossibility.'})
