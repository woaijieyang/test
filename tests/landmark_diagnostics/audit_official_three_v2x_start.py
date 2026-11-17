"""Compare the three remaining official-matched blockers against original/current meshes."""
import os,sys,json,gzip,math,struct,subprocess,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import atomic_json,digest
from swept_cylinder_reference import triangle_linear_sweep_distance
from cylinder_contact_height import contact_height_range
import numpy as np,habitat_sim,psutil
u=psutil.cpu_percent(interval=1,percpu=True);eligible=[i for i in sorted(os.sched_getaffinity(0))[:64] if i not in [1,5,7,9,10,11,15,16]];os.sched_setaffinity(0,[min(eligible,key=lambda i:u[i])])
B=R/'outputs/landmark-connectivity';O=B/'official-three-v2x-start-audit-v1';O.mkdir(exist_ok=False);atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
scene='V2XKFyX4ASd';wanted={'1686','1687','53488'};parent_path=B/'full-native-v11/manifest.json';parent=json.loads(parent_path.read_text());tasks={t['task_key']:t for t in parent['tasks'] if t['scene']==scene and str(t['instruction_id']) in wanted};assert len(tasks)==3;held=set(json.loads((B/'constraint-blockers.json').read_text())['task_keys']);assert not set(tasks)&held
ce=R/'data/datasets/RxR_VLNCE_v0/train';ep=ce/'train_guide.json.gz';gp=ce/'train_guide_gt.json.gz';eps=[e for e in json.load(gzip.open(ep,'rt'))['episodes'] if str(e['instruction']['instruction_id']) in wanted];gt=json.load(gzip.open(gp,'rt'));subset=[]
for e in eps:
 key='train:'+str(e['instruction']['instruction_id']);assert e['scene_id']==f'mp3d/{scene}/{scene}.glb' and len(e['reference_path'])==len(tasks[key]['original_viewpoint_path']);subset.append({'task_key':key,'episode_id':e['episode_id'],'source_record_sha256':tasks[key]['source_record_sha256'],'start_position':e['start_position'],'reference_path':e['reference_path'],'locations':gt[str(e['episode_id'])]['locations']})
assert len(subset)==3;atomic_json(O/'official-subset.json',{'records':subset,'episode_file_sha256':digest(ep),'gt_file_sha256':digest(gp),'parent_manifest_sha256':digest(parent_path)});del gt
profile=json.loads(Path(parent['profile_path']).read_text());current=Path(profile['assets'][f'mp3d/{scene}/{scene}.glb']['navmesh_path']);original=R/f'data/scene_datasets/mp3d/{scene}/{scene}.navmesh';assert original.exists();reports={}
for label,path in [('original_shared',original),('current_profile',current)]:
 pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(str(path));headers=json.loads(subprocess.check_output([str(R/'.cache/navmesh-header-probe/probe'),str(path)],text=True));rows=[]
 for r in subset:
  start=r['start_position'];snap=list(pf.snap_point(start));queries=[]
  for a,b in zip(r['locations'],r['locations'][1:]):
   q=habitat_sim.ShortestPath();q.requested_start=a;q.requested_end=b;ok=pf.find_path(q) and math.isfinite(q.geodesic_distance);queries.append(bool(ok))
  rows.append({'task_key':r['task_key'],'start_navigable':bool(pf.is_navigable(start)),'start_snap':snap,'start_snap_displacement_m':math.dist(start,snap),'gt_locations':len(r['locations']),'gt_navigable':sum(bool(pf.is_navigable(q)) for q in r['locations']),'gt_finite_adjacent':sum(queries),'gt_adjacent_count':len(queries)})
 reports[label]={'mesh_path':str(path),'mesh_sha256':digest(path),'headers':headers,'rows':rows}
catalog=json.loads((B/'native-source-catalog-v1/catalog.json').read_text());native=next(r for r in catalog['scenes'] if r['scene']==scene);assert digest(native['native_geometry_path'])==native['native_geometry_sha256'];raw=Path(native['native_geometry_path']).read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);verts=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);indices=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);tri=verts[indices].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1);start=np.array(subset[0]['start_position']);assert all(r['start_position']==start.tolist() for r in subset);selected=np.flatnonzero((lo[:,0]<start[0]+.1)&(hi[:,0]>start[0]-.1)&(lo[:,2]<start[2]+.1)&(hi[:,2]>start[2]-.1)&(lo[:,1]<start[1]+1.5)&(hi[:,1]>start[1]+1e-5));contacts=[]
for j in selected:
 distance=triangle_linear_sweep_distance(tri[j],start,start)
 if distance<.1-1e-6:
  height=contact_height_range(tri[j],start);contacts.append({'triangle':int(j),'distance':float(distance),'height':height})
atomic_json(O/'validation.json',{'status':'OFFICIAL_MATCHED_BLOCKER_DIAGNOSTIC_NOT_REPAIR','tasks':3,'scene':scene,'official_subset_sha256':digest(O/'official-subset.json'),'mesh_reports':reports,'shared_official_start':start.tolist(),'source_start_contacts':contacts,'native_geometry_sha256':native['native_geometry_sha256'],'script_sha256':digest(__file__),'limits':'Original annotation/profile unchanged; original mesh load is read-only. Finite geodesics/native samples alone are not source-body or real-motion proof. These3 are outside held114 and remain in the full denominator.'});print({'source_contacts':len(contacts),'meshes':{k:{'rows':v['rows'],'headers':v['headers']} for k,v in reports.items()}})
