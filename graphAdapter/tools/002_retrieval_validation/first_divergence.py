"""Prepare a paired same-state test at the first differing model output."""
from pathlib import Path
import gzip,json,tarfile,io,hashlib,sys
from PIL import Image
from graphAdapter.interfaces.host_slots import native_slot_indices

def rows(d,n):return [json.loads(l)for l in gzip.open(d/n,'rt')]
def run(out):
    g=Path('outputs/graph_memory');r=g/'graph002-dynamic-context-r2r-01';d=next(r.glob('results/*/shadow/attempt0'))
    controls=json.loads((g/'candidate_detached_correction001-20261113/simulator-quality15-reuse-v3/control/REUSED_CONTROLS.json').read_bytes())
    original=rows(Path(controls[d.parents[1].name]['result']),'trace.jsonl.gz');changed=rows(d,'trace.jsonl.gz');flow=rows(d,'flow.jsonl.gz')
    calls=lambda xs:{v['call_id']:v for v in xs if v['kind']=='model_call'}
    ca,cb=calls(original),calls(changed)
    k=next(k for k in cb if k in ca and ca[k]['output_ids']!=cb[k]['output_ids'])
    act=lambda xs:[x for x in xs if x['kind']=='primitive_action']
    x,y=ca[k],cb[k];assert x['frame']==y['frame'] and x['processed_image_sha256']==y['processed_image_sha256']
    for a,b in zip(act(original)[:x['frame']],act(changed)[:x['frame']]):
        assert a['action']==b['action'] and a['after_evaluator_only']['position']==b['after_evaluator_only']['position'] and a['after_evaluator_only']['rotation_xyzw']==b['after_evaluator_only']['rotation_xyzw']
    first=next((a['step'],a['action'],b['action'])for a,b in zip(act(original),act(changed))if a['action']!=b['action'])
    audit=next(v for v in flow if v['kind']=='HostInputAudit'and v['call_id']==k)
    card=next(v for v in flow if v['kind']=='DynamicContextCompiled'and v['request_id']==audit['request_id'])
    suffix=card['model_suffix'];assert y['prompt'].replace(suffix,'',1)==x['prompt']
    pk=rows(d,'observation_packets.jsonl.gz');frame=x['frame'];last=pk[frame]['action'];count=last['primitive_count']
    assert last['primitive_index']==count and all(p['action']['macro_id']==last['macro_id']for p in pk[frame-count+1:frame+1])
    assert all(p['action']['action_id']==1 and p['action']['collision']is False for p in pk[frame-count+1:frame+1])
    import numpy as np
    length=sum(np.linalg.norm(np.asarray(pk[n]['pose_record']['T_odom_base'])[:3,3]-np.asarray(pk[n-1]['pose_record']['T_odom_base'])[:3,3]) for n in range(frame-count+1,frame+1))
    n=frame+1;slots=native_slot_indices(n,len(x['images']));out.mkdir(parents=True,exist_ok=True);images=out/'images';images.mkdir(exist_ok=True)
    need={f"observations/{pk[j]['frame_uid']}.rgb.png":im['pixel_sha256'] for j,im in zip(slots,x['images'])}
    with tarfile.open(d/'final-map.tar.gz','r|gz')as arc:
        for member in arc:
            if member.name not in need:continue
            data=arc.extractfile(member).read();h=need.pop(member.name)
            with Image.open(io.BytesIO(data))as pic:
                rgb=pic.convert('RGB');assert hashlib.sha256(rgb.mode.encode()+str(rgb.size).encode()+rgb.tobytes()).hexdigest()==h
            (images/(h+'.png')).write_bytes(data)
            if not need:break
    assert not need
    def make(fields):
        return y['prompt'].replace(suffix,'\nGraph memory for this decision:\n'+json.dumps(fields,separators=(',',':')),1)
    path=card['model_fields']['recent_path']
    def remove(key):return make(dict(as_of_step=frame,recent_path={k:v for k,v in path.items()if k!=key}))
    completed=dict(as_of_step=frame,last_completed_action=dict(from_step=frame-count,to_step=frame,action='forward',executed_primitives=count,recorded_forward_m=round(float(length),2)))
    variants=[('recorded_exact',y['prompt']),('original_exact',x['prompt']),('without_prior_turn',remove('executed_turn_primitives')),
        ('without_forward_distance',remove('recorded_forward_m')),('latest_complete_macro',make(completed))]
    (out/'replay-input.json').write_text(json.dumps(dict(recorded=dict(y,images=[im['pixel_sha256']for im in y['images']]),variants=variants)))
    (out/'binding.json').write_text(json.dumps(dict(original_call=x['call_id'],original_output_ids=x['output_ids'],original_text=x['normalized_output'],original_prompt=x['prompt'],
        first_output_difference=k,current_step=frame,first_action_difference=first,source=card['source'],published_fields=card['model_fields'],current_macro=completed,
        current_macro_source_uids=[p['frame_uid']for p in pk[frame-count:frame+1]],selection='first differing output on otherwise identical state; current macro derived from already executed public primitives; historical cutoff not advanced'),indent=2))
    print(k,frame,first,path,completed)
if __name__=='__main__':run(Path(sys.argv[1]))

