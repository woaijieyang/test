"""Trace concrete teaching operations, not just skill-derived rule IDs."""
import hashlib
import json


# Existing active demonstrations with concrete source/candidate evidence, rather
# than a new rule inferred from a navigation result. Missing actions are checked
# through the actual Finding, not through a fabricated candidate quotation.
WITNESSES = {
    'R2R-CORE-G08': (['G-P2-A1'], ['YOU FACE A CHANDELIER', 'WALK TOWARDS THE OPEN DOOR ON THE FAR WALL'], [(0, 'facing the chandelier'), (0, 'Walk towards the open door on the far wall')], None, None),
    'R2R-CORE-G10': (['G-P2-A2'], ['pack exit'], [], None, None),
    'R2R-GEN-036': (['G-P2-A6'], ['If the doorway on your left is open', 'Otherwise'], [(0, 'If the doorway on your left is open'), (0, 'Otherwise')], None, None),
    'R2R-GEN-037': (['G-P2-A6'], ['walk around the table', 'return to the same doorway'], [(0, 'walk around the table'), (0, 'return to the same doorway')], None, None),
    'R2R-CORE-R08': (['R-P2-A1'], ['YOU FACE A CHANDELIER', 'WALK TOWARDS THE OPEN DOOR ON THE FAR WALL'], [(0, 'stop facing the chandelier')], 'revise', 'WRONG_TARGET'),
    'R2R-CORE-R10': (['R-P2-C1'], ['pack exit'], [], 'unresolved', 'SOURCE_AMBIGUITY'),
    'R2R-DIAG-30': (['R-P2-A4'], ['If the hallway on your left is open', 'Otherwise'], [(0, 'Then enter the room on your right')], 'revise', 'DETACHED_CONDITION'),
    'R2R-DIAG-31': (['R-P2-A4','R-P2-B3'], ['Walk away from the doorway to the bench.', 'Return to the same doorway'], [(0, 'Wait at the doorway.')], 'revise', 'OMISSION'),
    'R2R-DIAG-05': (['R-P2-B3'], ['Turn around, go past the bed, out the door and to the right.'], [(0, 'Go into the next door on the right.')], 'revise', 'OMISSION'),
}


def report(rows, phase_data, index, registry):
    active={item['template_id']:item for item in index if item['status'] in ('fixed_core','dynamic')}

    records=[]
    for row in rows.values():
        if row['template_id'] not in active:continue
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
    for tid,(rules,quotes,evidence,verdict,code) in WITNESSES.items():
        row=rows[tid];item=active[tid];role=row['role']
        src=(row.get('input') or row['review_input'])['original_instruction']
        parts=(row['output'] if role=='generator' else row['review_input']['candidate'])['subtasks']
        if (set(rules)-set(item['rule_ids']) or any(q not in src for q in quotes)
                or any(q not in parts[i] for i,q in evidence)):
            raise ValueError('Invalid active operation witness: '+tid)
        if verdict is not None:
            review=row['expected_review']
            if review['verdict']!=verdict or code not in [f['code'] for f in review['findings']]:
                raise ValueError('Invalid Reviewer operation witness: '+tid)
        elif not evidence and row['output']['status']!='needs_review':
            raise ValueError('Missing source limitation witness: '+tid)
        records.append(dict(template_id=tid,rule_ids=rules,role=role,
            phases=['initial','repair'] if role=='generator' else ['review','recheck'],
            evidence_pointer='/teaching_notes/'+('case_rationale' if role=='generator' else 'case_specific_focus'),
            projected_pointer='/lesson',source_quotes=quotes,
            candidate_evidence=[dict(subtask_index=i,quote=q) for i,q in evidence],
            operation=item['lesson'],counter_boundary=item['counter_boundary'],
            verdict=verdict,finding_code=code,
            verification='active source/candidate and authored decision checked; not a live model result'))
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
    p2=[node['id'] for node in registry if node['level']==2]
    coverage={rid:[r['template_id'] for r in records if rid in r['rule_ids']] for rid in p2}
    missing=[rid for rid,examples in coverage.items() if not examples]
    if missing:raise ValueError('Missing active P2 operation witness: '+repr(missing))
    return dict(kind='operation_evidence_trace',records=records,priority_rule_gaps=gaps,
        active_p2_witnesses=coverage,active_p2_without_witness=missing,
        coverage_scope='At least one active operation witness per P2; not exhaustive coverage of every subcase or verified model adherence.',
        limits=['Rule-ID metadata alone is not counted as demonstrated behavior.',
                'No independent human or live-model semantic certification.',
                'No fabricated C10 under-segmentation negative; requires independently established focus loss.',
                'G09/R09 contrast surface-bound movement, start and endpoint placement; no full standalone surface-motion diagnostic or live-model certification.'])
