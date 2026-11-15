"""Format and evidence linkage only: no semantic heuristics and no navigation scorer."""
import json
from functools import lru_cache
from jsonschema import Draft202012Validator
from shared.identity import need,ContractError
from host.compile import ROOT
@lru_cache(maxsize=4)
def schema(path):return Draft202012Validator(json.loads((ROOT/path).read_bytes()))
def validate(path,x):
    err=next(schema(path).iter_errors(x),None);need(err is None,('Bad '+path+': '+str(err.message)) if err else '')
def quote(q,s):need(isinstance(q,str) and q.strip() and q in s,'Unverifiable exact quotation')
def generator(s,c):
    validate('generator/output.schema.json',c)
    ok=c['status']=='ok';need(bool(c['subtasks'])==ok and bool(c['issues'])!=ok,'Inconsistent candidate status');need(all(t.strip() for t in c['subtasks']),'Blank stage')
    for f in c['issues']:quote(f['source_quote'],s)
def feedback(s,rev,ans):
    validate('generator/repair.schema.json',ans);need(sorted(r['finding_index'] for r in ans['responses'])==list(range(len(rev['findings']))),'Unanswered or repeated finding')
    for r in ans['responses']:
        for q in r['source_quotes']:quote(q,s)
    generator(s,ans['candidate'])

def reviewer(s,c,r):
    validate('reviewer/output.schema.json',r);parts=c['subtasks'];n=len(parts);ver=r['verdict'];axes=r['dimensions']
    need([x['subtask_index'] for x in r['stage_checks']]==list(range(n)),'Stage audit incomplete');need([(x['left'],x['right']) for x in r['handoffs']]==[(i,i+1) for i in range(n-1)],'Adjacent handoff audit incomplete')
    for x in r['stage_checks']:
        body=parts[x['subtask_index']]
        for q in x['source_quotes']:quote(q,s)
        for q in x['candidate_quotes']:quote(q,body)
        if x['completion_quote'] is not None:quote(x['completion_quote'],body)
        if x['completion_basis']=='unspecified':need(x['completion_condition'] is None and x['completion_quote'] is None,'Unspecified endpoint cannot assert completion')
        if ver=='pass':need(x['entry_context'] and x['required_history'] and x['candidate_quotes'] and x['completion_condition'] and x['completion_quote'] and x['completion_basis']!='unspecified','pass lacks process/entry/end evidence')
    for x in r['handoffs']:
        for q in x['source_quotes']:quote(q,s)
        for label in ('left','right'):
            if x[label+'_quote'] is not None:quote(x[label+'_quote'],parts[x[label]])
        if x['status']=='supported':need(all(x[k] for k in ('previous_exit','next_required_entry','completion_evidence','left_quote','right_quote')),'Supported handoff lacks evidence')
        if ver=='pass':need(x['status']=='supported','Broken handoff cannot pass')
    for f in r['findings']:
        quote(f['source_quote'],s);ix=f['subtask_indices'];need(all(0<=i<n for i in ix) and len(set(ix))==len(ix),'Invalid finding stage index')
        if n and not f['candidate_evidence']:need(f['code'] in ('OMISSION','MISSING_REQUIREMENT'), 'Existing candidate requires actual evidence except for an omission')
        for q in f['candidate_evidence']:
            need(q['index'] in ix,'Candidate evidence outside finding scope');quote(q['quote'],parts[q['index']])
        need(axes[f['dimension']] in ('issue','source_limited'),'Finding conflicts with axis')
    if ver=='pass':need(c['status']=='ok' and n and not r['findings'] and all(v=='pass' for v in axes.values()),'Invalid pass')
    else:
        need(r['findings'] and any(v in ('issue','source_limited') for v in axes.values()),'Non-pass lacks grounded issue');need(all(v not in ('issue','source_limited') or any(f['dimension']==k for f in r['findings']) for k,v in axes.items()),'Unsupported dimension diagnosis')
        if ver=='unresolved':need('source_limited' in axes.values(),'unresolved requires source limitation')
        if ver=='revise':need('issue' in axes.values(),'revise requires repairable issue')
