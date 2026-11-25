"""Trace concrete teaching operations, not just skill-derived rule IDs."""
import hashlib
import json


def report(rows, phase_data):
    records=[]
    for row in rows.values():
        boundary=row.get('teaching_notes',{}).get('decision_boundary')
        if not boundary:continue
        role=row['role'];src=(row.get('input') or row['review_input'])['original_instruction']
        parts=(row['output'] if role=='generator' else row['review_input']['candidate'])['subtasks']
        if any(q not in src for q in boundary['source_quotes']):raise ValueError('Invalid rule evidence source')
        if any(e['quote'] not in parts[e['subtask_index']] for e in boundary['candidate_evidence']):raise ValueError('Invalid rule evidence candidate')
        records.append(dict(template_id=row['template_id'],rule_ids=boundary['rule_ids'],role=role,
            phases=['initial','repair'] if role=='generator' else ['review','recheck'],
            evidence_pointer='/teaching_notes/decision_boundary',projected_pointer='/decision_boundary',
            source_quotes=boundary['source_quotes'],candidate_evidence=boundary['candidate_evidence'],
            operation=boundary['operation'],counter_boundary=boundary['counter_boundary'],
            verification='source/candidate quotes checked; projection tested, not live model comprehension'))
    for role,items in phase_data.items():
        path=f"{role}/dataset_rules/r2r_{'repair' if role=='generator' else 'recheck'}_examples.json"
        for i,item in enumerate(items):
            records.append(dict(template_id=item['id'],rule_ids=item['rule_ids'],role=role,phases=[item['phase']],
                path=path,evidence_pointer=f'/{i}/expected_output',
                source_sha256=hashlib.sha256(item['input']['original_instruction'].encode()).hexdigest(),
                verification='complete phase output passes active contract; erroneous prior advice explicitly labelled'))
    priority=['G-P2-B4','G-P2-C1','R-P2-C2','R-P2-C3']
    gaps=[rid for rid in priority if not any(rid in x['rule_ids'] for x in records)]
    if gaps:raise ValueError('Missing required operation teaching: '+repr(gaps))
    return dict(kind='operation_evidence_trace',records=records,priority_rule_gaps=gaps,
        limits=['Rule-ID metadata alone is not counted as demonstrated behavior.',
                'No independent human or live-model semantic certification.',
                'No fabricated C10 under-segmentation negative; requires independently established focus loss.',
                'Surface-motion cue is detectable; dedicated contrasting surface-motion teaching remains unclaimed.'])
