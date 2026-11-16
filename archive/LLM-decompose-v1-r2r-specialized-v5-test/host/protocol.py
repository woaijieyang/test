"""Mechanical contracts and exact evidence linkage, with located diagnostics."""
import json
from functools import lru_cache
from jsonschema import Draft202012Validator
from shared.identity import need, text_hash
from host.compile import ROOT


def pointer(parts):
    return ''.join('/'+str(p).replace('~','~0').replace('/','~1') for p in parts)


def check(test, message, *, path='', code='CONTRACT_VIOLATION', **details):
    if 'stage_index' in details: details['stage_number']=details['stage_index']+1
    need(test,message,code=code,module='host.protocol',path=path,**details)


@lru_cache(maxsize=4)
def schema(path):
    return Draft202012Validator(json.loads((ROOT/path).read_bytes()))


def validate(path,value,*,prefix=''):
    err=next(schema(path).iter_errors(value),None)
    if err is None:return
    location=list(err.absolute_path)
    if err.validator=='required' and isinstance(err.instance,dict):
        missing=[k for k in err.validator_value if k not in err.instance]
        if missing:location.append(missing[0])
    details={}
    for i,part in enumerate(location[:-1]):
        if part in ('stage_audit','stage_checks') and isinstance(location[i+1],int):
            details['stage_index']=location[i+1]
    if not isinstance(err.instance,(dict,list)):details['actual']=err.instance
    check(False,'Bad '+path+': '+err.message,code='SCHEMA_VALIDATION_FAILED',
          path=prefix+pointer(location),schema_file=path,
          schema_path=pointer(err.absolute_schema_path),validator=err.validator,
          expected=err.validator_value,actual_type=type(err.instance).__name__,**details)


def quote(q,text,*,path='',target='source',stage_index=None):
    details={'target':target,'actual':q,'target_sha256':text_hash(text)}
    if stage_index is not None:details['stage_index']=stage_index
    check(isinstance(q,str) and bool(q.strip()),'Empty or invalid exact quotation',
          path=path,code='EXACT_QUOTE_INVALID',**details)
    check(q in text,'Unverifiable exact quotation',path=path,code='EXACT_QUOTE_NOT_FOUND',**details)


def entry(value,index,path,*,require_modes):
    """Check declared evidence; never infer a replacement mode or edit route text."""
    mode=value['mode']
    if require_modes:
        allowed=['episode_start','explicit_context'] if index==0 else ['explicit_context','inherited_pose','inherited_entity']
        check(mode in allowed,'Entry mode is inconsistent with the output stage index',
              code='ENTRY_MODE_INVALID_FOR_STAGE',path=path+'/mode',stage_index=index,
              actual=mode,expected=allowed,
              rule='The first output stage has no preceding output stage; later stages do not reset the episode.',
              interpretation_limit='Audit classification violation only; route correctness is not determined.')
    if mode=='explicit_context':
        check(bool(value['text']) and bool(value['text'].strip()) and bool(value['candidate_quotes']),
              'Explicit context needs an explanation and quotations from the actual stage',
              code='EXPLICIT_CONTEXT_EVIDENCE_MISSING',path=path,stage_index=index,
              actual={'text':value['text'],'candidate_quotes':value['candidate_quotes']},
              expected='Nonblank text and nonempty exact candidate quotations')


def generator(s,c,*,prefix=''):
    validate('generator/output.schema.json',c,prefix=prefix)
    ok=c['status']=='ok'
    check(bool(c['subtasks'])==ok and bool(c['issues'])!=ok,'Inconsistent candidate status',path=prefix+'/status')
    for i,t in enumerate(c['subtasks']):check(bool(t.strip()),'Blank stage',path=prefix+f'/subtasks/{i}',stage_index=i)
    for i,f in enumerate(c['issues']):quote(f['source_quote'],s,path=prefix+f'/issues/{i}/source_quote')
    check_generator_audit(s,c,prefix=prefix)


