"""Fixed-parameter official Recast626 controls in five known-provenance scenes."""
import os,sys,json,time,subprocess,datetime,fcntl
from pathlib import Path
R=Path('/data/zy/vln/case1');os.chdir(R);sys.path.insert(0,str(R/'scripts'))
from workspace import atomic_json,digest
B=R/'outputs/landmark-connectivity';O=B/'recast626-native-current-batch-v1';O.mkdir(exist_ok=False);lock=(O/'controller.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);scenes=['V2XKFyX4ASd','e9zR4mvMWw7','qoiz87JEwZ2','D7N2EKCX4Sj','HxpKQynjfin'];worker=R/'tests/landmark_diagnostics/build_recast626_native_known.py';parent=B/'full-native-v11/manifest.json';m=json.loads(parent.read_text());p=Path(m['profile_path']);profile=json.loads(p.read_text());manifest={'scenes':scenes,'worker_sha256':digest(worker),'parent_manifest_sha256':digest(parent),'profile_sha256':digest(p),'binding_receipt_sha256':digest(B/'recast626-isolated-binding-v1/validation.json'),'assets':{s:profile['assets'][f'mp3d/{s}/{s}.glb'] for s in scenes},'variable':'Only official626 filter boundary object; all current per-scene NavMeshSettings fixed','scope':'Static screen only, never adopts profile or starts model/navigation','excluded':'Known completed controls gTV/Xc and unknown original build settings'};atomic_json(O/'manifest.json',manifest);atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]});rows=[]
def note(status,**kw):atomic_json(O/'state.json',{'status':status,'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'completed':len(rows),'expected':len(scenes),**kw})
def idle():
 x=subprocess.check_output(['nvidia-smi','--id=4','--query-gpu=uuid,memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True).strip().split(',');a=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid','--format=csv,noheader'],text=True);return int(x[1])<1024 and int(x[2])<10 and x[0].strip() not in a
try:
 for sc in scenes:
  while not idle():note('WAITING_FOR_IDLE_GPU4',scene=sc);time.sleep(120)
  assert digest(worker)==manifest['worker_sha256'] and digest(parent)==manifest['parent_manifest_sha256'] and digest(p)==manifest['profile_sha256'];note('NATIVE_CONTROL_AND_PATCH_BUILD',scene=sc)
  with (O/(sc+'.log')).open('xb') as f:
   q=subprocess.Popen(['bash','scripts/with_runtime.sh','runtime/awarevln/bin/python',str(worker),'--scene',sc],stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT)
   st=Path('/proc')/str(q.pid)/'stat';atomic_json(O/(sc+'-worker.json'),{'pid':q.pid,'start_ticks':st.read_text().rsplit(')',1)[1].split()[19]});rc=q.wait()
  path=O/sc/'validation.json'
  if rc or not path.exists():
   row={'scene':sc,'status':'FAILED_RETAINED','exit_code':rc,'state':json.loads((O/sc/'state.json').read_text()) if (O/sc/'state.json').exists() else None};rows.append(row);note('FAILED',failure=row);raise RuntimeError('Scene control/build failed; see retained evidence')
  d=json.loads(path.read_text());assert d['native_byte_control_match'];rows.append({'scene':sc,'status':d['status'],'counts':d['counts'],'path':str(path),'sha256':digest(path)});atomic_json(O/'results-index.json',rows)
 atomic_json(O/'validation.json',{'status':'COMPLETE_STATIC_SCREEN_NOT_ACCEPTED','manifest_sha256':digest(O/'manifest.json'),'scenes':rows,'limits':'No geometry/whole-route/full-motion acceptance; any recovery requires exact source-bound joint selection and no regressions, actual execution/source guard and independent replay.'});note('COMPLETE_STATIC_SCREEN_NOT_ACCEPTED')
except Exception as e:note('FAILED',error=repr(e));raise
