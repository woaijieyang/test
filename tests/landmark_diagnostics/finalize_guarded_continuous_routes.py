"""Wait for one complete sampled run and its first audit, then strengthen its geometry audit."""
import os,sys,json,time,subprocess,fcntl,argparse,re,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.nice(15)
P=argparse.ArgumentParser();P.add_argument('--source-run',required=True);P.add_argument('--scene',required=True);args=P.parse_args();assert re.fullmatch('[A-Za-z0-9-]+',args.source_run) and re.fullmatch('[A-Za-z0-9]{11}',args.scene)
R=Path.cwd();sys.path.insert(0,str(R/'scripts'));from workspace import atomic_json,digest
B=R/'outputs/landmark-connectivity';run=B/args.source_run;lock=(run/'continuous-finalizer.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);source=json.loads((run/'process.json').read_text());worker=R/'tests/landmark_diagnostics/audit_guarded_continuous_routes_v2.py';sha=digest(worker);atomic_json(run/'continuous-finalizer-process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],'source':source,'auditor_sha256':sha})
def note(status,**kw):atomic_json(run/'continuous-finalizer-state.json',{'status':status,'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),**kw})
try:
 note('WAITING_FOR_COMPLETE_RUN_AND_STANDARD_AUDIT')
 while not (run/'validation.json').exists():
  p=Path('/proc',str(source['pid']),'stat');s=p.read_text().rsplit(')',1)[1].split() if p.exists() else [];assert s and s[19]==str(source['start_ticks']) and s[0] not in 'ZX','Source run terminal without complete validation';time.sleep(60)
 while not (run/'independent/validation.json').exists():
  state=json.loads((run/'independent-controller-state.json').read_text());assert state['status'] not in ['FAILED','BLOCKED_INCOMPLETE_SOURCE_RUN','BLOCKED_SOURCE_INFRASTRUCTURE_FAILURE'],state;proc=json.loads((run/'independent-controller-process.json').read_text());p=Path('/proc',str(proc['pid']),'stat');s=p.read_text().rsplit(')',1)[1].split() if p.exists() else [];assert s and s[19]==str(proc['start_ticks']) and s[0] not in 'ZX','Standard auditor missing';time.sleep(60)
 standard=json.loads((run/'independent/validation.json').read_text());assert standard['coverage_complete'] and not standard['audit_issues'];assert digest(worker)==sha;note('RUNNING_CONTINUOUS_AUDIT')
 out=args.source_run+'-continuous-v2'
 with (run/'continuous-audit-v2.log').open('xb') as log:p=subprocess.run([sys.executable,'-B',str(worker),'--source-run',args.source_run,'--scene',args.scene,'--output-run',out],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
 assert p.returncode==0;result=json.loads((B/out/'validation.json').read_text());note(result['status'],counts=result['counts'])
except Exception as e:note('FAILED',error=repr(e));raise
