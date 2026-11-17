"""Wait for the one frozen candidate generator, then audit once; never rerun it."""
import os,sys,time,json,subprocess,fcntl,datetime
from pathlib import Path
R=Path('/data/zy/vln/case1');os.chdir(R);sys.path.insert(0,str(R/'scripts'))
from workspace import atomic_json,digest
B=R/'outputs/landmark-connectivity';prefix='source-guard-key-mask-v1';lock=(B/(prefix+'-finalizer.lock')).open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);worker=json.loads((B/prefix/'process.json').read_text());auditor=R/'tests/landmark_diagnostics/audit_source_guard_key_mask.py';ah=digest(auditor);atomic_json(B/(prefix+'-finalizer-process.json'),{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],'auditor_sha256':ah})
def note(status,**kw):atomic_json(B/(prefix+'-finalizer-state.json'),{'status':status,'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),**kw})
try:
 note('WAITING_FOR_NATIVE_CONTROLLER')
 while True:
  p=Path('/proc')/str(worker['pid'])/'stat'
  if not p.exists():break
  x=p.read_text().rsplit(')',1)[1].split()
  if x[19]!=str(worker['start_ticks']) or x[0] in 'ZX':break
  time.sleep(30)
 assert (B/prefix/'validation.json').exists(),'Controller ended without validation receipt';assert digest(auditor)==ah;note('AUDITING_NATIVE_AND_SOURCE_GEOMETRY')
 with (B/(prefix+'-audit.log')).open('xb') as log:subprocess.run(['bash','scripts/with_runtime.sh','runtime/awarevln/bin/python',str(auditor)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,check=True)
 p=B/'source-guard-key-mask-independent-audit-v1/validation.json';d=json.loads(p.read_text());note(d['status'],newly_audited=len(d['rows']),receipt_sha256=digest(p))
except Exception as e:note('FAILED',error=repr(e));raise
