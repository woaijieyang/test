import os,sys,json,gzip,math,collections
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
if not os.environ.get('CASE1_PROTECTION'):raise RuntimeError('Protected runtime required')
os.environ['CUDA_VISIBLE_DEVICES']='';os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[4:5])
import habitat_sim
from habitat_sim.utils.common import quat_from_coeffs
run=ROOT/'outputs/landmark-connectivity/official-action-replay';summary=json.loads((run/'summary.json').read_text());m=json.loads(Path('outputs/landmark-connectivity/full-native-v1/manifest.json').read_text());tasks={t['task_key']:t for t in m['tasks']};profile=json.loads(Path(m['profile_path']).read_text());ce=Path('/data/zy/vln/data/raw_data/eval_annotations/rxr_vlnce_v0');cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id='NONE';cfg.create_renderer=False;cfg.enable_physics=False;agent=habitat_sim.agent.AgentConfiguration();agent.height=1.5;agent.radius=.1;agent.sensor_specifications=[];agent.action_space={1:habitat_sim.agent.ActionSpec('move_forward',habitat_sim.agent.ActuationSpec(amount=.25)),2:habitat_sim.agent.ActionSpec('turn_left',habitat_sim.agent.ActuationSpec(amount=15)),3:habitat_sim.agent.ActionSpec('turn_right',habitat_sim.agent.ActuationSpec(amount=15))};sim=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[agent]));results=[];current=None
try:
 for split in ('train','val_seen','val_unseen'):
  epfile=ce/split/f'{split}_guide.json.gz';gp=ce/split/f'{split}_guide_gt.json.gz';episodes={str(e['instruction']['instruction_id']):e for e in json.load(gzip.open(epfile,'rt'))['episodes']};gt=json.load(gzip.open(gp,'rt'))
  for r in summary['records']:
   if r['status']!='MOTION_PASS_PENDING_INDEPENDENT_REPLAY':continue
   task=tasks[r['task_key']]
   if task['split']!=split:continue
   tracepath=run/r['trace'];trace=json.load(gzip.open(tracepath,'rt'));e=episodes[task['instruction_id']];actions=[]
   for action in gt[str(e['episode_id'])]['actions']:
    action=int(action)
    if action==0:break
    assert action in (1,2,3);actions.extend([action]*(2 if action in (2,3) else 1))
   assert trace['actions']==actions and trace['start_rotation']==e['start_rotation'];assert trace['positions'][0]==task['targets'][0] or math.dist(trace['positions'][0],task['targets'][0])<1e-5
   sc=task['scene'];asset=profile['assets'][f'mp3d/{sc}/{sc}.glb'];assert digest(asset['navmesh_path'])==asset['navmesh_sha256']
   if sc!=current:assert sim.pathfinder.load_nav_mesh(asset['navmesh_path']);current=sc
   state=habitat_sim.AgentState();state.position=task['targets'][0];state.rotation=quat_from_coeffs(e['start_rotation']);sim.initialize_agent(0,state);maxerr=0.;errors=[];index=1
   for i,action in enumerate(actions):
    sim.step(action);pos=sim.get_agent(0).get_state().position.tolist();maxerr=max(maxerr,math.dist(pos,trace['positions'][i+1]));before=trace['positions'][i]
    if not sim.pathfinder.is_navigable(pos):errors.append('offmesh')
    if abs(pos[1]-before[1])>.5:errors.append('vertical_step')
    q=habitat_sim.ShortestPath();q.requested_start=pos;q.requested_end=task['targets'][-1]
    if not sim.pathfinder.find_path(q) or not math.isfinite(q.geodesic_distance):errors.append('unreachable_final_goal')
    while index<len(task['targets']):
     q.requested_start=pos;q.requested_end=task['targets'][index]
     if sim.pathfinder.find_path(q) and q.geodesic_distance<=.25:index+=1
     else:break
   if index!=len(task['targets']):errors.append('missing_ordered_target')
   if maxerr>1e-5:errors.append('replay_error')
   results.append({'task_key':task['task_key'],'status':'PASS' if not errors else 'FAIL','errors':sorted(set(errors)),'max_replay_error':maxerr,'trace_sha256':digest(tracepath),'steps':len(actions)})
finally:sim.close()
report={'status':'PASS' if len(results)==109 and all(r['status']=='PASS' for r in results) else 'FAIL','scope':'109_official_action_replay_candidates_only_not_full_dataset','counts':dict(collections.Counter(r['status'] for r in results)),'results':results,'max_replay_error':max(r['max_replay_error'] for r in results),'validator_sha256':digest(__file__)};atomic_json(run/'validation.json',report);print(json.dumps({k:v for k,v in report.items() if k!='results'}))
