"""Full660-record accounting; exact native replay for40 actual-pose-clear traces.
Alternative step curves remain hypothetical and cannot clear existing acceptance gates.
"""
import os,sys,json,gzip,hashlib,struct,math,subprocess,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import atomic_json,digest
from swept_cylinder_reference import triangle_linear_sweep_distance
import numpy as np,habitat_sim,psutil
from habitat_sim.utils.common import quat_from_coeffs
u=psutil.cpu_percent(interval=1,percpu=True);eligible=[i for i in sorted(os.sched_getaffinity(0))[:64] if i not in [6,10,11,12,13,15,18,20,22,24,27,30]];os.sched_setaffinity(0,[min(eligible,key=lambda i:u[i])])
B=R/'outputs/landmark-connectivity';O=B/'pRb-original-trace-step-interpretation-v1';O.mkdir(exist_ok=False);atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]});parent=B/'full-native-v11';m=json.loads((parent/'manifest.json').read_text());sc='pRbA3pwrgk9';tasks={t['task_key']:t for t in m['tasks'] if t['scene']==sc};assert len(tasks)==660;profile=json.loads(Path(m['profile_path']).read_text());asset=profile['assets'][f'mp3d/{sc}/{sc}.glb'];assert digest(asset['navmesh_path'])==asset['navmesh_sha256'];headers=json.loads(subprocess.check_output([str(R/'.cache/navmesh-header-probe/probe'),asset['navmesh_path']],text=True));assert len(headers)==1 and abs(headers[0]['height']-1.5)<1e-6 and abs(headers[0]['radius']-.1)<1e-6;climb=headers[0]['climb']
screen_path=B/'full-source-geometry-v1/scenes'/sc/'validation.json';screen=json.loads(screen_path.read_text());rows_by_key={r['task_key']:r for r in screen['rows']};assert set(rows_by_key)==set(tasks);confirmed_path=B/f'full-source-native-{sc}-v1/actual-position-confirmation.json';confirmed=json.loads(confirmed_path.read_text());blocked=set(confirmed['task_keys_with_native_confirmed_actual_alerts']);assert len(blocked)==620 and blocked=={r['task_key'] for r in screen['rows'] if r['actual_position_contacts']>0};geo_path=B/f'full-source-native-{sc}-v1/validation.json';geo=json.loads(geo_path.read_text());gp=Path(geo['native_geometry_path']);assert digest(gp)==geo['native_geometry_sha256'];raw=gp.read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);vertices=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);ix=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);tri=vertices[ix].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1);cache={};regions={}
def sweep(a,b):
 key=(tuple(a),tuple(b))
 if key in cache:return cache[key]
 a=np.array(a);b=np.array(b);low=np.minimum(a,b);high=np.maximum(a,b);cell=tuple(np.floor(low/.5).astype(int));topcell=tuple(np.floor(high/.5).astype(int));rk=(cell,topcell)
 if rk not in regions:
  lowbox=np.array(cell)*.5;highbox=(np.array(topcell)+1)*.5;regions[rk]=np.flatnonzero((lo[:,0]<highbox[0]+.1)&(hi[:,0]>lowbox[0]-.1)&(lo[:,2]<highbox[2]+.1)&(hi[:,2]>lowbox[2]-.1)&(lo[:,1]<highbox[1]+1.5)&(hi[:,1]>lowbox[1]+1e-5))
 hit=None
 for j in regions[rk]:
  if lo[j,0]>=high[0]+.1 or hi[j,0]<=low[0]-.1 or lo[j,2]>=high[2]+.1 or hi[j,2]<=low[2]-.1 or lo[j,1]>=high[1]+1.5 or hi[j,1]<=low[1]+1e-5:continue
  d=triangle_linear_sweep_distance(tri[j],a,b)
  if d<.1-1e-6:hit={'native_triangle':int(j),'distance':d};break
 cache[key]=hit;return hit
cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id='NONE';cfg.create_renderer=False;cfg.enable_physics=False;a=habitat_sim.agent.AgentConfiguration();a.height=1.5;a.radius=.1;a.sensor_specifications=[];a.action_space={1:habitat_sim.agent.ActionSpec('move_forward',habitat_sim.agent.ActuationSpec(amount=.25)),2:habitat_sim.agent.ActionSpec('turn_left',habitat_sim.agent.ActuationSpec(amount=15)),3:habitat_sim.agent.ActionSpec('turn_right',habitat_sim.agent.ActuationSpec(amount=15))};sim=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[a]));assert sim.pathfinder.load_nav_mesh(asset['navmesh_path']);reports=[]
for key,t in sorted(tasks.items()):
 source=rows_by_key[key]
 if key in blocked:
  reports.append({'task_key':key,'status':'BLOCKED_NATIVE_CONFIRMED_ACTUAL_BODY_CONTACT_PRESERVED','source_record_sha256':t['source_record_sha256'],'source_result_sha256':source['result_sha256'],'native_confirmation_sha256':digest(confirmed_path),'replayed_here':False});continue
 rp=Path(source['result_path']);assert digest(rp)==source['result_sha256'];r=json.loads(rp.read_text());assert r['status']=='PASS' and r['source_record_sha256']==t['source_record_sha256'];tp=parent/r['trace_path'];assert digest(tp)==r['trace_sha256'];trace=json.load(gzip.open(tp,'rt'));assert trace['task_key']==key and trace['targets']==t['targets'] and trace['mesh_sha256']==asset['navmesh_sha256'];assert len(trace['positions'])==len(trace['actions'])+1 and len(trace['actions'])<=10000
 state=habitat_sim.AgentState();state.position=t['targets'][0];state.rotation=quat_from_coeffs(trace['rotation']);sim.initialize_agent(0,state);positions=[sim.get_agent(0).get_state().position.tolist()];maximum_error=math.dist(positions[0],trace['positions'][0]);pose_alerts=[];certificates=[];unresolved=[]
 hit=sweep(positions[0],positions[0])
 if hit:pose_alerts.append({'position_index':0,**hit})
 for i,action in enumerate(trace['actions'],1):
  start=positions[-1];sim.step(action);end=sim.get_agent(0).get_state().position.tolist();positions.append(end);maximum_error=max(maximum_error,math.dist(end,trace['positions'][i]));assert sim.pathfinder.is_navigable(end) and abs(end[1]-start[1])<=.5
  actual=sweep(end,end)
  if actual:pose_alerts.append({'position_index':i,**actual})
  direct=sweep(start,end)
  if direct:
   delta=abs(end[1]-start[1]);corner=None;step_hits=None
   if action==1 and 1e-5<delta<=climb and math.hypot(end[0]-start[0],end[2]-start[2])<=.25+1e-5:
    corner=[end[0],start[1],end[2]] if end[1]<start[1] else [start[0],end[1],start[2]];step_hits=[sweep(start,corner),sweep(corner,end)]
   rec={'action_index':i,'start':start,'end':end,'direct_contact':direct,'step_corner':corner,'step_contacts':step_hits,'actual_internal_curve_observed':False}
   if corner is not None and not any(step_hits):certificates.append(rec)
   else:unresolved.append(rec)
 prev=0
 for bound in trace['reached_reference_boundaries']:
  n=bound['action_index'];j=bound['reference_index'];assert prev<=n<len(positions) and n-prev<=1500;prev=n;q=habitat_sim.ShortestPath();q.requested_start=positions[n];q.requested_end=t['targets'][j];assert sim.pathfinder.find_path(q) and q.geodesic_distance<=.25
 assert maximum_error<=1e-5 and len(trace['reached_reference_boundaries'])==len(t['targets'])-1
 status='NATIVE_ACTUAL_BODY_CONTACT_FOUND' if pose_alerts else 'UNRESOLVED_CONTINUOUS_SOURCE_CONTACT' if unresolved else 'STEP_REALIZATION_EXISTS_PROTOCOL_REVIEW_REQUIRED' if certificates else 'LINEAR_CONTINUOUS_SOURCE_CLEAR_DIAGNOSTIC'
 report={'task_key':key,'status':status,'actions_replayed':len(trace['actions']),'max_replay_error':maximum_error,'actual_pose_alerts':pose_alerts,'hypothetical_step_certificates':certificates,'unresolved_transitions':unresolved,'trace_sha256':r['trace_sha256'],'source_record_sha256':t['source_record_sha256'],'replayed_here':True,'source_actions_changed':False,'source_endpoints_changed':False};atomic_json(O/(key.replace(':','-')+'.json'),report);reports.append({k:v for k,v in report.items() if k not in ['actual_pose_alerts','hypothetical_step_certificates','unresolved_transitions']});atomic_json(O/'state.json',{'status':'RUNNING','records':len(reports),'fresh_replayed':sum(x['replayed_here'] for x in reports)})
sim.close();import collections;counts=dict(collections.Counter(r['status'] for r in reports));assert len(reports)==660 and len({r['task_key'] for r in reports})==660 and sum(r['replayed_here'] for r in reports)==40
atomic_json(O/'validation.json',{'status':'COMPLETE_INTERPRETATION_DIAGNOSTIC_NOT_ACCEPTANCE','records':reports,'counts':counts,'scene_tasks':660,'global_denominator':33954,'fresh_replayed_records':40,'retained_actual_contact_records':620,'body_height':1.5,'body_radius':.1,'climb_upper_bound_from_native_header':climb,'source_screen_sha256':digest(screen_path),'native_confirmation_sha256':digest(confirmed_path),'native_geometry_receipt_sha256':digest(geo_path),'script_sha256':digest(__file__),'sweep_helper_sha256':digest(R/'tests/landmark_diagnostics/swept_cylinder_reference.py'),'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'limits':'Existing strict straight-sweep failures are retained. A collision-free bounded piecewise curve is an existence certificate, NOT an observed native internal trajectory or adopted protocol. No acceptance status, criteria, mesh, target, budget or model result changed.'});atomic_json(O/'state.json',{'status':'COMPLETE_INTERPRETATION_DIAGNOSTIC_NOT_ACCEPTANCE','counts':counts});print(counts)
