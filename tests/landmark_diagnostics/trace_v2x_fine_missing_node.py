"""Observe why an existing fine mesh loses a previously usable V2X shared node."""
import os,sys,json,time,subprocess,datetime,math
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
R=Path.cwd();sys.path[:0]=[str(R/'.cache/native-stage-trace-xc-v1'),str(R/'scripts')]
from workspace import atomic_json,digest
import psutil
B=R/'outputs/landmark-connectivity';O=B/'v2x-fine-missing-node-stage-v1';O.mkdir(exist_ok=False);atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]});scene='V2XKFyX4ASd';node='719c98cc49cd4ea4bdfa1094f30c54d9';proposal=B/'V2X-grounded-fine05-supported-v1/validation.json';p=json.loads(proposal.read_text());options=[r for r in p['nodes'] if r['node']==node and r['original_target'] is not None and r['original_body_contact'] is None];assert options;chosen=min(options,key=lambda r:math.dist(r['original_target'],r['anchor']));watch=chosen['original_target'];recipe_path=B/'static-scene-search-v1'/f'{scene}.json';recipe=next(r for r in json.loads(recipe_path.read_text())['variants'] if r['variant']=='fine05_climb03');assert digest(recipe['mesh_path'])==recipe['mesh_sha256']
try:
 while True:
  raw=subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True);active=set(subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid','--format=csv,noheader'],text=True).splitlines());idle=[]
  for line in raw.splitlines():
   i,u,m,v=[x.strip() for x in line.split(',')]
   if int(i) in [5,6] and int(m)<1024 and int(v)<10 and u not in active:idle.append(int(i))
  usage=psutil.cpu_percent(interval=1,percpu=True);cpus=[i for i in sorted(os.sched_getaffinity(0))[:64] if i not in [1,5,7,9,10,11,15,16] and usage[i]<20]
  if idle and len(cpus)>=2:gpu=min(idle);cpus=sorted(cpus,key=lambda i:usage[i])[:2];break
  atomic_json(O/'state.json',{'status':'WAITING_FOR_IDLE_RESOURCES'});time.sleep(30)
 os.environ['CUDA_VISIBLE_DEVICES']=str(gpu);os.sched_setaffinity(0,cpus)
 import habitat_sim,habitat_sim._ext.habitat_sim_bindings as binding
 binding_receipt=json.loads((B/'native-stage-trace-xc-v1/state.json').read_text());assert digest(binding.__file__)==binding_receipt['binding_sha256'];os.environ['CASE1_NAV_TRACE_PREFIX']=str(O/'native');os.environ['CASE1_NAV_TRACE_WATCH']=' '.join(map(str,watch));gp=R/f'data/scene_datasets/mp3d/{scene}/{scene}.glb';cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id=str(gp);cfg.create_renderer=True;cfg.enable_physics=False;cfg.gpu_device_id=0;agent=habitat_sim.agent.AgentConfiguration();agent.height=1.5;agent.radius=.1;sensor=habitat_sim.SensorSpec();sensor.uuid='build';sensor.sensor_type=habitat_sim.SensorType.COLOR;sensor.resolution=[16,16];agent.sensor_specifications=[sensor];sim=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[agent]));ns=habitat_sim.NavMeshSettings();ns.set_defaults()
 for k,v in recipe['settings'].items():setattr(ns,k,v)
 atomic_json(O/'state.json',{'status':'REPRODUCING_FINE_CONTROL_WITH_STAGE_OBSERVATION','gpu':gpu,'cpus':cpus,'watch':watch})
 try:assert sim.recompute_navmesh(sim.pathfinder,ns);assert sim.pathfinder.save_nav_mesh(str(O/'control.navmesh'))
 finally:sim.close()
 matches=digest(O/'control.navmesh')==recipe['mesh_sha256'];atomic_json(O/'validation.json',{'status':'BYTE_IDENTICAL_FINE_CONTROL_STAGE_TRACE' if matches else 'CONTROL_MISMATCH_NOT_INTERPRETABLE','scene':scene,'node':node,'watch_position':watch,'official_anchor':chosen['anchor'],'existing_position_source_body_contact':chosen['original_body_contact'],'control_mesh_sha256':digest(O/'control.navmesh'),'expected_mesh_sha256':recipe['mesh_sha256'],'recipe_receipt_sha256':digest(recipe_path),'proposal_receipt_sha256':digest(proposal),'native_geometry_sha256':digest(O/'native-1.bin'),'scene_sha256':digest(gp),'binding_sha256':digest(binding.__file__),'build_settings':{k:getattr(ns,k) for k in dir(ns) if not k.startswith('_') and isinstance(getattr(ns,k),(bool,int,float,str))},'script_sha256':digest(__file__),'limits':'Observation-only trace of the already rejected fine variant. No parameter changes, mesh adoption, scene edits, new successful task or relaxed physical limit.'});assert matches;atomic_json(O/'state.json',{'status':'COMPLETE_BYTE_CONTROL_STAGE_OBSERVATION'})
except Exception as e:atomic_json(O/'state.json',{'status':'FAILED','error':repr(e)});raise
