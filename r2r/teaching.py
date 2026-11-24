"""R2R-only teaching projection. Runtime output contracts stay unchanged."""
from copy import deepcopy
from r2r.selection import teaching_index, _verify

FULL_GENERATOR={'R2R-CORE-G02','R2R-CORE-G10'}
FULL_REVIEWER={'R2R-CORE-R02','R2R-CORE-R06','R2R-CORE-R07','R2R-CORE-R10'}

def card(example,role,detailed):
    index,_=teaching_index();item=index.get(example['template_id'])
    if item is None:raise ValueError('Unindexed R2R teaching card')
    _verify(example,item)
    if role!=example['role']:raise ValueError('Teaching role mismatch')
    source=(example.get('input') or example['review_input'])['original_instruction']
    result=dict(template_id=example['template_id'],source=source,lesson=item['lesson'],
                counter_boundary=item['counter_boundary'],skills=item['skills'],
                format='lesson_summary')
    if role=='generator':
        out=example['output'];result['stages']=deepcopy(out['subtasks'])
        result['source_issues']=deepcopy(out['issues'])
        result['decision']=dict(status=out['status'],mode=example['decision']['mode'])
        result['boundary_evidence']=[dict(after_stage=h['from_subtask_index'],completed_event=h['preceding_exit']['candidate_quote'],next_action_context=h['next_entry']['candidate_quote']) for h in out['handoffs']]
        result['completion_evidence']=[dict(stage=s['subtask_index'],event=s['ending']['candidate_quotes'],kind=s['ending']['kind'],stop_scope=s['ending']['stop_scope']) for s in out['stage_audit']]
        if example['template_id'] in FULL_GENERATOR:
            result['format']='complete_initial_output_demonstration'
            result['expected_output']=deepcopy(out)
            # The complete object already contains these same stages and quotes.
            for key in ('stages','source_issues','boundary_evidence','completion_evidence'):result.pop(key)
    else:
        out=example['expected_review'];result['candidate']=deepcopy(example['review_input']['candidate'])
        result['verdict']=out['verdict'];result['dimensions']=deepcopy(out['dimensions'])
        result['evidence_excerpt']=[dict(source=f['source_quote'],candidate=deepcopy(f['candidate_evidence']),check=f['c_check'],affected_requirements=f['source_requirement_ids']) for f in out['findings']]
        result['local_repair']=[dict(action=f['repair']['instruction'],preserve=f['repair']['protected_requirements']) for f in out['findings']]
        if not out['findings']:
            result['evidence_excerpt']=[dict(source=c['source_quote'],candidate=deepcopy(c['candidate_evidence']),status=c['status']) for c in out['source_coverage']]
        if example['template_id'] in FULL_REVIEWER:
            result['format']='complete_review_output_demonstration'
            result['expected_output']=deepcopy(out)
            for key in ('verdict','dimensions','evidence_excerpt','local_repair'):result.pop(key)
    return result
