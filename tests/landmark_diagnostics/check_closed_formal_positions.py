"""Read-only snapshot diagnostic of completed formal episodes; never a full PASS."""
import os,sys,json,gzip,math,datetime
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
if not os.environ.get('CASE1_PROTECTION'):raise RuntimeError('Protected runtime required')
os.environ['CUDA_VISIBLE_DEVICES']='';os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[5:6])
import habitat_sim
run=ROOT/'outputs/awarevln-r2r-valunseen-endpoint9-20261015-v2';m=json.loads((run/'run_manifest.json').read_text());pp=ROOT/'data/derived/navmeshes/awarevln-scene-minimal-endpoint9-v2/profile.json';assert digest(pp)==m['navmesh_sha256'];profile=json.loads(pp.read_text());eps=json.load(gzip.open(m['datasets']['r2r']['annotation'],'rt'))['episodes'];epmap={(e['scene_id'],str(e['episode_id'])):e for e in eps};finders={};errors=[];count=0;points=0;keys=[]
for p in list(run.glob('shards/*/attempt-*/episodes/*/result.json')):
 row=json.loads(p.read_text());key=row['task_key'];parts=key.split('|');sc=parts[3];ep=epmap[(sc,parts[4])];trace=p.parent/'trace.jsonl';assert digest(trace)==row['trace_sha256']
 if sc not in finders:
  pf=habitat_sim.PathFinder();asset=profile['assets'][sc];assert digest(asset['navmesh_path'])==asset['navmesh_sha256'];assert pf.load_nav_mesh(asset['navmesh_path']);finders[sc]=pf
 pf=finders[sc]
 for line in trace.read_text().splitlines():
  e=json.loads(line);position=e['state_evaluator_only']['position'] if e['kind']=='reset' else e['after_evaluator_only']['position'] if e['kind']=='primitive_action' else None
  if position is None:continue
  points+=1
  if not pf.is_navigable(position):errors.append({'task_key':key,'kind':'offmesh_actual_position','position':position,'step':e.get('primitive_step',e.get('step'))})
  for goal in ep['goals']:
   q=habitat_sim.ShortestPath();q.requested_start=position;q.requested_end=goal['position']
   if not pf.find_path(q) or not math.isfinite(q.geodesic_distance):errors.append({'task_key':key,'kind':'unreachable_actual_position','position':position})
 count+=1;keys.append(key)
report={'status':'SNAPSHOT_FAIL' if errors else 'SNAPSHOT_NO_ERRORS_NOT_FULL_ACCEPTANCE','completed_episodes_checked':count,'positions_checked':points,'error_count':len(errors),'affected_episodes':len(set(e['task_key'] for e in errors)),'errors':errors,'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'profile_sha256':digest(pp),'scope':'Only closed immutable traces at snapshot start; no model calls or running artifact changes.'};out=ROOT/'outputs/landmark-connectivity/formal-closed-position-snapshot.json';atomic_json(out,report);print(json.dumps({k:v for k,v in report.items() if k!='errors'}));print(errors[:3])
