"""Persistent, fixed-operation correction executor. No model/pose inference."""
from pathlib import Path
import json,os,sys,time,traceback
root=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(root/'src'),str(root/'vendor_sources/EvoMemNav')]
from graphAdapter.map_memory.correction_runtime import require_correction_runtime
from graphAdapter.map_memory.correction_workspace import CorrectionJob,build_detached,catch_up_detached,DetachedWorkspaceSession
from graphAdapter.map_memory.storage.store import canonical,_write_immutable
require_correction_runtime()
session=DetachedWorkspaceSession()
import atexit
atexit.register(session.close)
for line in sys.stdin:
    if len(line)>1024*1024:raise ValueError('Oversized correction command')
    command=json.loads(line)
    if command.get('mode')=='shutdown':break
    started=time.monotonic();error=None
    try:
        if command['mode'] not in ('build','catchup','release'):raise ValueError('Unsupported correction operation')
        job=CorrectionJob(Path(command['job']).read_bytes())
        if job.digest!=command['job_sha256']:raise ValueError('Frozen command job changed')
        if command['mode']=='build':result=build_detached(job,command['workspace'],session=session)
        elif command['mode']=='catchup':result=catch_up_detached(job,command['workspace'],command['tail'],session=session)
        else:result=session.release(job,command['workspace'])
        sid=result['detached_snapshot']['snapshot_id']
    except BaseException as exc:
        session.close();traceback.print_exc();error=repr(exc);sid=None
    # Source readers are closed; the private workspace store may remain retained for the next phase.
    receipt=dict(phase_id=command['phase_id'],job_sha256=command['job_sha256'],mode=command['mode'],
        state='READY' if error is None else 'FAILED',snapshot_id=sid,error=error,
        pid=os.getpid(),elapsed_s=time.monotonic()-started,service_creations=session.creations,service_reuses=session.reuses)
    _write_immutable(Path(command['work']),'DAEMON_PHASE.json',canonical(receipt))
