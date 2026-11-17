"""One exact guarded-run finalizer, no retry or navigation restart."""
import os,sys,json,time,subprocess,fcntl,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.nice(15)
R=Path.cwd();sys.path.insert(0,str(R/'scripts'));from workspace import atomic_json,digest
B=R/'outputs/landmark-connectivity';run=B/'17drp-continuous-source-guard-v3';lease=(run/'exact-independent-controller.lock').open('a');fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB);source=json.loads((run/'process.json').read_text());worker=R/'tests/landmark_diagnostics/audit_17drp_exact_guard_results.py';sha=digest(worker);atomic_json(run/'exact-independent-process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],'source_controller':source,'auditor_sha256':sha})
def note(status,**kw):atomic_json(run/'exact-independent-state.json',{'status':status,'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),**kw})
try:
 note('WAITING_FOR_FULL_261_GUARDED_RUN')
 while not (run/'validation.json').exists():
  p=Path('/proc',str(source['pid']),'stat');z=p.read_text().rsplit(')',1)[1].split() if p.exists() else [];assert z and z[19]==str(source['start_ticks']) and z[0] not in 'ZX','Source run incomplete';time.sleep(60)
 assert digest(worker)==sha;note('RUNNING_EXACT_CONTINUOUS_INDEPENDENT_AUDIT')
 with (run/'exact-independent.log').open('xb') as log:p=subprocess.run([sys.executable,'-B',str(worker),'--source-run',run.name,'--output-run','17drp-continuous-source-guard-v3-independent'],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
 assert p.returncode==0;result=json.loads((B/'17drp-continuous-source-guard-v3-independent/validation.json').read_text());note(result['status'],counts=result['counts'])
except Exception as e:note('FAILED',error=repr(e));raise
