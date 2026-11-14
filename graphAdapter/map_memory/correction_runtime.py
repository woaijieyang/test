"""Identify inherited correction runtime without pretending the broker has host Landlock."""
import json,os,subprocess,sys
from pathlib import Path

def require_correction_runtime():
    private=os.environ.get('GRAPH_MEMORY_PRIVATE_RUNTIME')
    if private:
        record=json.loads(private)
        namespace=os.readlink('/proc/self/ns/mnt')
        if record.get('kind')!='memory_worker_bwrap' or record.get('mount_namespace')!=namespace:
            raise RuntimeError('Correction private namespace changed')
        if record.get('owner_pid') not in (os.getpid(),os.getppid()):
            raise RuntimeError('Correction process is not owned by its private worker')
        return dict(kind=record['kind'],mount_namespace=namespace,owner_pid=record['owner_pid'],pid=os.getpid())
    record=json.loads(os.environ.get('CASE1_PROTECTION','{}'))
    if record.get('landlock_abi',0)<3 or record.get('readonly_mount') is not True:
        raise RuntimeError('Verified protected runtime required for correction')
    return dict(kind='host_protected_runtime',landlock_abi=record['landlock_abi'],pid=os.getpid())

def probe_child_runtime():
    expected=require_correction_runtime()
    child=subprocess.run([sys.executable,'-I','-B',str(Path(__file__).resolve())],capture_output=True,text=True,timeout=15)
    if child.returncode:raise RuntimeError('Correction runtime child failed: '+child.stderr[-2000:])
    result=json.loads(child.stdout)
    if result['kind']!=expected['kind']:raise RuntimeError('Correction child runtime differs')
    if expected['kind']=='memory_worker_bwrap' and result['mount_namespace']!=expected['mount_namespace']:
        raise RuntimeError('Correction child escaped private mounts')
    return result

if __name__=='__main__':print(json.dumps(require_correction_runtime()))
