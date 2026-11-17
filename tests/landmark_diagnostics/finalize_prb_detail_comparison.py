import os,sys,json,time,fcntl,subprocess,datetime
from pathlib import Path
R=Path.cwd();sys.path.insert(0,str(R/'scripts'))
from workspace import atomic_json,digest
B=R/'outputs/landmark-connectivity';run=B/'full-source-guard-pRb-detail-exact-v1';lock=(run/'comparison-controller.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);source=json.loads((run/'independent-controller-process.json').read_text());worker=R/'tests/landmark_diagnostics/compare_prb_detail_full_scene.py';worker_sha=digest(worker);atomic_json(run/'comparison-controller-process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],'source':source,'comparator_sha256':worker_sha})
def note(status,**kw):atomic_json(run/'comparison-controller-state.json',{'status':status,'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),**kw})
try:
 note('WAITING_FOR_COMPLETE_INDEPENDENT_FULL_SCENE_AUDIT')
 target=B/'full-source-guard-pRb-detail-exact-v1-independent/validation.json'
 while not target.exists():
  p=Path('/proc',str(source['pid']),'stat');s=p.read_text().rsplit(')',1)[1].split() if p.exists() else [];assert s and s[19]==str(source['start_ticks']) and s[0] not in ['Z','X'],'Independent audit terminal without full validation';time.sleep(60)
 assert digest(worker)==worker_sha;note('COMPARING_FULL_IDENTITY_SETS')
 with (run/'comparison.log').open('xb') as f:code=subprocess.run([sys.executable,'-B',str(worker)],stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT).returncode
 assert code==0;result=B/'prb-detail-nonregression-v1.json';d=json.loads(result.read_text());note('COMPLETE_FULL_IDENTITY_COMPARISON',candidate_strict_passed=d['candidate_strict_passed'],all_baselines_preserved=d['all_baselines_preserved'],all_tasks_strict=d['all_tasks_strict'],report_sha256=digest(result))
except Exception as e:note('FAILED',error=repr(e));raise
