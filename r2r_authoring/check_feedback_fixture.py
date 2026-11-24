"""Debug the authored partial-accept replay without making model calls."""
from copy import deepcopy
import json
from adapter.source import Source
from renderer.freeze import freeze
from host import protocol
from host.compile import ROOT
from r2r.test_quality import fullpass,run

def main():
    ex=json.loads((ROOT/'generator/repair_examples.json').read_bytes())[0]
    source=ex['input']['original_instruction'];good=deepcopy(ex['output']['candidate'])
    def edit(x):
        if isinstance(x,str):return x.replace('Go around the right side of the center unit','Go around the left side of the center unit').replace('right side of the center unit','left side of the center unit')
        if isinstance(x,list):return [edit(v) for v in x]
        if isinstance(x,dict):return {k:(v if k=='source_quotes' else edit(v)) for k,v in x.items()}
        return x
    bad=edit(deepcopy(good));r0=deepcopy(ex['input']['review'])
    r0['findings'][0]['repair']['instruction']+=' Add a stop at the center unit before going to the doorway.'
    answer=deepcopy(ex['output']);answer['responses'][0].update(decision='partially_accept',reason='Restore the supported right-side traversal while keeping only the source doorway stop.')
    view=freeze(Source('probe','R2R','en',source),bad['subtasks'],'\n')
    candidate={'status':'ok','subtasks':list(view.stages),'issues':[]}
    checks=[('generator',lambda:protocol.generator(source,bad)),('review_raw',lambda:protocol.reviewer(source,bad,r0)),('review_frozen',lambda:protocol.reviewer(source,candidate,r0,rendered_instruction=view.rendered)),('feedback',lambda:protocol.feedback(source,r0,answer))]
    for name,check in checks:
        try:check();print('FIXTURE_CHECK',name,'PASS')
        except Exception as e:print('FIXTURE_CHECK',name,str(e),getattr(e,'details',None))
    r1=fullpass(source,good);r1['prior_finding_reviews']=[dict(finding_index=0,status='resolved',candidate_evidence=[dict(subtask_index=0,quote=good['subtasks'][0])],explanation='The actual right-side traversal is restored and the extra stop was rejected.')]
    result,requests,pending=run(source,[bad,r0,answer,r1])
    print('FIXTURE_RESULT',json.dumps({'error':result['error'],'disposition':result['disposition'],'pending':len(pending),'calls':[{'phase':c['phase'],'validation':c.get('validation'),'errors':c.get('validation_errors'),'output_keys':list(c.get('raw_output',{})),'user':c['request']['messages'][1]['content']} for c in result['calls']]},ensure_ascii=False))
if __name__=='__main__':main()
