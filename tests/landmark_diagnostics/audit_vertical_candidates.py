"""Independent static audit of vertical-query proposals; never accepts motion."""
import os,sys,json,math,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.nice(15);os.sched_setaffinity(0,[sorted(os.sched_getaffinity(0))[12]])
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
import habitat_sim
B=ROOT/'outputs/landmark-connectivity';run=B/'grounded-vertical-candidates-v1';oldpath=B/'full-native-v11/manifest.json';old=json.loads(oldpath.read_text());new=json.loads((run/'manifest.json').read_text());before={t['task_key']:t for t in old['tasks']};held=set(json.loads((B/'constraint-blockers.json').read_text())['task_keys']);ledger={t['task_key']:t for t in json.loads((run/'mapping-ledger.json').read_text())['records']};identity={(r['scene'],r['node']):r for r in json.loads((B/'published-identity-nodes.json').read_text())['nodes']};native={(r['scene'],r['node']):r['native_candidates'][0] for r in json.loads((B/'native-mapping.json').read_text())['nodes']};profile=json.loads(Path(new['profile_path']).read_text());assert new['profile_sha256']==old['profile_sha256']==digest(new['profile_path']);assert len(new['tasks'])==len(before)==33954 and len({t['task_key'] for t in new['tasks']})==33954;finders={};recoveries=[];regressions=[];issues=[];allowed={'targets','status','static_errors','mapping_methods'}
for t in new['tasks']:
 key=t['task_key'];o=before[key];prior=o['status']=='READY_FOR_NATIVE_MOTION';ready=t['status']=='READY_FOR_NATIVE_MOTION'
 if prior or key in held:assert t==o
 assert {k:v for k,v in t.items() if k not in allowed}=={k:v for k,v in o.items() if k not in allowed}
 if prior and not ready:regressions.append(key)
 if ready and not prior:
  sc=t['scene'];asset=profile['assets'][f'mp3d/{sc}/{sc}.glb']
  if sc not in finders:
   assert digest(asset['navmesh_path'])==asset['navmesh_sha256'];pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(asset['navmesh_path']);finders[sc]=pf
  pf=finders[sc];choices=ledger[key]['choices'];assert len(choices)==len(t['targets'])==len(t['original_viewpoint_path'])
  for node,q,choice in zip(t['original_viewpoint_path'],t['targets'],choices):
   assert choice['position']==q and all(math.isfinite(v) for v in q);assert pf.is_navigable(q) and math.dist(q,list(pf.snap_point(q)))<=1e-5;anchor=choice['anchor'];assert math.dist(q,anchor)<=.5
   if choice['rank']>=3:assert math.hypot(q[0]-anchor[0],q[2]-anchor[2])<=.350001
   if (sc,node) in native:assert anchor==native[(sc,node)]
   elif identity[(sc,node)]['method']!='UNRESOLVED_no_direct_identity':assert anchor==identity[(sc,node)]['position']
   else:
    camera=identity[(sc,node)]['camera_position'];assert math.hypot(q[0]-camera[0],q[2]-camera[2])<.5 and 0<=camera[1]-q[1]<=2
  for a,b in zip(t['targets'],t['targets'][1:]):
   path=habitat_sim.ShortestPath();path.requested_start=a;path.requested_end=b;assert pf.find_path(path) and math.isfinite(path.geodesic_distance)
  recoveries.append({'task_key':key,'scene':sc,'new_vertical_query_points':sum(c['rank']==4 for c in choices),'choices':choices})
assert not regressions
atomic_json(run/'static-transition-audit.json',{'status':'STATIC_CANDIDATE_ONLY' if recoveries else 'NO_RECOVERY','time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'total':33954,'held114_identical':True,'prior_ready_identical':30543,'recovered':recoveries,'regressed':regressions,'audit_issues':issues,'script_sha256':digest(__file__),'parent_manifest_sha256':digest(oldpath),'manifest_sha256':digest(run/'manifest.json'),'profile_sha256':new['profile_sha256'],'limits':'All original tasks and physical/source bounds retained. No proof of source-body clearance or real motion from static checks.'});print('static recoveries',len(recoveries),'regressions',len(regressions))
