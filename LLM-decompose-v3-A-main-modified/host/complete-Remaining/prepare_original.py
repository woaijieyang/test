from pathlib import Path
import sys,json
pkg=Path('src/subtaskAdapter/LLM-decompose-v3-A-main-modified').resolve();sys.path.insert(0,str(pkg))
sys.path.insert(0,str(pkg/'host'))
from full_workflow import run as run_record
from orchestrator.requests import RuntimeConfig
sys.path.insert(0,str(pkg.parent/'LLM-decompose-v1-r2r-specialized/scripts'))
import prepare_a2 as native
native.P=Path(sys.argv[1]).resolve()
cfg=RuntimeConfig.from_dict(json.loads((pkg/'config/runtime.json').read_bytes()))
def language_record(row):
    return json.loads((native.P/'records'/row['safe_id']/'result.json').read_bytes())
def checked(row):
    saved=language_record(row)

    events=[e for profile in saved['profile_history'] for e in profile['events']]
    def replay(req):
        event=next(e for e in events if e['request']['role']==req['role'] and e['request']['messages']==req['messages'] and 'response' in e)
        import copy
        answer=copy.deepcopy(event['response'])
        answer['receipt']['client_request_id']=req['client_request_id']
        answer['receipt']['request_sha256']=req['request_sha256']
        return answer
    actual=run_record(dict(task_key=row['record_id'],dataset=row['dataset'],language=row['language'],original_instruction=row['original_instruction']),replay,cfg)
    assert actual['result']['instruction']==saved['result']['instruction']
    assert actual['result']['state']==saved['result']['state']
    result=saved['result']
    return result['instruction'],dict(result,candidate_sha256=result.get('candidate_sha256'))
native.checked=checked
if __name__ == '__main__':
    rows=list(map(json.loads,(native.P/'manifest.jsonl').read_bytes().splitlines()))
    native.prepare(rows[:1],1600)
