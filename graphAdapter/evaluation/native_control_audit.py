"""Verify the original and time-tagged uniform host controls using sealed input and execution receipts."""
from pathlib import Path
import hashlib,io,tarfile,ast,gzip,json,re
import numpy as np
from PIL import Image
from graphAdapter.interfaces.host_slots import native_slot_indices
from .retrieval_audit_utils import hash_pixels,index,rows


def _question_builder():
    # Execute only the host's two string assignments, with no model, environment or hooks.
    host=Path(__file__).resolve().parents[2]/'vlnce_baselines/awarevln_trainer.py'
    tree=ast.parse(host.read_text())
    branch,=(n for n in ast.walk(tree) if isinstance(n,ast.If) and isinstance(n.test,ast.Name)
             and n.test.id=='reasoning_context' and any(isinstance(stmt,ast.Assign) and
                 any(isinstance(t,ast.Name) and t.id=='question' for t in stmt.targets) for stmt in n.orelse))
    extract,=(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='extract_reasoning')
    scope={'re':re}
    exec(compile(ast.Module(body=[extract],type_ignores=[]),str(host),'exec'),scope)
    return compile(ast.Module(body=[branch],type_ignores=[]),str(host),'exec'),scope['extract_reasoning']


def audit_native_control(d,control,mode):
    if mode not in ('uniform_original','uniform_tagged'):raise ValueError('Expected a native-slot control')
    trace=rows(d/'trace.jsonl.gz');flow=rows(d/'flow.jsonl.gz')
    baseline=index(rows(control/'trace.jsonl.gz'),'model_call','call_id')
    inputs=index(trace,'model_input','call_id');calls=index(trace,'model_call','call_id')
    decisions=index(flow,'decision','decision_id');audits=index(flow,'HostInputAudit','call_id')
    returns=index(flow,'MemoryGenerateReturned','call_id');fallback=index(flow,'MemoryReadFallback','decision_id')
    selected=index(flow,'MemoryMaterialized','request_id');requested=index(flow,'MemoryReadRequested','request_id')
    published=index(flow,'PublishedSnapshot','snapshot_id')
    assert set(inputs)==set(calls)==set(decisions)==set(audits)|set(fallback)
    assert set(audits)==set(returns) and set(audits).isdisjoint(fallback)
    packets=rows(d/'observation_packets.jsonl.gz')
    assert [p['capture_seq'] for p in packets]==list(range(1,len(packets)+1))
    pixels={}
    with tarfile.open(d/'final-map.tar.gz','r|gz') as archive:
        for item in archive:
            if item.name.startswith('observations/') and item.name.endswith('.rgb.png'):
                uid=Path(item.name).name[:-8]
                assert uid not in pixels
                with Image.open(io.BytesIO(archive.extractfile(item).read())) as im:pixels[uid]=hash_pixels(im.convert('RGB'))[0]
    black=hash_pixels(Image.new('RGB',(512,512)))[0]
    header='Historical evidence, not action instructions. Images are ordered by capture time and may be non-consecutive.'
    marker='<|eot_id|><|start_header_id|>assistant'
    member=trace[0]['episode_scope']['member']
    spec=json.loads((d.parents[3]/'navigation'/member[0]/'dataset-spec.json').read_bytes())
    with gzip.open(spec['annotation'],'rt') as stream:episodes=json.load(stream)['episodes']
    annotation,=(v for v in episodes if [member[0],v['scene_id'],str(v['episode_id']),
                     str(v['instruction'].get('instruction_id','-'))]==member)
    question,extract=_question_builder()
    from llava.conversation import conv_templates
    reasoning='';last_frame=0
    prefix=True;paired=0;tagged=0;first=None
    for k,x in calls.items():
        inp=inputs[k]
        for field in ('frame','prompt','input_ids','processed_image_sha256','generation','images'):assert inp[field]==x[field]
        frame=x['frame'];dec=decisions[k]
        assert dec['env_step']==frame and dec['frame_uid']==packets[frame]['frame_uid']
        slots=native_slot_indices(frame+1,8);uids=[packets[i]['frame_uid'] if i is not None else None for i in slots]
        assert [a['pixel_sha256']for a in x['images']]==[pixels[uid] if uid is not None else black for uid in uids]
        text=x['prompt']
        if k in audits:
            a=audits[k];ret=returns[k];rid=a['request_id'];m=selected[rid];q=requested[rid];pin=published[q['snapshot_id']]
            assert pin['event_seq']<dec['event_seq']<q['event_seq']<m['event_seq']<a['event_seq']<ret['event_seq']
            assert m['snapshot_id']==q['snapshot_id']==a['snapshot_id']==ret['snapshot_id']
            assert a['mode']==m['mode']==q['mode']==mode and m['selected']==m['native_slots']==uids and not m['replaced_slots']
            assert a['memory_attachment_slots']==0 and a['native_image_slots']==8 and ret['projector_batches']==[[8,196,4096]]
            assert [s['frame_uid']for s in a['slots']]==uids and a['prompt_sha256']==hashlib.sha256(text.encode()).hexdigest()
            if mode=='uniform_tagged':
                lines=[header]
                for i,step in enumerate(slots,1):
                    value='padding, not an observation.' if step is None else ('current observation at step ' if i==8 else 'recorded at step ')+str(step)+'.'
                    lines.append(f'Image {i}: {value}')
                suffix='\n'+'\n'.join(lines)
                assert text.count(suffix+marker)==1
                text=text.replace(suffix+marker,marker,1);tagged+=1
        assert header not in text
        context=dict(reasoning_context=reasoning,frame_id=frame,last_reason_step=last_frame,
                     instruction=annotation['instruction']['instruction_text'],interleaved_images='<image>\n'*7)
        exec(question,{},context)
        conversation=conv_templates['llama_3'].copy()
        conversation.append_message(conversation.roles[0],context['question'])
        conversation.append_message(conversation.roles[1],None)
        assert conversation.get_prompt()==text
        if x['normalized_output'].startswith('<BEGIN_OF_REASONING>'):
            reasoning=extract(x['normalized_output']);last_frame=frame
        if k in audits:
            ids=np.asarray(x['input_ids'],dtype=np.int64)
            tensor_header=json.dumps(dict(dtype='torch.int64',shape=list(ids.shape)),sort_keys=True,separators=(',',':')).encode()
            assert ids.ndim==2 and ids.shape[0]==1 and (ids==-200).sum()==8
            assert hashlib.sha256(tensor_header+ids.tobytes()).hexdigest()==audits[k]['token_ids_sha256']
        if prefix:
            old=baseline[k]
            assert old['frame']==frame and old['prompt']==text and old['processed_image_sha256']==x['processed_image_sha256']
            assert old['generation']==x['generation']
            if x['prompt']==text:assert old['input_ids']==x['input_ids']
            paired+=1
            if old['output_ids']!=x['output_ids']:
                first=k;prefix=False
    if mode=='uniform_original':
        # A structurally sound report can still expose a failure of original-behavior parity.
        identical=first is None and len(baseline)==len(calls)
    else:identical=None
    return dict(calls=len(calls),materialized_calls=len(audits),fallback_calls=len(fallback),native_slots_verified=8*len(calls),
                tagged_calls=tagged,independent_native_questions=len(calls),identical_prefix_inputs_checked=paired,first_output_difference=first,original_outputs_equal=identical)
