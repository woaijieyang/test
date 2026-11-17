"""Trace one missing node through the native build, with byte-exact navmesh control."""
import os,sys,json,math,subprocess,struct,csv,collections
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='4';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['PYTHONDONTWRITEBYTECODE']='1';os.nice(15)
R=Path.cwd();O=R/'outputs/landmark-connectivity/native-stage-trace-xc-v2';C=R/'.cache/native-stage-trace-xc-v2';sys.path[:0]=[str(C),str(R/'scripts'),str(R/'.cache/geometry-tools')]
from workspace import atomic_json,digest
state=json.loads((O/'state.json').read_text());assert state['status']=='BINDING_READY_NOT_SCENE_VALIDATED'
def note(status,**kw):atomic_json(O/'scene-state.json',{'status':status,**kw})
try:
 import psutil
 usage=psutil.cpu_percent(interval=1,percpu=True);os.sched_setaffinity(0,sorted(sorted(os.sched_getaffinity(0))[:64],key=lambda i:usage[i])[:2])
 x=subprocess.check_output(['nvidia-smi','--id=4','--query-gpu=uuid,memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True).strip().split(',');active=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid','--format=csv,noheader'],text=True);assert int(x[1])<1024 and int(x[2])<10 and x[0].strip() not in active,'GPU4 not idle'
 import habitat_sim,habitat_sim._ext.habitat_sim_bindings as binding,numpy as np
 assert Path(binding.__file__).resolve()==Path(state['binding']) and digest(binding.__file__)==state['binding_sha256']
 B=R/'outputs/landmark-connectivity';m=json.loads((B/'full-native-v11/manifest.json').read_text());p=json.loads(Path(m['profile_path']).read_text());sc='XcA2TqTSSAj';node='ec0421cc61c64f6f8692d327d6838fd5';asset=p['assets'][f'mp3d/{sc}/{sc}.glb'];source=json.loads((B/'remaining-body-clearance.json').read_text());r=next(r for r in source['records'] if r['scene']==sc and r['node']==node);watch=r['closest_free_candidates'][0];gp=R/f'data/scene_datasets/mp3d/{sc}/{sc}.glb';assert digest(gp)==r['scene_sha256']==asset['scene_sha256']
 os.environ['CASE1_NAV_TRACE_PREFIX']=str(O/'native');os.environ['CASE1_NAV_TRACE_WATCH']=' '.join(map(str,watch));note('NATIVE_BUILD',watch=watch)
 cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id=str(gp);cfg.create_renderer=True;cfg.enable_physics=False;cfg.gpu_device_id=0;agent=habitat_sim.agent.AgentConfiguration();agent.height=1.5;agent.radius=.1;sensor=habitat_sim.SensorSpec();sensor.uuid='build';sensor.sensor_type=habitat_sim.SensorType.COLOR;sensor.resolution=[16,16];agent.sensor_specifications=[sensor];sim=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[agent]));ns=habitat_sim.NavMeshSettings();ns.set_defaults()
 for k,v in asset['build_settings'].items():setattr(ns,k,v)
 try:
  assert sim.recompute_navmesh(sim.pathfinder,ns);dest=O/'instrumented.navmesh';assert sim.pathfinder.save_nav_mesh(str(dest))
 finally:sim.close()
 assert digest(dest)==asset['navmesh_sha256'],'Instrumented native build differs from frozen native reference'
 bins=list(O.glob('native-*.bin'));assert len(bins)==1;raw=bins[0].read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);assert len(raw)==8+nv*12+nt*12;verts=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);indices=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);assert indices.min()>=0 and indices.max()<nv;tri=verts[indices].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1)
 helper=R/'tests/landmark_diagnostics/audit_remaining_body_clearance.py';s=helper.read_text();exec(s[s.index('def clip('):s.index('records=[]')]);q=np.array(watch);ids=np.flatnonzero((lo[:,0]<q[0]+.1)&(hi[:,0]>q[0]-.1)&(lo[:,2]<q[2]+.1)&(hi[:,2]>q[2]-.1)&(lo[:,1]<q[1]+1.5)&(hi[:,1]>q[1]+1e-5));contacts=[]
 for i in ids:
  poly=clip(list(tri[i]),q[1]+1e-5,True)
  if len(poly)<3:continue
  poly=clip(poly,q[1]+1.5,False)
  if len(poly)>=3 and distance(poly,q)<.1-1e-6:contacts.append({'triangle':int(i),'vertices':tri[i].tolist(),'max_height':float(max(v[1] for v in poly)-q[1])})
 config=list(map(float,next(O.glob('native-*-config.txt')).read_text().split()));cs,ch,H,climb,radius,region,bx,by,bz=config;cx=math.floor((q[0]-bx)/cs);cz=math.floor((q[2]-bz)/cs);stage_rows=[]
 for kind in ['raw','compact']:
  f=next(O.glob('native-*-'+kind+'.csv'));rows=list(csv.reader(f.open()))
  for stage in dict.fromkeys(row[0] for row in rows):
   subset=[row for row in rows if row[0]==stage and abs(float(row[4 if kind=='raw' else 3])-q[1])<.2]
   center=[row for row in subset if int(row[1])==cx and int(row[2])==cz]
   stage_rows.append({'kind':kind,'stage':stage,'local_spans_near_foot':len(subset),'walkable_near_foot':sum(int(row[5])!=0 for row in subset),'center_cell':center})
 result={'status':'NATIVE_STAGE_DIAGNOSIS_ONLY','scene':sc,'node':node,'watch_source_body_clear_sample':watch,'source_camera':r['camera_position'],'reference_mesh_sha256':asset['navmesh_sha256'],'instrumented_mesh_sha256':digest(dest),'native_byte_control_match':True,'scene_sha256':digest(gp),'binding_sha256':digest(binding.__file__),'native_triangle_dump_sha256':digest(bins[0]),'vertices':nv,'triangles':nt,'native_geometry_body_contacts':contacts,'native_build_config':config,'watch_cell':[cx,cz],'stages':stage_rows,'script_sha256':digest(__file__),'limits':'Records where this source-supported sample is removed; does not establish route feasibility. Logging instrumentation must produce identical mesh; no setting/data/install changes.'}
 atomic_json(O/'validation.json',result);note('COMPLETE_NATIVE_STAGE_DIAGNOSIS',contacts=len(contacts));print(json.dumps({'contacts':len(contacts),'stages':stage_rows}))
except Exception as e:note('FAILED',error=repr(e));raise
