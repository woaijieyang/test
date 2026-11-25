"""Reproducible source-local R2R authoring; no online semantic rewriting."""
from pathlib import Path
import argparse,copy,hashlib,json,re,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from r2r_authoring.detail import author_generator,author_paired,finalize_detail
from r2r_authoring.review import repair_diagnostic,finalize_special,levels
PARENT='081db4b9ea0712ff720c137fe96c240c26f7b15c'
EVALUATED='9dd24a655a845d59698e835c0326fbf73db5fbb8'
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
def sha(data):return hashlib.sha256(data).hexdigest()
def encode(obj):return (json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode()

def materialize():
    paths=[n for n in git('ls-tree','-r','--name-only',EVALUATED).decode().splitlines() if '/templates/R2R/' in n and n.endswith('.json')]
    raw={p:git('show',EVALUATED+':'+p) for p in paths}
    data={p:json.loads(v) for p,v in raw.items()};original=copy.deepcopy(data)
    rows={r['template_id']:r for r in data.values()}
    if len(rows)!=119:raise ValueError('Unexpected source inventory')
    gens={int(t[-3:]):r for t,r in rows.items() if t.startswith('R2R-GEN-')}
    author_errors=[]
    for n,row in gens.items():
        try:author_generator(row,n)
        except Exception as exc:author_errors.append({'template_id':row['template_id'],'error':str(exc)})
    if author_errors:
        print('AUTHOR_SPEC_ERRORS '+json.dumps(author_errors,ensure_ascii=False));raise ValueError('Explicit positive authoring specification requires correction')
    for tid,row in rows.items():
        if tid.startswith('R2R-CORE-G'):author_generator(row,int(row['provenance']['core_curated_from'][-3:]))
        elif tid.startswith('R2R-REV-'):author_paired(row,gens[int(tid[-3:])],int(tid[-3:]))
    for tid,n in {'R2R-CORE-R01':4,'R2R-CORE-R03':19,'R2R-CORE-R05':20,'R2R-CORE-R09':2}.items():author_paired(rows[tid],gens[n],n)
    for tid,row in rows.items():
        if tid.startswith('R2R-DIAG-'):repair_diagnostic(row,int(tid[-2:]))
    finalize_special(rows)
    for row in rows.values():
        notes=row['teaching_notes'];lesson=notes.get('case_rationale') if row['role']=='generator' else notes.get('case_specific_focus')
        if lesson:
            notes['decision_reason']=lesson
            if row['role']=='reviewer':notes['review_principle']=lesson
        if row['role']=='reviewer' and row['expected_review']['verdict']=='pass':levels(row['expected_review'],{},len(row['review_input']['candidate']['subtasks']))
    finalize_detail(rows)
    from host import protocol
    from host.template_selector import validate_template
    errors=[]
    for path,row in data.items():
        src=(row.get('input') or row['review_input'])['original_instruction'];old=original[path];oldsrc=(old.get('input') or old['review_input'])['original_instruction']
        if src!=oldsrc or row['source']!=old['source']:raise ValueError('Source identity changed: '+path)
        try:
            validate_template(row['role'],row,source_path=path)
            if row['role']=='generator':protocol.generator(src,row['output'])
            else:protocol.reviewer(src,row['review_input']['candidate'],row['expected_review'])
        except Exception as exc:errors.append({'template_id':row['template_id'],'error':str(exc)})
    if errors:
        print('AUTHORING_ERRORS '+json.dumps(errors,ensure_ascii=False));raise ValueError(f'{len(errors)} authored templates fail active contracts')
    gc=[rows[f'R2R-CORE-G{i:02d}'] for i in range(1,11)];rc=[rows[f'R2R-CORE-R{i:02d}'] for i in range(1,11)]
    pg={r['provenance']['core_curated_from'] for r in gc};pr={r['provenance']['core_curated_from'] for r in rc}
    index=[];changes=[]
    for path,row in sorted(data.items()):
        tid=row['template_id'];source=(row.get('input') or row['review_input'])['original_instruction'];notes=row['teaching_notes']
        status='fixed_core' if '-CORE-' in tid else 'source_archive' if tid in pg|pr else 'retained_pair' if row.get('pair_id') in pg else 'dynamic'
        skills=notes.get('primary_skills')
        if not skills:
            lookup={'C01':'lost_action','C02':'attribute','C03':'scope','C04':'scope','C05':'target_identity','C06':'frame','C07':'ordinal','C08':'endpoint','C09':'entry','C10':'grouping','C11':'terminal','C12':'expression'}
            skills=sorted({lookup[f['c_check']] for f in row.get('expected_review',{}).get('findings',[])}) or ['uncertainty']
        blob=encode(row);pair=row.get('pair_id');relation=None
        if pair in rows:
            other=rows[pair];relation='same_source' if source==(other.get('input') or other['review_input'])['original_instruction'] else 'analogy'
        lesson=(notes.get('case_rationale') if row['role']=='generator' else notes.get('case_specific_focus')) or notes.get('transfer_rule') or notes.get('review_principle')
        if not lesson:raise ValueError('Missing concrete lesson: '+tid)
        index.append(dict(template_id=tid,path=path,role=row['role'],status=status,pair_id=pair,pair_relation=relation,source_sha256=sha(source.encode()),source_family=row['source'].get('source_key'),content_sha256=sha(blob),skills=skills,lesson=lesson,reusable_rule=notes.get('reusable_rule') or notes.get('transfer_rule'),counter_boundary=notes.get('counter_example_boundary') or notes.get('anti_pattern'),quality='authored_and_contract_checked'))
        changes.append(dict(template_id=tid,path=path,source_sha256=sha(source.encode()),evidence_blob=sha(raw[path]),result_sha256=sha(blob),changed=original[path]!=row))
    outputs={p:encode(r) for p,r in data.items()}
    outputs['shared/dataset_rules/r2r_teaching_index.json']=encode({'profile':'r2r-en','items':index})
    outputs['provenance/r2r_teaching_changes.json']=encode(dict(parent_commit=PARENT,evaluated_commit=EVALUATED,templates=changes,template_count=len(data),runtime_eligible=sum(r['status'] in ('fixed_core','dynamic') for r in index),source_identities_preserved=True,active_contracts_validated=True,review_method='Explicit source-local model-assisted review; evaluated stage evidence is retained unless a listed field repair applies. No independent human certification.',semantic_correctness_certified=False,navigation_evaluated=False))
    registry=[]
    for role in ('generator','reviewer'):
        text=(ROOT/role/'dataset_rules/r2r_en.md').read_text()
        for m in re.finditer(r'^#{2,3} ([GR]-P[012](?:-[A-Z][0-9]?)?)\s+—\s+(.+)$',text,re.M):
            rid,title=m.groups();level=int(rid[3]);parent=None if level==0 else rid[0]+'-P0' if level==1 else rid[0]+'-P1-'+rid.split('-')[-1][0]
            registry.append(dict(id=rid,role=role,level=level,parent=parent,title=title,path=f'{role}/dataset_rules/r2r_en.md'))
    ids={r['id'] for r in registry}
    if len(ids)!=len(registry) or not registry or any(r['parent'] and r['parent'] not in ids for r in registry):raise ValueError('Broken role-rule inheritance')
    outputs['provenance/r2r_rule_links.json']=encode({'common_authority':'shared/semantic_contract.md','shared_interpretations':'shared/dataset_rules/r2r_en.md','nodes':registry})
    return outputs

def main():
    p=argparse.ArgumentParser();p.add_argument('--write',action='store_true');p.add_argument('--check',action='store_true');args=p.parse_args();outputs=materialize();changed=[]
    for rel,blob in outputs.items():
        path=ROOT/rel
        if not path.exists() or path.read_bytes()!=blob:
            changed.append(rel)
            if args.write:path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(blob)
    print(json.dumps({'mode':'write' if args.write else 'check','assets':len(outputs),'changed':changed}))
    if changed and not args.write:raise SystemExit(1)
if __name__=='__main__':main()
