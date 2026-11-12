from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import subprocess,sys,json,shutil,threading,time
from types import SimpleNamespace
from transport import CodexCLIBackend,Task,write_new
work=Path(sys.argv[1]);gates={r:threading.Semaphore(4) for r in ('generator','reviewer')}
backend=CodexCLIBackend(executable=shutil.which('codex.cmd'),model='gpt-6.1-sol',effort='high',cwd=Path.cwd())
def execute(row):
 d=work/'records'/row['safe_id'];d.mkdir(parents=True,exist_ok=True)
 if any(d.iterdir()):raise RuntimeError('Reconcile prior receipt before replay')
 command='cd /data/zy/vln && cd case1 && runtime/awarevln/bin/python -u '+work.as_posix()+'/remote_record.py '+work.as_posix()+' '+row['safe_id']
 with (d/'remote.err').open('w') as err:
  proc=subprocess.Popen(['ssh','codex-server',command],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err,text=True,encoding='utf8')
  for line in proc.stdout:
   obj=json.loads(line)
   if 'done' in obj:
    write_new(d/'done.json',obj);continue
   req=obj['request'];folder=d/req['client_request_id'];folder.mkdir();write_new(folder/'envelope.json',req)
   previous=work.with_name('r2r-v3-A-main-Remaining-20261109-r0')/'records'/row['safe_id']
   result=None
   for saved in previous.glob('*/envelope.json'):
    old_req=json.loads(saved.read_bytes())
    if old_req['messages']==req['messages'] and old_req['role']==req['role'] and old_req['output_schema']==req['output_schema']:
     events=saved.parent/'events.jsonl'
     ev=[json.loads(e) for e in events.read_text(encoding='utf8').splitlines()] if events.exists() else []
     if not any(e.get('type')=='turn.completed' for e in ev):
      raise RuntimeError('Prior call has no terminal receipt; reconcile before retry')
     thread=next(e['thread_id'] for e in ev if e.get('type')=='thread.started')
     result=SimpleNamespace(text=(saved.parent/'output.txt').read_text(encoding='utf8'),child_thread_id=thread)
     write_new(folder/'reused.json',{'source':str(saved.parent)})
     break
   if result is None:
    with gates[req['semantic_role']]:
     result=backend.complete(Task(req['role'],(chr(10)*2).join(m['content'] for m in req['messages']),req['output_schema']),folder)
   sessions=list((Path.home()/'.codex/sessions').glob('*/*/*/*'+result.child_thread_id+'*.jsonl'))
   contexts=[e['payload'] for f in sessions for e in map(json.loads,f.open(encoding='utf8')) if e['type']=='turn_context']
   assert contexts and all(c['model']=='gpt-6.1-sol' and c['effort']=='high' for c in contexts)
   reply=dict(output=json.loads(result.text),receipt=dict(request_id=result.child_thread_id,client_request_id=req['client_request_id'],request_sha256=req['request_sha256'],execution_kind='model',model='gpt-6.1-sol',effort='high'))
   write_new(folder/'receipt.json',reply['receipt']);proc.stdin.write(json.dumps(reply)+chr(10));proc.stdin.flush()
  assert proc.wait()==0
 return row['safe_id']
rows=list(map(json.loads,(work/'manifest.jsonl').read_bytes().splitlines()))
with ThreadPoolExecutor(max_workers=8) as pool:
 jobs={pool.submit(execute,row):row for row in rows}
 for f in as_completed(jobs):print(json.dumps([jobs[f]['safe_id'],str(f.exception()) if f.exception() else 'DONE']),flush=True)
