"""Finite scene batch, respecting existing source constraints; no mesh or task adoption."""
import os,sys,json,subprocess,time,collections,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
R=Path.cwd();sys.path.insert(0,str(R/'scripts'));from workspace import atomic_json,digest
import psutil
B=R/'outputs/landmark-connectivity';O=B/'bounded-component-surface-batch-v2';O.mkdir(exist_ok=False);m=json.loads((B/'full-native-v11/manifest.json').read_text());held=set(json.loads((B/'constraint-blockers.json').read_text())['task_keys']);counts=collections.Counter(t['scene'] for t in m['tasks'] if t['status']=='STATIC_BLOCKED_PRESERVED' and t['task_key'] not in held)
# Xc already has a broader whole-scene graph overapproximation negative; VFua just audited.
scenes=[s for s,_ in counts.most_common() if s not in ['XcA2TqTSSAj','VFuaQ6m2Qom']];u=psutil.cpu_percent(interval=2,percpu=True);cpus=sorted([i for i in sorted(os.sched_getaffinity(0))[:64] if u[i]<25],key=lambda i:u[i])[:4];assert len(cpus)==4 and psutil.virtual_memory().available>12*1024**3;worker=R/'tests/landmark_diagnostics/probe_component_surface_scene_v2.py';helper=R/'tests/landmark_diagnostics/bounded_triangle_projection.py';sources={str(p):digest(p) for p in [worker,helper]};atomic_json(O/'manifest.json',{'status':'FROZEN_DIAGNOSTIC_NO_ADOPTION','scenes':scenes,'excluded_completed_diagnostics':['XcA2TqTSSAj','VFuaQ6m2Qom'],'blocked_counts':dict(counts),'cpus':cpus,'sources':sources,'parent_manifest_sha256':digest(B/'full-native-v11/manifest.json'),'source_bounds':{'sphere_m':.5,'new_horizontal_proposal_m':.35,'final_horizontal_check_m':.350001},'limits':'Original data/body/bounds unchanged. Prior/current/anchor snap seeds retained; new query is analytic triangle projection within the old ring domain. Camera-only mapping is not expanded; held114 untouched.'});atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]});pending=list(scenes);active={};done=[];failures=[]
while pending or active:
 for cpu in cpus:
  if cpu in active or not pending or failures:continue
  assert all(digest(p)==h for p,h in sources.items());scene=pending.pop(0);log=(O/(scene+'.log')).open('xb');p=subprocess.Popen([sys.executable,'-B',str(worker),'--scene',scene,'--cpu',str(cpu)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT);active[cpu]=(scene,p,log)
 for cpu,(scene,p,log) in list(active.items()):
  code=p.poll()
  if code is None:continue
  log.close();del active[cpu]
  if code:failures.append({'scene':scene,'exit_code':code})
  else:done.append(scene)
 atomic_json(O/'state.json',{'status':'FAILED_WAITING_OWN_ACTIVE' if failures else 'RUNNING','completed':len(done),'expected':len(scenes),'active':[{'scene':s,'pid':p.pid,'cpu':cpu} for cpu,(s,p,_) in active.items()],'failures':failures})
 if failures and not active:break
 if active:time.sleep(30)
if failures:raise RuntimeError(str(failures))
records=[];totals=collections.Counter()
for scene in done:
 p=O/scene/'validation.json';r=json.loads(p.read_text());totals.update(r['counts']);records.append({'scene':scene,'counts':r['counts'],'path':str(p),'sha256':digest(p)})
atomic_json(O/'validation.json',{'status':'COMPLETE_GEOMETRIC_CANDIDATE_BATCH_NOT_ACCEPTANCE','scenes':len(done),'counts':dict(totals),'scene_receipts':records,'manifest_sha256':digest(O/'manifest.json'),'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'limits':'No candidate is adopted. Any recovered static candidate still needs original source bounds, semantic/floor consistency, source-body checks, actual native motion and independent replay.'});atomic_json(O/'state.json',{'status':'COMPLETE','scenes':len(done),'counts':dict(totals)});print(dict(totals))
