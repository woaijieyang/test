"""Independently validate full identity coverage and every recorded native trace."""
import os,json,gzip,sys,math,collections,datetime
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,owned,atomic_json,digest
if not os.environ.get('CASE1_PROTECTION'):raise RuntimeError('Protected runtime required')
os.environ['CUDA_VISIBLE_DEVICES']='';os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:1])
import habitat_sim
from habitat_sim.utils.common import quat_from_coeffs
run=ROOT/'outputs/landmark-connectivity/full-native-v11';m=json.loads((run/'manifest.json').read_text());msha=digest(run/'manifest.json');binding=json.loads((run/'validation-code-binding.json').read_text());assert binding['manifest_sha256']==msha and binding['actual_validator_sha256']==digest(__file__);assert digest(m['profile_path'])==m['profile_sha256'];profile=json.loads(Path(m['profile_path']).read_text());tasks={t['task_key']:t for t in m['tasks']};assert len(tasks)==33954
for source in m['sources']+m['mapping_evidence']:assert digest(source['path'])==source['sha256']
rows=[json.loads(p.read_text()) for p in run.glob('shard-*/*.result.json')];keys=[r['task_key'] for r in rows];assert len(keys)==len(set(keys))==33954 and set(keys)==set(tasks)
cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id='NONE';cfg.create_renderer=False;cfg.enable_physics=False;agent=habitat_sim.agent.AgentConfiguration();agent.height=1.5;agent.radius=.1;agent.sensor_specifications=[];agent.action_space={1:habitat_sim.agent.ActionSpec('move_forward',habitat_sim.agent.ActuationSpec(amount=.25)),2:habitat_sim.agent.ActionSpec('turn_left',habitat_sim.agent.ActuationSpec(amount=15)),3:habitat_sim.agent.ActionSpec('turn_right',habitat_sim.agent.ActuationSpec(amount=15))};sim=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[agent]));current=None;counts=collections.Counter();split_counts=collections.defaultdict(collections.Counter);issues=[];replay_max=0;failure_kinds=collections.Counter();query=habitat_sim.ShortestPath()
try:
 for row in sorted(rows,key=lambda r:(r['scene'],r['task_key'])):
  key=row['task_key'];task=tasks[key];assert row['manifest_sha256']==msha and row['source_record_sha256']==task['source_record_sha256'];counts[row['status']]+=1;split_counts[task['split']][row['status']]+=1
  if row['status']=='STATIC_BLOCKED_PRESERVED':assert row['errors']==task['static_errors'];continue
  tracepath=owned(run/row['trace_path']);assert digest(tracepath)==row['trace_sha256'];trace=json.load(gzip.open(tracepath,'rt'));assert trace['task_key']==key and trace['manifest_sha256']==msha and trace['targets']==task['targets'];assert len(trace['positions'])==len(trace['actions'])+1
  sc=task['scene'];asset=profile['assets'][f'mp3d/{sc}/{sc}.glb'];assert trace['mesh_sha256']==asset['navmesh_sha256']
  if current!=sc:assert digest(asset['navmesh_path'])==asset['navmesh_sha256'];assert sim.pathfinder.load_nav_mesh(asset['navmesh_path']);current=sc
  state=habitat_sim.AgentState();state.position=task['targets'][0];state.rotation=quat_from_coeffs(trace['rotation']);sim.initialize_agent(0,state);error=math.dist(sim.get_agent(0).get_state().position.tolist(),trace['positions'][0]);bad=[]
  for i,action in enumerate(trace['actions']):
   assert action in (1,2,3);sim.step(action);pos=sim.get_agent(0).get_state().position.tolist();error=max(error,math.dist(pos,trace['positions'][i+1]));counts['actual_actions']+=1
   if not sim.pathfinder.is_navigable(pos):bad.append('offmesh_actual_position')
   if abs(pos[1]-trace['positions'][i][1])>.5:bad.append('vertical_step_exceeded')
   query.requested_start=pos;query.requested_end=task['targets'][-1]
   if not sim.pathfinder.find_path(query) or not math.isfinite(query.geodesic_distance):bad.append('actual_position_unreachable')
  replay_max=max(replay_max,error)
  if error>1e-5:issues.append({'task_key':key,'kind':'replay_mismatch','max_error':error})
  if row['status']=='PASS':
   if bad:issues.append({'task_key':key,'kind':'invalid_PASS','details':sorted(set(bad))})
   assert len(trace['reached_reference_boundaries'])==len(task['targets'])-1
   for boundary in trace['reached_reference_boundaries']:
    query.requested_start=trace['positions'][boundary['action_index']];query.requested_end=task['targets'][boundary['reference_index']]
    if not sim.pathfinder.find_path(query) or query.geodesic_distance>.250001:issues.append({'task_key':key,'kind':'reference_boundary_not_reached'})
  else:
   assert trace['errors']
   for e in trace['errors']:failure_kinds[e.get('error',e['kind'])]+=1
finally:sim.close()
report={'status':'PASS' if not issues and counts['PASS']==33954 else 'COMPLETE_NOT_ACCEPTED','scope':'all_33954_records_retained; execute_and_independently_replay_every_statically_eligible_record','coverage_complete':True,'manifest_sha256':msha,'counts':dict(counts),'split_counts':{k:dict(v) for k,v in split_counts.items()},'audit_issues':issues,'failure_kinds':dict(failure_kinds),'max_independent_replay_error':replay_max,'time':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),'validator_sha256':digest(__file__),'limits':'Static-blocked records remain in the full denominator and prevent acceptance. Oracle/native diagnostics are not AwareVLN model scores.'};atomic_json(run/'validation.json',report);print(json.dumps(report))
