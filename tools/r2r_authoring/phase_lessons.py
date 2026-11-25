"""Two synthetic high-impact advice contrasts using real G1/R1 contracts.

The supplied R0 advice is intentionally fallible, never a gold review. The gold
responses reject invented counts/stop relocation and preserve correct content.
No benchmark instructions or scene/episode identities are used.
"""
from copy import deepcopy
from tools.r2r_authoring.positive import field
from tools.r2r_authoring.review import levels, make_finding, AXES

SPECS = (
    dict(id='UNSUPPORTED_COUNT',source='Walk past the planters and stop at the blue cabinet.',
         target='the blue cabinet',ending='stop at the blue cabinet',condition='past the planters',
         check='C07',code='COUNT_SCOPE_DRIFT',source_quote='the planters',
         bad_claim='The candidate should specify exactly two planters.',
         bad_remedy='Replace the planters with two planters.',
         reason='The source specifies planters without a count. Neither the source nor correct candidate supplies two; reject the added quantity while preserving the planter pass and cabinet stop.',
         grules=['G-P2-A2','G-P2-C1','G-P2-C2'],rrules=['R-P2-C1','R-P2-C2','R-P2-C3']),
    dict(id='UNSUPPORTED_STOP_RELOCATION',source='Walk down the ramp to the landing. Walk to the cabinet and stop there.',
         target='the cabinet',ending='stop there',condition='Walk down the ramp to the landing.',
         check='C11',code='WRONG_TARGET',source_quote='Walk to the cabinet and stop there.',
         bad_claim='The final stop belongs at the landing before the cabinet movement.',
         bad_remedy='Stop on the landing, then continue toward the cabinet without the cabinet stop.',
         reason='The source independently requests cabinet travel after the landing and stops there. Moving that final stop across the cabinet event changes order and terminal scope; preserve the correct route unchanged.',
         grules=['G-P2-A5','G-P2-B3','G-P2-C1','G-P2-C2'],rrules=['R-P2-A3','R-P2-C1','R-P2-C2','R-P2-C3']),
)


def lessons():
    result={'generator':[], 'reviewer':[]}
    for spec in SPECS:
        src=spec['source'];ev=[dict(subtask_index=0,quote=src)]
        stage=dict(subtask_index=0,entry=dict(mode='episode_start',text='Use only the source episode start.',candidate_quotes=[]),
            target=field('The source-selected final cabinet.',spec['target']),
            process=field('Perform the complete ordered source process.',src),
            ending=dict(kind='explicit_event',text='The source-required final cabinet stop.',candidate_quotes=[spec['ending']],stop_scope='terminal'),
            conditions=field('Preserve the stated earlier route event before the final target.',spec['condition']),
            source_quotes=[src],carryover=[])
        good=dict(status='ok',subtasks=[src],issues=[],stage_audit=[stage],handoffs=[])
        view=dict(status='ok',subtasks=[src],issues=[])
        check=deepcopy(stage);check.update(status='supported',source_requirement_ids=['SRC-01'])
        gold=dict(verdict='pass',dimensions={d:'pass' for d in AXES},
            source_coverage=[dict(requirement_id='SRC-01',source_quote=src,requirement='Keep the ordered route, its stated quantities and final placement without additions.',candidate_evidence=ev,status='covered')],
            layer_checks=[],findings=[],stage_checks=[check],handoffs=[],prior_finding_reviews=[])
        levels(gold,{},1)
        prior=deepcopy(gold)
        f=make_finding(spec['code'],'L1_source_coverage',spec['check'],'source_fidelity',['SRC-01'],spec['source_quote'],ev,
                       spec['bad_claim'],spec['bad_remedy'],[0])
        prior.update(verdict='revise',dimensions=dict(source_fidelity='issue',closure_handoff='pass',segmentation_adequacy='pass'),findings=[f])
        prior['stage_checks'][0]['status']='gap';prior['source_coverage'][0]['status']='altered_or_missing'
        levels(prior,{'L1_source_coverage':(spec['bad_claim'],[0]),'L3_stage_checks':(spec['bad_claim'],[0]),'L6_route_readback':(spec['bad_claim'],[0])},1)
        answer=dict(candidate=good,responses=[dict(finding_index=0,decision='reject',source_quotes=[src],reason=spec['reason'])])
        final=deepcopy(gold)
        final['prior_finding_reviews']=[dict(finding_index=0,status='resolved',candidate_evidence=ev,explanation='The prior objection was unsupported. '+spec['reason'])]
        from host import protocol
        protocol.generator(src,good);protocol.reviewer(src,view,prior,rendered_instruction=src)
        protocol.feedback(src,prior,answer)
        protocol.reviewer(src,view,final,rendered_instruction=src,prior_review=prior,prior_candidate=view,prior_rendered_instruction=src)
        common=dict(id=spec['id'],source_kind='authored_synthetic',is_official_dataset_record=False,
            note='Prior R0 advice is intentionally wrong, not an answer to imitate. Only the expected phase output is gold for this teaching case.')
        result['generator'].append(dict(**common,phase='repair',rule_ids=spec['grules'],
            input=dict(original_instruction=src,candidate=view,review=prior),expected_output=answer))
        result['reviewer'].append(dict(**common,phase='recheck',rule_ids=spec['rrules'],
            input=dict(original_instruction=src,candidate=view,rendered_instruction=src,prior_review=prior,prior_candidate=view,prior_rendered_instruction=src),expected_output=final))
    return result
