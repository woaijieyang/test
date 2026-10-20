"""One-shot dependency continuation; never restarts healthy or terminal runs."""
import datetime,json,os,subprocess,time
from pathlib import Path
R=Path.cwd();B=R/'outputs/connectivity';O=B/'endpoint115-v2-continuation-v1'
def save(status,**kw):
 p=O/'state.json';t=p.with_suffix('.tmp');t.write_text(json.dumps({'status':status,'time':datetime.datetime.now().astimezone().isoformat(),**kw},indent=2));t.replace(p)
expected=json.loads((B/'endpoint115-full-motion-v1/process.json').read_text());save('WAITING_FOR_EXISTING_V1_FULL3062_TERMINAL',parent_process=expected)
while not (B/'endpoint115-full-motion-v1/validation.json').exists():
 p=Path('/proc')/str(expected['pid'])/'stat'
 if not p.exists():save('FAILED_PARENT_NO_COMPLETE_RECEIPT');raise SystemExit(2)
 fields=p.read_text().rsplit(')',1)[1].split()
 if fields[0]=='Z' or fields[19]!=expected['start_ticks']:save('FAILED_PARENT_IDENTITY_OR_ZOMBIE');raise SystemExit(2)
 time.sleep(300)
v=json.loads((B/'endpoint115-full-motion-v1/validation.json').read_text());assert v['coverage_complete'] and v['expected']==3062
assert not (B/'endpoint115-full-motion-v2').exists()
with (O/'v2-controller.log').open('xb') as log:
 p=subprocess.Popen(['scripts/with_runtime.sh','runtime/awarevln/bin/python','-B','tests/landmark_diagnostics/run_endpoint115_full_validation_v2.py'],stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
 fields=Path(f'/proc/{p.pid}/stat').read_text().rsplit(')',1)[1].split();save('RUNNING_V2_FULL3062',child_pid=p.pid,child_start_ticks=fields[19]);code=p.wait()
save('COMPLETE_V2_RECEIPT_READY_NOT_FORMAL_ACCEPTANCE' if code==0 else 'FAILED_V2_PRESERVED',returncode=code)
