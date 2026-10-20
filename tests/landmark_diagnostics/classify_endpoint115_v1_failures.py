"""Reconcile every completed v1 result/audit and classify failures without exclusions."""
import collections,datetime,hashlib,json,math,os,re,sys,time
from pathlib import Path
R=Path.cwd();sys.path.insert(0,str(R/'scripts'))
from workspace import digest,atomic_json
assert os.environ.get('CASE1_PROTECTION');os.nice(15)
B=R/'outputs/connectivity/endpoint115-full-motion-v1';O=R/'outputs/connectivity/endpoint115-v1-failure-classification-v1';O.mkdir(exist_ok=False)
process=json.loads((B/'process.json').read_text());atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
while not (B/'validation.json').exists():
 p=Path('/proc')/str(process['pid'])/'stat';assert p.exists(),'Parent exited without full receipt';f=p.read_text().rsplit(')',1)[1].split();assert f[0]!='Z' and f[19]==process['start_ticks'];time.sleep(30)
v=json.loads((B/'validation.json').read_text());m=json.loads((B/'manifest.json').read_text());assert v['manifest_sha256']==digest(B/'manifest.json') and v['coverage_complete'] and v['expected']==3062
rows=v['results'];assert len(rows)==len({r['task_key'] for r in rows})==3062 and {r['task_key'] for r in rows}==set(m['task_keys'])
D=R/'data/derived/annotations/awarevln-endpoint115-v1';changes=json.loads((D/'changes.json').read_text());new106={r['task_key'] for r in changes['new106']};all115={r['task_key'] for rows0 in changes['all115_against_original'].values() for r in rows0};assert len(new106)==106 and len(all115)==115
bound=json.loads((D/'manifest.json').read_text());assert digest(D/'manifest.json')==m['derivative_manifest_sha256'];assert all(digest(p)==h for p,h in bound['source_files_unchanged'].items()) and all(digest(p)==h for p,h in bound['derived_files'].items());assert all(digest(p)==h for p,h in m['sources'].items())
counts=collections.Counter();by_ds=collections.defaultdict(collections.Counter);by_scene=collections.defaultdict(collections.Counter);scopes=collections.defaultdict(collections.Counter);reports=[];actions=0;maximum=0.;oversteps=[];early=set();maxima={};audit_issues=[]
for row in rows:
 assert digest(row['result_path'])==row['result_sha256'] and digest(row['audit_path'])==row['audit_sha256'];d=json.loads(Path(row['result_path']).read_text());a=json.loads(Path(row['audit_path']).read_text());key=row['task_key'];assert d['task_key']==a['task_key']==key and a['result_sha256']==row['result_sha256'] and a['manifest_sha256']==d['guard_manifest_sha256'];assert a['status']==row['status'] and a['error']==d['error']==row['error'];assert a['independent_replay'] and math.isfinite(a['max_replay_error']) and a['max_replay_error']<=1e-5;actions+=a['actions'];maximum=max(maximum,a['max_replay_error']);assert len(d['actions'])==a['actions'] and len(d['positions'])==len(d['actions'])+1
 if row['status']=='PASS_STRICT_MOTION_REPLAY':
  assert not a['source_alerts'] and d['error'] is None;category='PASS_STRICT_MOTION_REPLAY'
 elif d['error']=="AssertionError('actual_horizontal_limit')":
  category='NATIVE_HORIZONTAL_OVERSTEP';p,q=d['positions'][-2:];act=d['actions'][-1];horizontal=math.hypot(q[0]-p[0],q[2]-p[2]);assert horizontal>((.25 if act==1 else 0)+1e-4) and any(t['kind']=='displacement' and t['position']==len(d['actions']) for t in a['source_alerts']);oversteps.append(horizontal)
 elif re.fullmatch(r"RuntimeError\('legal_action_search_exhausted:[0-9]+'\)",d['error']):
  nodes=int(d['error'].split(':')[-1].split("'")[0]);assert 1<=nodes<=5000 and not a['source_alerts'];category='SEARCH_NODE_BUDGET_5000' if nodes==5000 else 'SEARCH_FRONTIER_EXHAUSTED_'+str(nodes)
  if nodes<5000:early.add(key)
 else:raise AssertionError(('Unclassified failure',key,d['error']))
 ds=key.split('|')[0];scene=key.split('|')[3];counts[category]+=1;by_ds[ds][category]+=1;by_scene[scene][category]+=1;scopes['new106' if key in new106 else 'prior9' if key in all115 else 'unchanged2947'][category]+=1
 reports.append({'task_key':key,'category':category,'error':d['error'],'actions':a['actions'],'independent_replay_error':a['max_replay_error'],'actual_alert_count':len(a['source_alerts']),'result_path':row['result_path'],'result_sha256':row['result_sha256'],'audit_path':row['audit_path'],'audit_sha256':row['audit_sha256']})
assert sum(by_ds['r2r'].values())==1839 and sum(by_ds['rxr'].values())==1223
front=R/'outputs/connectivity/endpoint115-v1-frontier-diagnostic-v1/validation.json';fr=json.loads(front.read_text());assert {r['task_key'] for r in fr['records']}==early
root=[r for r in fr['records'] if r['failure']=="RuntimeError('legal_action_search_exhausted:1')"]
assert all(r['prefix_actions']==0 and r['last_actual_source_contact'] is None and all(p['source_sweep_contact'] is not None for p in r['probes']) for r in root)
summary={'status':'COMPLETE_ALL3062_CLASSIFIED_NOT_ACCEPTED','coverage':3062,'counts':dict(counts),'dataset_counts':{k:dict(v) for k,v in by_ds.items()},'scene_counts':{k:dict(v) for k,v in by_scene.items()},'annotation_scope_counts':{k:dict(v) for k,v in scopes.items()},'actions_independently_replayed':actions,'max_independent_replay_error':maximum,'horizontal_overstep_range_m':[min(oversteps),max(oversteps)],'root_frontier_tasks':len(root),'root_frontier_reason':'Original initial pose is source-clear, but each of three native next actions intersects fixed source cylinder. Native rotations alter floor height before resulting body collision. This blocks all first actions for these starts under this fixed profile/protocol; not a proof of general physical impossibility.','early_frontier_receipt_sha256':digest(front),'frontier_snapshot_note':'Original frontier probe records its completion-time results-index hash; this final reconciliation independently verifies every selected task/result hash and exact coverage of all sub5000 failures.','records':reports,'validation_sha256':digest(B/'validation.json'),'manifest_sha256':digest(B/'manifest.json'),'script_sha256':digest(__file__),'time':datetime.datetime.now().astimezone().isoformat(),'formal_launch_allowed':False,'limits':'All failures retained; search-budget/frontier failure is distinct from source geometry impossibility. v1 and v2 cannot be pooled. Strict actual/native/source/replay gates unchanged.'}
atomic_json(O/'validation.json',summary);print(json.dumps({k:summary[k] for k in ['status','counts','actions_independently_replayed','max_independent_replay_error','horizontal_overstep_range_m','root_frontier_tasks']}))
