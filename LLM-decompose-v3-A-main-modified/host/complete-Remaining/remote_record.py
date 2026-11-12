from pathlib import Path
import json,sys
pkg=Path('src/subtaskAdapter/LLM-decompose-v3-A-main-modified').resolve()
sys.path.insert(0,str(pkg))
sys.path.insert(0,str(pkg/'host'))
from full_workflow import run as run_record
from orchestrator.requests import RuntimeConfig
work=Path(sys.argv[1]);safe=sys.argv[2]
row=next(r for r in map(json.loads,(work/'manifest.jsonl').read_bytes().splitlines()) if r['safe_id']==safe)
d=work/'records'/safe;d.mkdir(parents=True,exist_ok=True)
assert not (d/'result.json').exists()
cfg=RuntimeConfig.from_dict({'generator':{'model':'gpt-6.1-sol','effort':'high'},'reviewer':{'model':'gpt-6.1-sol','effort':'high'},'max_technical_retries':1})
def call(req):
 print(json.dumps({'request':req},ensure_ascii=False),flush=True)
 return json.loads(sys.stdin.readline())
def journal(event):
 with (d/'events.jsonl').open('a') as f:f.write(json.dumps(event,ensure_ascii=False)+chr(10))
result=run_record(dict(task_key=row['record_id'],dataset=row['dataset'],language=row['language'],original_instruction=row['original_instruction']),call,cfg,journal=journal)
temp=d/'result.tmp';temp.write_text(json.dumps(result,ensure_ascii=False));temp.replace(d/'result.json')
print(json.dumps({'done':result['result']['state']}),flush=True)
