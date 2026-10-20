"""One finalizer for full-source diagnostics; waits for exact controller identity, no restarts."""
import os,sys,json,time,fcntl,subprocess,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.nice(15)
R=Path.cwd();sys.path.insert(0,str(R/'scripts'));from workspace import atomic_json,digest
O=R/'outputs/landmark-connectivity/full-source-geometry-v1';lease=(O/'coverage-controller.lock').open('a');fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB);source=json.loads((O/'process.json').read_text());worker=R/'tests/landmark_diagnostics/validate_full_source_screen_coverage.py';sha=digest(worker)
atomic_json(O/'coverage-controller-process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],'source':source,'validator_sha256':sha})
def note(status,**kw):atomic_json(O/'coverage-controller-state.json',{'status':status,'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),**kw})
try:
 note('WAITING_FOR_FULL_SOURCE_SCREEN')
 while not (O/'validation.json').exists():
  p=Path('/proc',str(source['pid']),'stat');z=p.read_text().rsplit(')',1)[1].split() if p.exists() else []
  if not z or z[19]!=str(source['start_ticks']) or z[0] in 'ZX':note('BLOCKED_INCOMPLETE_SOURCE');sys.exit(0)
  time.sleep(60)
 assert digest(worker)==sha;note('VALIDATING_ALL_IDENTITIES_AND_SAMPLE_COUNTS')
 with (O/'independent-coverage.log').open('xb') as log:p=subprocess.run([sys.executable,'-B',str(worker)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
 assert p.returncode==0,('coverage audit failed',p.returncode)
 r=json.loads((O/'independent-coverage.json').read_text());note(r['status'],tasks=r['tasks'],scenes=r['scenes'])
except Exception as e:note('FAILED',error=repr(e));raise
