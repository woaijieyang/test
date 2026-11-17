"""Counterexample test: exact official action replay versus failed greedy navigation."""
import os,sys,json,gzip,math,collections,hashlib
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
if not os.environ.get('CASE1_PROTECTION'):raise RuntimeError('Protected runtime required')
os.environ['CUDA_VISIBLE_DEVICES']='';os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:1])
import habitat_sim
from habitat_sim.utils.common import quat_from_coeffs
run=ROOT/'outputs/landmark-connectivity/full-native-v1';m=json.loads((run/'manifest.json').read_text());tasks={t['task_key']:t for t in m['tasks']};failed=[json.loads(p.read_text()) for p in run.glob('shard-*/*.result.json') if json.loads(p.read_text())['status']=='FAIL'];profile=json.loads(Path(m['profile_path']).read_text());out=ROOT/'outputs/landmark-connectivity/official-action-replay';out.mkdir(exist_ok=False);ce=Path('/data/zy/vln/data/raw_data/eval_annotations/rxr_vlnce_v0');cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id='NONE';cfg.create_renderer=False;cfg.enable_physics=False;agent=habitat_sim.agent.AgentConfiguration();agent.height=1.5;agent.radius=.1;agent.sensor_specifications=[];agent.action_space={1:habitat_sim.agent.ActionSpec('move_forward',habitat_sim.agent.ActuationSpec(amount=.25)),2:habitat_sim.agent.ActionSpec('turn_left',habitat_sim.agent.ActuationSpec(amount=15)),3:habitat_sim.agent.ActionSpec('turn_right',habitat_sim.agent.ActuationSpec(amount=15))};sim=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[agent]));records=[];current=None
try:
 for split in ('train','val_seen','val_unseen'):
  epfile=ce/split/f'{split}_guide.json.gz';gtfile=ce/split/f'{split}_guide_gt.json.gz';eps={str(e['instruction']['instruction_id']):e for e in json.load(gzip.open(epfile,'rt'))['episodes']};gt=json.load(gzip.open(gtfile,'rt'))
  for old in failed:
   task=tasks[old['task_key']]
   if task['split']!=split:continue
   e=eps.get(task['instruction_id']);r={'task_key':task['task_key'],'original_failure':old['errors'],'scene':task['scene']}
   if e is None:r['status']='NO_OFFICIAL_GT';records.append(r);continue
   sc=task['scene'];asset=profile['assets'][f'mp3d/{sc}/{sc}.glb']
   if sc!=current:assert sim.pathfinder.load_nav_mesh(asset['navmesh_path']);current=sc
   state=habitat_sim.AgentState();state.position=task['targets'][0];state.rotation=quat_from_coeffs(e['start_rotation']);sim.initialize_agent(0,state);positions=[sim.get_agent(0).get_state().position.tolist()];actions=[];errors=[];index=1
   original_actions=gt[str(e['episode_id'])]['actions'];expanded=[]
   for action in original_actions:
    action=int(action)
    if action==0:break
    if action not in (1,2,3):errors.append({'kind':'unsupported_official_action','action':action});break
    expanded.extend([action]*(2 if action in (2,3) else 1))
   for action in expanded:
    sim.step(action);point=sim.get_agent(0).get_state().position.tolist();before=positions[-1];positions.append(point);actions.append(action)
    if not sim.pathfinder.is_navigable(point):errors.append({'kind':'offmesh_position'});break
    if abs(point[1]-before[1])>.5:errors.append({'kind':'vertical_step_exceeded'});break
    while index<len(task['targets']):
     q=habitat_sim.ShortestPath();q.requested_start=point;q.requested_end=task['targets'][index]
     if sim.pathfinder.find_path(q) and q.geodesic_distance<=.25:index+=1
     else:break
   if index<len(task['targets']):errors.append({'kind':'unreached_ordered_targets','next_index':index})
   r.update(status='MOTION_PASS_PENDING_INDEPENDENT_REPLAY' if not errors else 'FAIL',errors=errors,actions=len(actions),reached_targets=index,expected_targets=len(task['targets']),ce_episode_id=str(e['episode_id']));records.append(r);trace={'task_key':task['task_key'],'start_rotation':e['start_rotation'],'positions':positions,'actions':actions,'errors':errors,'mesh_sha256':asset['navmesh_sha256']};name=hashlib.sha256(task['task_key'].encode()).hexdigest()[:24]+'.json.gz';(out/name).write_bytes(gzip.compress(json.dumps(trace,separators=(',',':')).encode(),mtime=0));r['trace']=name
  print(split,dict(collections.Counter(r['status'] for r in records)),flush=True)
finally:sim.close()
summary={'status':'DIAGNOSTIC_COMPLETE','counts':dict(collections.Counter(r['status'] for r in records)),'records':records,'script_sha256':digest(__file__),'conversion':'Official RxR 30-degree turns expanded to two 15-degree primitive actions; same .25m forward; initial rotation from matching official episode; no state correction mid-trajectory.'};atomic_json(out/'summary.json',summary)
