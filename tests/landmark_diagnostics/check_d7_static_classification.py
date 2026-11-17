"""Reproduce the114 retained tiled static failures from saved candidate evidence."""
from pathlib import Path
import collections, hashlib, itertools, json
R=Path.cwd();B=R/'outputs/landmark-connectivity'
run=B/'D7-grounded-tiled-mixed-v1'
validation=run/'validation.json'
v=json.loads(validation.read_text())
tasks={t['task_key']:t for t in json.loads((run/'candidate_tasks.json').read_text())['tasks']}
original=B/'D7-tiled-static114-classification-v1.json'
record=json.loads(original.read_text())
assert hashlib.sha256(validation.read_bytes()).hexdigest()==record['source_sha256']
nodes={}
for n in v['nodes']:
    key=(n['node'],tuple(n['original_target']) if n['original_target'] is not None else None)
    if key in nodes:assert nodes[key]['components']==n['components']
    else:nodes[key]=n
rows=[]
for r in v['rows']:
    if r['status']!='NO_SOURCE_CLEAR_COMMON_COMPONENT':continue
    t=tasks[r['task_key']]
    assert len(t['targets'])==len(t['original_viewpoint_path'])
    sets=[set(nodes[(node,tuple(target) if target is not None else None)]['components'])
          for node,target in zip(t['original_viewpoint_path'],t['targets'])]
    assert not set.intersection(*sets)
    missing=[i for i,s in enumerate(sets) if not s]
    pair=next(([i,j] for i,j in itertools.combinations(range(len(sets)),2) if not sets[i]&sets[j]),None)
    rows.append({'task_key':r['task_key'],'category':'missing_source_clear_candidate' if missing else 'disjoint_candidate_components',
                 'missing_nodes':[t['original_viewpoint_path'][i] for i in missing],
                 'first_disjoint_pair':None if pair is None else [{'index':i,'node':t['original_viewpoint_path'][i],'components':sorted(sets[i])} for i in pair]})
assert rows==record['rows'] and len(rows)==114
nonmain=collections.Counter()
for r in rows:
    for point in r['first_disjoint_pair'] or []:
        if point['components']!=['0']:nonmain[point['node']]+=1
output=B/'D7-tiled-static114-classification-reproduction-v1.json'
assert not output.exists()
output.write_text(json.dumps({'status':'PASS_SAVED_STATIC_CLASSIFICATION_REPRODUCTION','records':114,
    'source_report_sha256':hashlib.sha256(original.read_bytes()).hexdigest(),
    'first_conflict_nonmain_node_counts':dict(nonmain),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'limits':'First conflicting pair classifies each record; it is not an exhaustive minimal cut or proof of physical impossibility.'},indent=2))
print('PASS',len(rows),dict(nonmain))

