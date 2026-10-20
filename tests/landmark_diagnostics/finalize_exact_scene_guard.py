"""Wait for the frozen full scene exact repair, then independently replay every result once."""
import os,sys,json,time,subprocess,fcntl,datetime,argparse,re
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.nice(15)
R=Path.cwd();sys.path.insert(0,str(R/'scripts'))
from workspace import atomic_json,digest
P=argparse.ArgumentParser();P.add_argument('--source-run',required=True);P.add_argument('--scene',required=True);P.add_argument('--expected',required=True,type=int);args=P.parse_args();assert re.fullmatch('[A-Za-z0-9-]+',args.source_run) and re.fullmatch('[A-Za-z0-9]{11}',args.scene) and args.expected>0;B=R/'outputs/landmark-connectivity';run=B/args.source_run;lock=(run/'independent-controller.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
source=json.loads((run/'process.json').read_text());auditor=R/'tests/landmark_diagnostics/audit_guarded_continuous_routes_v3.py';auditor_sha=digest(auditor)
atomic_json(run/'independent-controller-process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],'source':source,'auditor_sha256':auditor_sha})
def note(status,**kw):atomic_json(run/'independent-controller-state.json',{'status':status,'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),**kw})
try:
 note('WAITING_FOR_FULL_SCENE_REPAIR')
 while not (run/'validation.json').exists():
  p=Path('/proc',str(source['pid']),'stat');s=p.read_text().rsplit(')',1)[1].split() if p.exists() else []
  assert s and s[19]==str(source['start_ticks']) and s[0] not in ['Z','X'],'Targeted repair terminal without validation'
  time.sleep(60)
 v=json.loads((run/'guarded/validation.json').read_text());m=json.loads((run/'guarded/manifest.json').read_text());assert v['coverage_complete'] and v['expected']==m['expected']==args.expected and len(v['results'])==args.expected and digest(run/'guarded/manifest.json')==v['manifest_sha256'];assert digest(auditor)==auditor_sha
 note('RUNNING_INDEPENDENT_EXACT_AUDIT')
 with (run/'independent-audit.log').open('xb') as log:
  proc=subprocess.Popen([sys.executable,'-B',str(auditor),'--source-run',run.name,'--scene',args.scene,'--output-run',args.source_run+'-independent'],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
  atomic_json(run/'independent-worker-process.json',{'pid':proc.pid,'start_ticks':Path('/proc',str(proc.pid),'stat').read_text().rsplit(')',1)[1].split()[19]});code=proc.wait()
 assert code==0
 report=B/(args.source_run+'-independent')/'validation.json';v=json.loads(report.read_text());assert v['scope_tasks']==args.expected and v['scene_tasks']==args.expected and v['full_scene_coverage'];note('COMPLETE_FULL_SCENE_INDEPENDENT_AUDIT',counts=v['counts'],report_sha256=digest(report))
except Exception as e:note('FAILED',error=repr(e));raise