def check_generator_audit(s,c,*,prefix=''):
    parts=c['subtasks'];n=len(parts)
    if c['status']=='needs_review':
        check(not c['stage_audit'] and not c['handoffs'],'A source-limited response may not publish a partial stage audit',path=prefix+'/stage_audit')
        return
    check([a['index'] for a in c['stage_audit']]==list(range(n)),'Generator audit must cover every stage exactly once',path=prefix+'/stage_audit')
    check([(h['left'],h['right']) for h in c['handoffs']]==[(i,i+1) for i in range(n-1)],'Generator handoff audit must cover every adjacent pair',path=prefix+'/handoffs')
    for a in c['stage_audit']:
        i=a['index'];stage=parts[i];loc=prefix+f'/stage_audit/{i}'
        check(a['status']=='supported','Accepted candidate has an incomplete stage; revise cut/merge rather than invent state',path=loc+'/status',stage_index=i)
        check(bool(a['source_quotes']),'Stage must cite source evidence',path=loc+'/source_quotes',stage_index=i)
        for j,q in enumerate(a['source_quotes']):quote(q,s,path=loc+f'/source_quotes/{j}',stage_index=i)
        for key in ('entry','process','target','ending','conditions'):
            field=a[key]
            for j,q in enumerate(field['candidate_quotes']):quote(q,stage,path=loc+f'/{key}/candidate_quotes/{j}',target='candidate_stage',stage_index=i)
            if key in ('process','target','ending'):
                check(bool(field['text']) and bool(field['candidate_quotes']),f'Accepted stage requires grounded {key} in actual English',path=loc+'/'+key,stage_index=i)
        entry(a['entry'],i,loc+'/entry',require_modes=True)
        ending=a['ending']['kind']
        check(ending!='unspecified','Accepted stage has no supported completion; merge/rebound first',path=loc+'/ending/kind',stage_index=i)
        if ending=='terminal_goal_directive':
            check(i==n-1,'Terminal goal directive is allowed at final stage only',path=loc+'/ending/kind',stage_index=i)
            # Existing wording rule retained; its known limitations are documented.
            check(any(t in a['ending']['text'].lower() for t in ('not specified','unspecified','not asserted','no arrival','no explicit')),'Terminal directive must disclose absent arrival/STOP, not certify completion',path=loc+'/ending/text',stage_index=i)
    for j,h in enumerate(c['handoffs']):
        left,right=h['left'],h['right'];loc=prefix+f'/handoffs/{j}'
        check(h['status']=='supported' and h['entry_binding']!='coupled_unresolved','Accepted candidate has unsupported handoff; move cut or merge',path=loc)
        check(h['previous_exit'] and h['next_entry'] and h['left_quote'] and h['right_quote'],'Handoff must identify previous completion and next requirement',path=loc)
        quote(h['left_quote'],parts[left],path=loc+'/left_quote',target='candidate_stage',stage_index=left)
        quote(h['right_quote'],parts[right],path=loc+'/right_quote',target='candidate_stage',stage_index=right)
        check(bool(h['source_requirement_ids']),'Handoff needs evidence IDs',path=loc+'/source_requirement_ids')


def feedback(s,rev,ans):
    validate('generator/repair.schema.json',ans)
    check(sorted(r['finding_index'] for r in ans['responses'])==list(range(len(rev['findings']))),'Unanswered or repeated finding',path='/responses')
    for i,r in enumerate(ans['responses']):
        for j,q in enumerate(r['source_quotes']):quote(q,s,path=f'/responses/{i}/source_quotes/{j}')
    generator(s,ans['candidate'],prefix='/candidate')


