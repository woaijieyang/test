"""Independent exhaustive benchmark/recorded-trajectory connectivity acceptance."""
import argparse,hashlib,json,math,os,sys,datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from workspace import ROOT,owned,read_json,atomic_json,digest
from preflight import SPECS,dataset_base,load,task_key

def main():
 p=argparse.ArgumentParser();p.add_argument('--profile',required=True);p.add_argument('--run');p.add_argument('--output',required=True);a=p.parse_args()
 if not os.environ.get('CASE1_PROTECTION'):raise RuntimeError('Use protected runtime')
 os.environ['CUDA_VISIBLE_DEVICES']=''
 import habitat_sim
 profile_path=Path(a.profile).resolve();profile=read_json(profile_path)
 if profile['agent']!={'height':1.5,'radius':.1}:raise RuntimeError('Body changed')
 finders={};errors=[];counts={'tasks':0,'points_checked':0,'goal_path_queries':0,'segment_queries':0};evidence=[]
 def finder(scene):
  if scene not in finders:
   asset=profile['assets'][scene];mesh=Path(asset['navmesh_path'])
   if digest(mesh)!=asset['navmesh_sha256']:raise RuntimeError('Mesh drift '+scene)
   pf=habitat_sim.PathFinder()
   if not pf.load_nav_mesh(str(mesh)):raise RuntimeError('Cannot load mesh '+scene)
   finders[scene]=pf
  return finders[scene]
 def error(key,kind,**values):errors.append({'task_key':key,'kind':kind,**values})
 def valid(point):return len(point)==3 and all(isinstance(v,(int,float)) and math.isfinite(v) for v in point)
 def path(pf,start,end):
  query=habitat_sim.ShortestPath();query.requested_start=start;query.requested_end=end
  return bool(pf.find_path(query)) and math.isfinite(query.geodesic_distance)
 def points(key,pf,values,goals,kind,require_navigable=False):
  for index,point in enumerate(values):
   counts['points_checked']+=1
   if not valid(point):error(key,'nonfinite_position',section=kind,index=index);continue
   if require_navigable and not pf.is_navigable(point):error(key,'offmesh_position',section=kind,index=index,position=point)
   for goal in goals:
    counts['goal_path_queries']+=1
    if not path(pf,point,goal):error(key,'unreachable_goal',section=kind,index=index,position=point,goal=goal)
  for index,(start,end) in enumerate(zip(values,values[1:])):
   counts['segment_queries']+=1
   if valid(start) and valid(end) and not path(pf,start,end):error(key,'unreachable_adjacent_segment',section=kind,index=index,start=start,end=end)
 datasets={};gt={}
 for ds,spec in SPECS.items():
  base=dataset_base(ds);annotation=base/spec[1];gtpath=base/spec[2]
  episodes=[ep for ep in load(annotation)['episodes'] if ds!='rxr' or ep['instruction']['language']=='en-US']
  if len(episodes)!=spec[3]:raise RuntimeError('Wrong full cohort '+ds)
  datasets[ds]={task_key(ds,e):e for e in episodes};gt[ds]=load(gtpath)
  evidence.extend([{'path':str(annotation),'sha256':digest(annotation)},{'path':str(gtpath),'sha256':digest(gtpath)}])
 dataset_counts={};trace_receipts=[];expected_count=3062
 if not a.run:
  for ds,episodes in datasets.items():
   for key,ep in episodes.items():
    pf=finder(ep['scene_id']);goals=[g['position'] for g in ep['goals']]
    points(key,pf,[ep['start_position'],*goals],goals,'endpoints',True)
    points(key,pf,[ep['start_position'],*gt[ds][str(ep['episode_id'])]['locations'],*goals],goals,'dense_reference')
    points(key,pf,[ep['start_position'],*ep.get('reference_path',[]),*goals],goals,'sparse_reference')
    counts['tasks']+=1
   dataset_counts[ds]=len(episodes)
  scope='all_3062_endpoints_dense_and_sparse_reference_connectivity'
 else:
  import re
  run=owned(a.run);manifest=read_json(run/'run_manifest.json')
  if digest(profile_path)!=manifest['navmesh_sha256']:raise RuntimeError('Run uses different mesh profile')
  for ds,spec in manifest['datasets'].items():
   if digest(spec['annotation'])!=digest(dataset_base(ds)/SPECS[ds][1]) or digest(spec['gt'])!=digest(dataset_base(ds)/SPECS[ds][2]):raise RuntimeError('Run annotation/GT identity mismatch')
  records=[json.loads(line) for line in (run/'results.jsonl').read_text().splitlines() if line.strip()]
  expected={r['task_key'] for r in manifest['expected_tasks']};keys=[r['task_key'] for r in records]
  if len(keys)!=len(set(keys)) or set(keys)!=expected:raise RuntimeError('Run incomplete or duplicate; no partial PASS')
  expected_count=len(expected)
  if manifest['scope']=='full':
   authoritative=set().union(*(set(datasets[ds]) for ds in manifest['datasets']))
   if expected!=authoritative:raise RuntimeError('Formal run is not the exact full dataset')
  configs={}
  for row in records:
   key=row['task_key'];ds=row['dataset'];ep=datasets[ds][key];pf=finder(ep['scene_id']);goals=[g['position'] for g in ep['goals']]
   config_path=owned(run/row['effective_config_path'])
   if digest(config_path)!=row['effective_config_sha256']:raise RuntimeError('Effective configuration drift')
   if str(config_path) not in configs:
    # YACS __str__ includes Python tuple representations, so it is not YAML.
    # Read only unambiguous indentation-qualified scalar fields; never eval.
    stack=[];scalars={}
    for line in config_path.read_text().splitlines():
     match=re.match(r'^( *)([A-Za-z0-9_]+):(?: (.*))?$',line)
     if not match:continue
     indent=len(match.group(1));name=match.group(2);value=match.group(3)
     while stack and stack[-1][0]>=indent:stack.pop()
     scalar_key='.'.join([item[1] for item in stack]+[name])
     if value is None or not value.strip():stack.append((indent,name))
     else:
      if scalar_key in scalars:raise RuntimeError('Ambiguous duplicate effective config scalar')
      scalars[scalar_key]=value.strip()
    configs[str(config_path)]=scalars
   config=configs[str(config_path)]
   if float(config['TASK_CONFIG.SIMULATOR.AGENT_0.HEIGHT'])!=1.5 or float(config['TASK_CONFIG.SIMULATOR.AGENT_0.RADIUS'])!=.1:raise RuntimeError('Actual runtime body mismatch')
   view=Path(config['TASK_CONFIG.DATASET.SCENES_DIR'])
   expected_view=ROOT/'data/derived/evaluation-scenes'/hashlib.sha256(json.dumps(profile,sort_keys=True).encode()).hexdigest()[:16]
   if view.resolve()!=expected_view.resolve():raise RuntimeError('Actual scene-view identity mismatch')
   scene=view/ep['scene_id'];mesh=scene.with_suffix('.navmesh')
   if digest(mesh)!=profile['assets'][ep['scene_id']]['navmesh_sha256']:raise RuntimeError('Actual selected scene-view mesh mismatch')
   trace=owned(run/row['trace_path'])
   if digest(trace)!=row['trace_sha256']:raise RuntimeError('Trace drift')
   events=[json.loads(line) for line in trace.read_text().splitlines() if line.strip()]
   if not events or events[0]['kind']!='reset' or events[-1]['kind']!='terminal':raise RuntimeError('Unclosed actual trajectory')
   positions=[events[0]['state_evaluator_only']['position']]
   if math.dist(positions[0],ep['start_position'])>1e-4:error(key,'reset_position_mismatch')
   for event in events:
    if event['task_key']!=key:raise RuntimeError('Cross-episode evidence')
    if event['kind']=='primitive_action':
     before=event['before_evaluator_only']['position'];after=event['after_evaluator_only']['position']
     if math.dist(positions[-1],before)>1e-5:error(key,'trajectory_gap')
     positions.append(after)
   points(key,pf,positions,goals,'actual_execution',True)
   counts['tasks']+=1;dataset_counts[ds]=dataset_counts.get(ds,0)+1
   trace_receipts.append({'task_key':key,'trace_sha256':row['trace_sha256'],'positions':len(positions)})
  evidence.extend([{'path':str(run/'run_manifest.json'),'sha256':digest(run/'run_manifest.json')},{'path':str(run/'results.jsonl'),'sha256':digest(run/'results.jsonl')}])
  scope=manifest['scope']+'_actual_trajectory_connectivity'
 assert counts['tasks']==expected_count
 report={'status':'PASS' if not errors else 'FAIL','checked_at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),'scope':scope,'counts':counts,'dataset_counts':dataset_counts,'unreachable_or_invalid_count':len(errors),'errors':errors,'profile_sha256':digest(profile_path),'auditor_sha256':digest(__file__),'evidence':evidence,'traces':trace_receipts,'limits':'Proof covers authorized episodes/references and every recorded actual position, not arbitrary unused MP3D mesh islands. Original reference points are checked for connectivity, not silently projected or rewritten.'}
 atomic_json(owned(a.output),report);print(json.dumps({k:report[k] for k in ('status','scope','counts','unreachable_or_invalid_count')}))
 if errors:raise SystemExit('Strict connectivity acceptance failed')
if __name__=='__main__':main()
