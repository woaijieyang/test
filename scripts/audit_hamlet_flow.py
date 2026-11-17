"""Join observed HAMLET memory consumption to baseline calls and executed actions."""
import argparse,json,hashlib,struct
from pathlib import Path
from workspace import ROOT,owned,read_json,digest,atomic_json
from result_contract import rows
from audit_model_trace import parse
p=argparse.ArgumentParser();p.add_argument('--run',required=True);a=p.parse_args();run=owned(a.run).resolve();manifest=read_json(run/'run_manifest.json')
if manifest.get('method')!='hamlet' or not manifest.get('policy_identity'):raise ValueError('Frozen HAMLET method required')
results=rows(run/'results.jsonl');baseline={};counts={'episodes':len(results),'calls':0,'selected_memory_calls':0,'nonzero_prompt_delta_calls':0,'consumed_memory_calls':0,'fallback_calls':0,'primitive_actions':0};files=[]
for row in results:
    events=rows(run/row['trace_path']);episode=str(row['task_key'].split('|')[-2])
    for e in events:
        if e['kind']=='model_call':
            key=(episode,int(e['call_id']))
            if key in baseline:raise ValueError('Ambiguous episode/call binding')
            baseline[key]=e
        elif e['kind']=='primitive_action':counts['primitive_actions']+=1
seen=set();ended=set()
for path in sorted(run.glob('shards/shard-*/attempt-*/hamlet-dataflow.jsonl')):
    files.append({'path':str(path.relative_to(run)),'sha256':digest(path)});active=None;stored={};pending=None;call_count=0
    for e in rows(path):
        kind=e['kind']
        if kind=='initialized':continue
        episode=str(e['episode_id'])
        if kind=='reset':
            if active is not None or e['archive_items'] or e['policy_calls'] or e['turns'] or e['fallback_remaining']:raise ValueError('Unclean episode boundary')
            active=episode;stored={};call_count=0;continue
        if episode!=active:raise ValueError('Cross-episode memory event')
        if kind=='memory_input':
            if pending is not None or e['policy_call_id']!=call_count or e['call_id']!=call_count+1:raise ValueError('Nonsequential memory call')
            for item in e['archive_items']:
                if item['policy_call_id']>=call_count or stored.get(item['item_id'])!=item['moment']:raise ValueError('Memory is future or differs from prior stored tensor')
            pending=e;counts['fallback_calls']+=int(e['fallback_active'])
        elif kind=='memory_generation':
            key=(episode,int(e['call_id']))
            if pending is None or key in seen or key not in baseline or pending['call_id']!=e['call_id']:raise ValueError('Unbound generated output')
            if e['adapted_prompt']!=e['generation_prefill']:raise ValueError('Selected memory did not reach actual generation prefill')
            original=baseline[key]
            input_flat=[v for row in original['input_ids'] for v in row]
            input_sha=hashlib.sha256(struct.pack('<'+'q'*len(input_flat),*input_flat)).hexdigest()
            if pending['input_ids']['sha256']!=input_sha or pending['images']['sha256']!=original['processed_image_sha256'] or pending['images']['shape']!=original['processed_image_shape']:raise ValueError('HAMLET actual input differs from baseline recorder input')
            ids=original['output_ids'];flat=[v for row in ids for v in row]
            expected=hashlib.sha256(struct.pack('<'+'q'*len(flat),*flat)).hexdigest()
            if e['output_tokens']['dtype']!='torch.int64' or e['output_tokens']['sha256']!=expected:raise ValueError('HAMLET and baseline generated tokens differ')
            selected=e['selected_item_ids'];coarse={i for i in e['coarse_candidate_item_ids'] if i is not None};archive=[i['item_id'] for i in pending['archive_items']]
            if e['archive_item_ids']!=archive or not set(selected)<=coarse or not coarse<=set(archive):raise ValueError('Router selection alignment failed')
            if pending['fallback_active'] and (selected or e['prompt_max_abs_delta']!=0):raise ValueError('Fallback did not disable read injection')
            item='archive_'+str(call_count).zfill(6)
            if e['archive_before_write']!=archive or e['archive_after_write']!=(archive+[item])[-256:]:raise ValueError('Memory write chronology/capacity changed')
            stored[item]=e['stored_moment'];counts['calls']+=1;counts['selected_memory_calls']+=bool(selected);counts['nonzero_prompt_delta_calls']+=e['prompt_max_abs_delta']>0;counts['consumed_memory_calls']+=bool(selected) and e['prompt_max_abs_delta']>0
            seen.add(key);call_count+=1;pending=None
        elif kind=='action_decision':
            if (episode,e['call_id']) not in seen:raise ValueError('Action decision without completed model call')
            parsed,is_reasoning,_=parse(baseline[(episode,e['call_id'])]['normalized_output'])
            if is_reasoning or not parsed or e['action']!=parsed[0]:raise ValueError('Memory fallback feedback differs from executed baseline parser')
        elif kind=='terminal_reset':
            if pending is not None or e['calls']!=call_count or e['archive_after_clear']!=0:raise ValueError('Unclosed memory generation/reset')
            ended.add(episode);active=None
        else:raise ValueError('Unknown memory event '+kind)
    if active is not None or pending is not None:raise ValueError('Unclosed worker memory stream')
if seen!=set(baseline) or len(ended)!=len(results):raise ValueError('Missing memory/model episode coverage')
if counts['consumed_memory_calls']==0:raise ValueError('No actual nonzero selected-memory consumption observed')
receipt={'status':'PASS','method':'causal_memory_actual_prefill_action_join_v1','manifest_sha256':digest(run/'run_manifest.json'),'counts':counts,'files':files,'scope':'Actual memory-to-generation and baseline action feedback consistency; not a claim of performance improvement'}
atomic_json(run/'hamlet_dataflow_audit.json',receipt);print(json.dumps(receipt))
