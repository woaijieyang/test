"""Audit a complete diagnostic cohort without admitting it as a full result."""
import argparse,sys,json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from workspace import owned,read_json,digest,atomic_json
from result_contract import rows,aggregate,finite_metrics,METRICS
p=argparse.ArgumentParser();p.add_argument('--run',required=True);a=p.parse_args()
run=owned(a.run).resolve();manifest=read_json(run/'run_manifest.json')
if manifest['scope']!='diagnostic':raise ValueError('Diagnostic scope required')
records=rows(run/'results.jsonl');summary=aggregate(manifest,records)
if not summary['complete']:raise ValueError('Diagnostic incomplete or has runtime errors')
for item in manifest['frozen_files']:
    if digest(item['path'])!=item['sha256']:raise ValueError('Frozen file changed: '+item['path'])
semantic=read_json(run/'semantic_audit.json');independent=read_json(run/'independent_metrics.json')
identity=digest(run/'run_manifest.json')
if semantic.get('status')!='PASS' or semantic.get('errors') or semantic.get('manifest_sha256')!=identity:raise ValueError('Semantic audit mismatch')
if independent.get('method')!='trajectory_recompute_v1' or independent.get('manifest_sha256')!=identity:raise ValueError('Independent metric provenance mismatch')
expected={row['task_key']:row for row in independent['results']}
if len(expected)!=len(independent['results']) or set(expected)!={row['task_key'] for row in records}:raise ValueError('Metric coverage mismatch')
traces={row['task_key']:(row['trace_path'],row['trace_sha256']) for row in records}
if {row['task_key']:(row['path'],row['sha256']) for row in semantic['trace_files']}!=traces:raise ValueError('Semantic trace binding mismatch')
counts={'model_inputs':0,'model_calls':0,'primitive_actions':0,'episodes':len(records)}
for row in records:
    other=expected[row['task_key']];finite_metrics(row);finite_metrics(other)
    if other['trace_sha256']!=row['trace_sha256']:raise ValueError('Recompute trace mismatch')
    for metric in METRICS:
        if not math.isclose(row['metrics'][metric],other['metrics'][metric],rel_tol=1e-6,abs_tol=1e-5):raise ValueError('Metric mismatch '+metric)
    for path_key,sha_key in [('trace_path','trace_sha256'),('effective_config_path','effective_config_sha256')]:
        target=owned(run/row[path_key]).resolve()
        if run not in target.parents or digest(target)!=row[sha_key]:raise ValueError('Run evidence drift')
    events=rows(run/row['trace_path'])
    if events[0]['kind']!='reset' or events[-1]['kind']!='terminal' or any(e['task_key']!=row['task_key'] for e in events):raise ValueError('Unclosed or cross-episode trace')
    for field,kind in [('model_inputs','model_input'),('model_calls','model_call'),('primitive_actions','primitive_action')]:counts[field]+=sum(e['kind']==kind for e in events)
for image in semantic['image_files']:
    path=owned(run/image['path']).resolve()
    if run not in path.parents or digest(path)!=image['sha256']:raise ValueError('Actual model image drift')
configs={row['effective_config_path']:row['effective_config_sha256'] for row in records}
if read_json(run/'effective-configs.json')!={'files':[{'path':k,'sha256':v} for k,v in sorted(configs.items())]}:raise ValueError('Effective config bundle mismatch')
receipt={'status':'PASS','claim_scope':'complete diagnostic episodes only; not a full benchmark result','run_id':manifest['run_id'],'manifest_sha256':identity,'auditor_sha256':digest(__file__),'counts':counts,'receipts':{name:digest(run/name) for name in ['results.jsonl','semantic_audit.json','independent_metrics.json','effective-configs.json']}}
atomic_json(run/'diagnostic_validation.json',receipt);print(json.dumps(receipt))
