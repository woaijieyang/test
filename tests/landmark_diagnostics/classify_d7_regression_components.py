"""Find inclusion-minimal allowed-component conflicts for the15 D7 route regressions."""
import json,hashlib,collections,itertools,datetime
from pathlib import Path
B=Path('outputs/landmark-connectivity');O=B/'D7-grounded-fine05-v1';sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();v=json.loads((O/'validation.json').read_text());audit=json.loads((O/'independent-static.json').read_text());assert audit['input_sha256']==sha(O/'validation.json');tr=json.loads((O/'static-transition-audit.json').read_text());parent=B/'full-native-v11/manifest.json';assert sha(parent)==v['parent_manifest_sha256'];tasks={t['task_key']:t for t in json.loads(parent.read_text())['tasks']};rows={r['task_key']:r for r in v['rows']};catalog={(r['node'],None if r['original_target'] is None else tuple(r['original_target'])):r for r in v['nodes']};reports=[];groups={}
def intersection(indices,sets):return set.intersection(*(sets[i] for i in indices)) if indices else {'unconstrained'}
for key in tr['regressed']:
 row=rows[key]
 task=tasks[key];entries=[catalog[(node,None if p is None else tuple(p))] for node,p in zip(task['original_viewpoint_path'],task['targets'])];sets=[set(e['components']) for e in entries];assert not intersection(range(len(sets)),sets)
 pairs=[(i,j) for i in range(len(sets)) for j in range(i+1,len(sets)) if not sets[i]&sets[j]]
 if any(not s for s in sets):core=[next(i for i,s in enumerate(sets) if not s)]
 elif pairs:core=list(min(pairs,key=lambda pair:(pair[1]-pair[0],pair)))
 else:
  core=list(range(len(sets)))
  for i in core.copy():
   reduced=[j for j in core if j!=i]
   if reduced and not intersection(reduced,sets):core=reduced
 assert not intersection(core,sets) and all(intersection([j for j in core if j!=i],sets) for i in core)
 members=[{'reference_index':i,'node':task['original_viewpoint_path'][i],'allowed_components':sorted(sets[i]),'candidates':entries[i]['components'],'anchor':entries[i]['anchor']} for i in core];signature=tuple((r['node'],tuple(r['allowed_components'])) for r in members);gid=hashlib.sha256(json.dumps(signature).encode()).hexdigest()[:16];group=groups.setdefault(gid,{'group_id':gid,'members':members,'task_keys':[],'core_size':len(core)});assert [(r['node'],r['allowed_components']) for r in group['members']]==[(r['node'],r['allowed_components']) for r in members];group['task_keys'].append(key);reports.append({'task_key':key,'group_id':gid,'core_reference_indices':core,'inclusion_minimal':True,'kind':'MISSING_SOURCE_BOUNDED_CANDIDATE' if any(not sets[i] for i in core) else 'COMPONENT_CONFLICT'})
assert len(reports)==15 and len({r['task_key'] for r in reports})==15;ordered=sorted(groups.values(),key=lambda r:(-len(r['task_keys']),r['group_id']));out=O/'component-conflict-cores.json';assert not out.exists();out.write_text(json.dumps({'status':'COMPLETE15_SOURCE_CANDIDATE_CONFLICT_LOCALIZATION_NOT_REPAIR','tasks':15,'distinct_conflicts':len(ordered),'groups':ordered,'records':reports,'proposal_sha256':sha(O/'validation.json'),'independent_static_sha256':sha(O/'independent-static.json'),'parent_manifest_sha256':sha(parent),'script_sha256':sha(__file__),'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'limits':'Inclusion-minimal conflicting candidate-component sets for this rejected mesh/proposal, not physical impossibility or exhaustive support-space proof. No task removed or coordinate adopted.'},indent=2)+'\n');print('CONFLICTS',len(ordered));print('TOP',[(len(r['task_keys']),[(m['node'],m['allowed_components']) for m in r['members']]) for r in ordered[:5]])