def reviewer(s,c,r):
    validate('reviewer/output.schema.json',r)
    parts=c['subtasks'];n=len(parts);ver=r['verdict'];axes=r['dimensions']
    check([x['layer'] for x in r['layer_checks']]==[f'L{i}' for i in range(7)],'Reviewer must complete L0-L6 exactly once and in order',path='/layer_checks')
    check([x['index'] for x in r['stage_checks']]==list(range(n)),'Stage audit incomplete or reordered',path='/stage_checks')
    check([(x['left'],x['right']) for x in r['handoffs']]==[(i,i+1) for i in range(n-1)],'Adjacent handoff audit incomplete',path='/handoffs')
    ids=set(x['id'] for x in r['source_coverage'])
    check(len(ids)==len(r['source_coverage']) and ids,'Source coverage IDs must be unique',path='/source_coverage')
    for j,x in enumerate(r['source_coverage']):
        loc=f'/source_coverage/{j}';quote(x['source_quote'],s,path=loc+'/source_quote')
        check(x['state'] in ('covered','omitted','altered','superseded','source_ambiguous'),'Bad source coverage state',path=loc+'/state')
        for k,ev in enumerate(x['candidate_evidence']):
            check(0<=ev['index']<n,'Coverage evidence stage index invalid',path=loc+f'/candidate_evidence/{k}/index',actual=ev['index'])
            quote(ev['quote'],parts[ev['index']],path=loc+f'/candidate_evidence/{k}/quote',target='candidate_stage',stage_index=ev['index'])
        if x['state'] in ('omitted','altered'):
            check(any(f['source_quote']==x['source_quote'] or x['source_quote'] in f['source_quote'] or f['source_quote'] in x['source_quote'] for f in r['findings']),'Omitted/altered source item must be a finding',path=loc+'/state')
    for x in r['stage_checks']:
        i=x['index'];loc=f'/stage_checks/{i}'
        check(all(k in ids for k in x['source_requirement_ids']),'Stage references unknown source requirement',path=loc+'/source_requirement_ids',stage_index=i)
        for field in ('entry','process','target','ending','conditions'):
            for j,q in enumerate(x[field]['candidate_quotes']):quote(q,parts[i],path=loc+f'/{field}/candidate_quotes/{j}',target='candidate_stage',stage_index=i)
        entry(x['entry'],i,loc+'/entry',require_modes=ver=='pass')
        if x['entry']['mode']=='inherited_entity':check(x['entry']['text'],'Inherited entity must be uniquely identified',path=loc+'/entry/text',stage_index=i)
        if x['ending']['kind']=='terminal_goal_directive':
            check(i==n-1 and x['ending']['text'] and ('not' in x['ending']['text'].lower() or 'unspecified' in x['ending']['text'].lower()),'Terminal directive is final-only and cannot claim arrival',path=loc+'/ending',stage_index=i)
        if ver=='pass':check(x['status']=='supported' and x['entry']['mode']!='missing' and x['ending']['kind']!='unspecified' and x['ending']['text'],'Passing stage lacks supported entry or ending',path=loc,stage_index=i)
        if x['entry']['mode']=='missing' or x['ending']['kind']=='unspecified':check(x['status']!='supported','Missing entry/ending cannot be marked supported',path=loc+'/status',stage_index=i)
    for j,x in enumerate(r['handoffs']):
        loc=f'/handoffs/{j}'
        check(all(k in ids for k in x['source_requirement_ids']),'Handoff references unknown source requirement',path=loc+'/source_requirement_ids')
        for field,index in [('left_quote',x['left']),('right_quote',x['right'])]:
            if x[field]:quote(x[field],parts[index],path=loc+'/'+field,target='candidate_stage',stage_index=index)
        if x['entry_binding']=='coupled_unresolved':check(x['status']!='supported','Unresolved coupled boundary cannot pass',path=loc+'/status')
        if ver=='pass':check(x['status']=='supported' and x['previous_exit'] and x['next_entry'],'Pass contains unsupported handoff',path=loc)
    for j,f in enumerate(r['findings']):
        loc=f'/findings/{j}';quote(f['source_quote'],s,path=loc+'/source_quote')
        check(all(k in ids for k in f['source_requirement_ids']),'Finding references unknown source requirement',path=loc+'/source_requirement_ids')
        check(all(0<=i<n for i in f['subtask_indices']),'Finding stage index invalid',path=loc+'/subtask_indices')
        for k,ev in enumerate(f['candidate_evidence']):
            check(ev['index'] in f['subtask_indices'],'Candidate evidence outside finding scope',path=loc+f'/candidate_evidence/{k}/index')
            quote(ev['quote'],parts[ev['index']],path=loc+f'/candidate_evidence/{k}/quote',target='candidate_stage',stage_index=ev['index'])
        check(r['layer_checks'][int(f['layer'][1:])]['status']=='issue','Finding layer not marked issue',path=loc+'/layer')
        check(f['code'] in ('OMISSION','MISSING_ENTRY_ANCHOR','OPEN_INTERMEDIATE_STAGE','OVERSEGMENTED','UNDERSEGMENTED','WRONG_REFERENCE_FRAME','COUNT_SCOPE_DRIFT','DETACHED_CONDITION','UNSUPPORTED_ADDITION','WRONG_ORDER','WRONG_TARGET','WRONG_RELATION','LOST_EVENT','SOURCE_AMBIGUITY','OVERREJECTION'),'Unknown finding code',path=loc+'/code')
    for j,layer in enumerate(r['layer_checks']):
        check(all(0<=i<len(r['findings']) for i in layer['finding_indices']),'Layer references unknown finding',path=f'/layer_checks/{j}/finding_indices')
        if layer['status']=='issue':check(layer['finding_indices'],'Issue layer has no finding',path=f'/layer_checks/{j}/finding_indices')
    for dim in ('fidelity','closure_handoff','segmentation_adequacy'):
        if axes[dim] in ('issue','source_limited'):check(any(f['dimension']==dim or dim in f['related_dimensions'] for f in r['findings']),'Dimension diagnosis has no supporting finding',path='/dimensions/'+dim)
    if ver=='pass':
        check(c['status']=='ok' and not r['findings'] and all(v=='pass' for v in axes.values()),'Invalid pass',path='/verdict')
        check(all(x['state'] in ('covered','superseded') for x in r['source_coverage']),'Pass omits or alters a source requirement',path='/source_coverage')
        check(all(x['status'] in ('pass','not_applicable') for x in r['layer_checks']),'Pass has a failed audit layer',path='/layer_checks')
    else:
        check(r['findings'] and any(v in ('issue','source_limited') for v in axes.values()),'Non-pass lacks grounded issue',path='/verdict')
        if ver=='unresolved':check(any(v=='source_limited' for v in axes.values()),'Unresolved requires source limitation',path='/dimensions')
        if ver=='revise':check(any(v=='issue' for v in axes.values()),'Revise requires a repairable issue',path='/dimensions')
