"""Re-query existing meshes at already recorded source-supported free samples; no parameter scan."""
import os,sys,json,math,collections,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.nice(15)
sys.path.insert(0,str(Path.cwd()/'scripts'));sys.path.insert(0,str(Path.cwd()/'tests/landmark_diagnostics'))
from workspace import ROOT,atomic_json,digest
from bounded_camera_seed import select_camera_seed
import habitat_sim,psutil
usage=psutil.cpu_percent(interval=1,percpu=True);os.sched_setaffinity(0,[min(sorted(os.sched_getaffinity(0))[:64],key=lambda x:usage[x])])
B=ROOT/'outputs/landmark-connectivity';mp=B/'full-native-v11/manifest.json';m=json.loads(mp.read_text());profile=json.loads(Path(m['profile_path']).read_text());held=set(json.loads((B/'constraint-blockers.json').read_text())['task_keys']);source=B/'remaining-body-clearance.json';body={(r['scene'],r['node']):r for r in json.loads(source.read_text())['records']};identity={(r['scene'],r['node']):r for r in json.loads((B/'published-identity-nodes.json').read_text())['nodes']};affected=collections.defaultdict(set)
for t in m['tasks']:
 if t['status']=='READY_FOR_NATIVE_MOTION' or t['task_key'] in held:continue
 for node,p in zip(t['original_viewpoint_path'],t['targets']):
  if p is None:affected[(t['scene'],node)].add(t['task_key'])
finders={};records=[]
for (sc,node),keys in sorted(affected.items()):
 asset=profile['assets'][f'mp3d/{sc}/{sc}.glb']
 if sc not in finders:
  pf=habitat_sim.PathFinder();assert digest(asset['navmesh_path'])==asset['navmesh_sha256'];assert pf.load_nav_mesh(asset['navmesh_path']);finders[sc]=pf
 pf=finders[sc];info=identity[(sc,node)];camera=info['camera_position'];r=body.get((sc,node));seeds=r['closest_free_candidates'] if r else [];accepted=[];rejected=collections.Counter();line_seed=select_camera_seed(pf,camera)
 for seed in seeds:
  q=list(map(float,pf.snap_point(seed)))
  if not all(math.isfinite(x) for x in q):rejected['nonfinite']+=1;continue
  if not pf.is_navigable(q) or math.dist(q,list(pf.snap_point(q)))>1e-5:rejected['unstable_or_offmesh']+=1;continue
  if math.hypot(q[0]-camera[0],q[2]-camera[2])>=.5 or not 0<=camera[1]-q[1]<=2:rejected['outside_original_camera_bounds']+=1;continue
  if not any(math.dist(q,x['position'])<=1e-5 for x in accepted):accepted.append({'position':q,'seed':seed,'source_body_clearance_after_snap':'NOT_YET_CHECKED'})
 records.append({'scene':sc,'node':node,'identity_method':info['method'],'task_keys':sorted(keys),'original_vertical_seed':line_seed,'source_free_samples_checked':len(seeds),'candidate_count':len(accepted),'candidates':accepted,'rejections':dict(rejected),'mesh_sha256':asset['navmesh_sha256']})
atomic_json(B/'source-supported-seed-recheck-v1.json',{'status':'SOURCE_SEED_QUERY_DIAGNOSTIC','time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'nodes':len(records),'records':records,'manifest_sha256':digest(mp),'source_evidence_sha256':digest(source),'profile_sha256':digest(m['profile_path']),'script_sha256':digest(__file__),'limits':'Only source samples previously recorded as body-clear are query seeds. Snapped positions require fresh source-body check and whole-route proof; no data/profile/gate modifications.'});print([(r['scene'],r['node'],len(r['task_keys']),r['source_free_samples_checked'],r['candidate_count']) for r in records])
