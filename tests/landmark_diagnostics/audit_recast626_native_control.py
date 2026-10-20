import os,sys,json,math,collections
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'));from workspace import ROOT,atomic_json,digest
from bounded_camera_seed import select_camera_seed
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[28:29]);os.nice(10)
import habitat_sim
b=ROOT/'outputs/landmark-connectivity';run=b/'recast626-native-v1';reference=next(v['mesh_path'] for v in json.loads((b/'mJX-intermediate-height-v1/summary.json').read_text())['variants'] if v['settings']['cell_height']==.1);paths={'habitat_old':reference,'standalone_old':str(run/'old.navmesh'),'upstream626':str(run/'upstream626.navmesh')};m=json.loads((b/'full-native-v8/manifest.json').read_text());ts=[t for t in m['tasks'] if t['scene']=='mJXqzFtmKg4'];ids={(x['scene'],x['node']):x for x in json.loads((b/'published-identity-nodes.json').read_text())['nodes']};reports={};pointmaps={}
for name,path in paths.items():
 pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(path);pm={};rows=[];counts=collections.Counter()
 def point(node,p):
  key=(node,tuple(p) if p is not None else None)
  if key not in pm:
   q=list(pf.snap_point(p)) if p is not None else select_camera_seed(pf,ids[('mJXqzFtmKg4',node)]['camera_position'])
   pm[key]=q if q is not None and all(math.isfinite(x) for x in q) and (p is None or math.dist(p,q)<=.5) else None
  return pm[key]
 for t in ts:
  ps=[point(n,p) for n,p in zip(t['original_viewpoint_path'],t['targets'])];ok=all(p is not None for p in ps);dist=[]
  if ok:
   for a,c in zip(ps,ps[1:]):
    q=habitat_sim.ShortestPath();q.requested_start=a;q.requested_end=c;valid=pf.find_path(q) and math.isfinite(q.geodesic_distance);dist.append(float(q.geodesic_distance) if valid else None)
    if not valid:ok=False
  old=t['status']=='READY_FOR_NATIVE_MOTION';counts['pass' if ok else 'blocked']+=1;counts['regressions']+=old and not ok;counts['recoveries']+=not old and ok;rows.append({'task_key':t['task_key'],'pass':ok,'distances':dist})
 reports[name]={'mesh_sha256':digest(path),'counts':dict(counts),'tasks':rows};pointmaps[name]=pm;print(name,dict(counts),flush=True)
ref=pointmaps['habitat_old'];control=pointmaps['standalone_old'];mismatches=[];max_delta=0
for k,a in ref.items():
 c=control[k]
 if (a is None)!=(c is None):mismatches.append(str(k))
 elif a is not None:max_delta=max(max_delta,math.dist(a,c))
state_mismatch=sum(a['pass']!=c['pass'] for a,c in zip(reports['habitat_old']['tasks'],reports['standalone_old']['tasks']));receipt={'status':'CONTROL_MATCH' if not mismatches and max_delta<=1e-5 and state_mismatch==0 else 'CONTROL_MISMATCH','max_point_delta':max_delta,'point_presence_mismatches':mismatches,'task_pass_mismatches':state_mismatch,'reports':reports,'script_sha256':digest(__file__),'limits':'Real native PathFinder load and static all-scene screen; final source-anchor joint selection and actual motion still mandatory.'};atomic_json(run/'static-control-audit.json',receipt);print(receipt['status'],max_delta,state_mismatch)
