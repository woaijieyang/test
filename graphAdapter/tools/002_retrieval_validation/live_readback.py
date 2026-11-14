from pathlib import Path
import json,hashlib,gzip,sys
from collections import Counter
from functools import lru_cache
import numpy as np
from PIL import Image
root=Path(sys.argv[1]).resolve()
domain=root/'live/r2r'
def read(path):
    op=gzip.open if path.suffix=='.gz' else open
    with op(path,'rb')as f:
        return [json.loads(line) for line in f if line.endswith(b'\n')]
def locate(live,sealed):
    matches=list((domain/'worker').rglob(live))
    return matches[0] if matches else next((root/'results').rglob(sealed))
flow=read(locate('flow_trace.jsonl','flow.jsonl.gz')); trace=read(locate('trace.jsonl','trace.jsonl.gz'))
def keyed(rows,kind,key):
    entries=[r for r in rows if r['kind']==kind]
    result={r[key]:r for r in entries}
    assert len(entries)==len(result),(kind,'duplicate')
    return result
inputs=keyed(trace,'model_input','call_id');outputs=keyed(trace,'model_call','call_id')
reads=keyed(flow,'MemoryReadRequested','request_id'); audits=keyed(flow,'HostInputAudit','call_id')
returns=keyed(flow,'MemoryGenerateReturned','call_id');materials=keyed(flow,'MemoryMaterialized','request_id')
def digest(data):return hashlib.sha256(data).hexdigest()
def hash_array(a,dtype):
    h=hashlib.sha256(json.dumps({'dtype':dtype,'shape':list(a.shape)},sort_keys=True,separators=(',',':')).encode())
    h.update(a.tobytes());return h.hexdigest()
@lru_cache(maxsize=1024)
def read_image(path):
    with Image.open(path)as image:
        a=np.asarray(image.convert('RGB'))
        return hash_array(a,a.dtype.str)
errors=[];pixcount=0;slots=0;different_uniform=0
for call,ret in returns.items():
    try:
        audit=audits[call]; inp=inputs[call]; out=outputs[call]
        req=reads[ret['request_id']]; mat=materials[ret['request_id']]
        assert len({e['frame_uid']for e in (ret,audit,req,mat)})==1
        assert len({e['snapshot_id']for e in (ret,audit,req,mat)})==1
        assert len({e['decision_id']for e in (ret,audit,req,mat)})==1
        assert req['event_seq']<mat['event_seq']<audit['event_seq']<ret['event_seq']
        assert digest(inp['prompt'].encode())==audit['prompt_sha256']
        assert hash_array(np.asarray(inp['input_ids'],np.int64),'torch.int64')==audit['token_ids_sha256']
        assert inp['processed_image_sha256']==out['processed_image_sha256']
        assert audit['logical_image_slots']==len(inp['images'])==ret['projector_shape'][0]
        assert audit['expanded_input_tokens']==audit['text_and_placeholder_tokens']+ret['projector_shape'][0]*(ret['projector_shape'][1]-1)
        assert audit['slots'][-1]['is_current'] and audit['slots'][-1]['frame_uid']==req['frame_uid']
        assert mat['selected']==[s['frame_uid']for s in audit['slots']]
        hist=[s['sensor_seq']for s in audit['slots'] if s['frame_uid'] and not s['is_current']]
        assert hist==sorted(hist) and all(s<=req['cutoff']['capture_seq']for s in hist)
        for s,im in zip(audit['slots'],inp['images']):
            slots+=1
            path=(domain/im['path']).resolve()
            assert path.is_relative_to(domain.resolve())
            if path.is_file():
                assert read_image(path)==s['host_pixel_hash'];pixcount+=1
        n=inp['frame']+1;B=len(inp['images'])
        if n>=B:
            native=list(np.linspace(0,n-1,B-1,endpoint=False,dtype=int)+1)+[n]
            actual=[s['sensor_seq']for s in audit['slots']]
            if native!=actual:different_uniform+=1
    except Exception as e:errors.append({'call':call,'error':repr(e)})
plan=json.loads((root/'retention_plan.json').read_text());member=plan['entries'][0]['member']
manifest=Path('outputs/graph_memory/candidate_detached_correction001-20261113/simulator-quality15-reuse-v3/control/REUSED_CONTROLS.json')
control=read(Path(next(v['result']for v in json.loads(manifest.read_text()).values()if v['member']==member))/'trace.jsonl.gz')
act=lambda data:[v for v in data if v['kind']=='primitive_action']
actions=act(trace);baseline=act(control);before=keyed(control,'model_input','call_id')
div=next(({'step':a['step'],'control_action':b['action'],'candidate_action':a['action'],'candidate_call':a['last_call_id'],'control_call':b['last_call_id']}for a,b in zip(actions,baseline)if a['action']!=b['action']),None)
def first(field):return next((k for k,v in inputs.items()if k in before and v[field]!=before[k][field]),None)
result={'run':str(root),'member':member,'scope':'completed model calls in observed prefix','returned_injections':len(returns),'fallback_reasons':dict(Counter(v['reason']for v in flow if v['kind']=='MemoryReadFallback')),'total_model_returns':len(outputs),'audited_slots':slots,'pixels_independently_checked_from_host_PNG':pixcount,'distinct_host_png':read_image.cache_info().currsize,'different_from_native_uniform_slots_calls':different_uniform,'first_prompt_difference':first('prompt'),'first_processed_image_difference':first('processed_image_sha256'),'first_action_difference':div,'actions':len(actions),'control_actions':len(baseline),'terminal_seen':any(v.get('done')for v in actions),'errors':errors}
print(json.dumps(result,indent=2))
out=root/'control'/('independent-material-readback-%06d.json'%len(returns))
if not out.exists():out.write_text(json.dumps(result,indent=2)+'\n')
if errors:raise SystemExit(1)
