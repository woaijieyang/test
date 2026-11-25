"""Explicit teaching-to-rule mapping; metadata never adds route facts.

Facets below describe authored lessons, not automatic truth judgments. Query
patterns only retrieve them. Missing branch/return/C10 evidence is reported,
never manufactured by tagging unrelated room-transition examples.
"""
GEN_RULES={
 'entity_frame':['G-P2-A3'],'frame':['G-P2-A3'],'ordinal':['G-P2-A3'],
 'terminal':['G-P2-B3'],'endpoint':['G-P2-A5','G-P2-B3'],'hall_end':['G-P2-B1'],
 'bounded':['G-P2-B3'],'stair_target':['G-P2-B1','G-P2-B3'],
 'scope':['G-P2-A4','G-P2-A5'],'attribute':['G-P2-A1'],'observation':['G-P2-A1'],
 'entry':['G-P2-B2'],'transit':['G-P2-B1'],'coupled':['G-P2-B1'],
 'direction':['G-P2-A3'],'attachment':['G-P2-A4'],'pass_by':['G-P2-A1','G-P2-A4'],
 'target_identity':['G-P2-A1','G-P2-A3'],'final_approach':['G-P2-B3'],
 'negation':['G-P2-A4'],'branch':['G-P2-A6'],'return':['G-P2-A6'],
 'uncertainty':['G-P2-A2'],'grouping':['G-P2-B1'],'lost_action':['G-P2-C2'],
}
REV_RULES={
 'entity_frame':['R-P2-A2'],'frame':['R-P2-A2'],'ordinal':['R-P2-A2'],
 'terminal':['R-P2-A3','R-P2-B2'],'endpoint':['R-P2-A3','R-P2-B2'],
 'hall_end':['R-P2-B1','R-P2-B2'],'bounded':['R-P2-A3'],'stair_target':['R-P2-B1'],
 'scope':['R-P2-A2','R-P2-A3'],'attribute':['R-P2-A1'],'observation':['R-P2-A1'],
 'entry':['R-P2-B2'],'transit':['R-P2-B1'],'coupled':['R-P2-B1'],
 'direction':['R-P2-A2'],'attachment':['R-P2-A2'],'pass_by':['R-P2-A1'],
 'target_identity':['R-P2-A1'],'final_approach':['R-P2-B2'],
 'negation':['R-P2-A4'],'branch':['R-P2-A4'],'return':['R-P2-A4'],
 'uncertainty':['R-P2-C1'],'grouping':['R-P2-B1'],'lost_action':['R-P2-B3'],
}
# Explicitly reviewed relation subtypes. Names must exist in FACET_PATTERNS.
POSITIVE_FACETS={
 1:['stair_turn','landmark_placement'],2:['stair_turn','arrival_trigger'],
 3:['stair_turn','pass_then_placement'],4:['expected_view','door_identity'],
 5:['door_identity','hall_end_entry','final_approach'],6:['hall_transit','arrival_trigger'],
 7:['ordered_turns','room_entry'],8:['pass_then_turn','doorway_stop'],
 9:['hall_transit','room_entry','doorway_stop'],10:['open_door_attribute','room_entry'],
 11:['hall_end_entry','ordered_turns','doorway_stop'],12:['ordered_turns','room_entry'],
 13:['open_door_attribute','hall_transit'],14:['transit_before_exit_stop'],
 15:['door_count_origin','ordinal_door'],16:['room_entry','landmark_placement'],
 17:['ordered_landmarks','door_identity'],18:['hall_until_bedroom','doorway_stop'],
 19:['preparatory_turn_ascent'],20:['modifier_attachment','ordinal_placement'],
 21:['bounded_ascent_refinement'],22:['ordered_crossings','final_approach'],
 23:['expected_view','explicit_arrival'],24:['ordered_turns','stair_wait'],
 25:['room_entry','behind_target'],26:['hall_transit','room_entry'],
 27:['ordered_turns','landmark_placement'],28:['center_door_selection'],
 29:['pass_then_placement','doorway_stop'],30:['object_relative_room','ordinal_room','landmark_placement'],
 31:['uncertain_name'],32:['hall_transit','stair_destination'],
 33:['ordered_landmarks','landmark_placement'],34:['hall_transit','hall_entry'],
 35:['modifier_attachment','hall_entry','ordinal_door'],
 36:['conditional_routes'],37:['required_return'],
}
DIAGNOSTIC_FACETS={
 1:['ordinal_door'],2:['ordered_turns'],3:['hall_transit','room_entry'],
 4:['doorway_stop'],5:['turnaround_entry'],6:['turn_after_landmark'],
 7:['ordinal_placement','landmark_placement'],8:['prohibited_entry'],9:['final_facing'],
 10:['maintained_frame'],11:['ordinal_door'],12:['ordered_turns','hall_end_entry'],
 13:['door_identity','room_entry'],14:['initial_frame'],15:['open_door_attribute','hall_transit'],
 16:['turn_until_frame'],17:['landmark_placement'],18:['prohibited_entry'],
 19:['maintained_frame','landmark_placement'],20:['landmark_placement'],
 21:['room_entry'],22:['explicit_arrival'],23:['window_side'],
 24:['hall_entry','modifier_attachment','ordinal_door'],25:['preparatory_turn_ascent'],
 26:['hall_entry','modifier_attachment','ordinal_door'],27:['open_door_attribute'],
 28:['hall_until_bedroom','doorway_stop'],29:['bounded_ascent_refinement'],
 30:['conditional_routes'],31:['required_return'],
}
CORE_REVIEW_FACETS={
 1:POSITIVE_FACETS[4],2:DIAGNOSTIC_FACETS[1],3:POSITIVE_FACETS[19],
 4:DIAGNOSTIC_FACETS[25],5:POSITIVE_FACETS[20],6:POSITIVE_FACETS[5],
 7:DIAGNOSTIC_FACETS[24],8:['expected_view','door_identity'],
 9:POSITIVE_FACETS[2],10:POSITIVE_FACETS[31],
}

def metadata(row, skills):
    tid=row['template_id'];role=row['role']
    mapping=GEN_RULES if role=='generator' else REV_RULES
    if set(skills)-set(mapping):raise ValueError('Unmapped teaching skills: '+repr(skills))
    rules=sorted({r for s in skills for r in mapping[s]})
    if role=='generator':
        num=int(row['provenance']['core_curated_from'][-3:]) if '-CORE-' in tid else int(tid[-3:])
        facets=POSITIVE_FACETS[num];polarity='source_limitation' if row['output']['status']!='ok' else 'generate'
    else:
        num=int(tid[-2:]) if '-CORE-' in tid or '-DIAG-' in tid else int(tid[-3:])
        facets=CORE_REVIEW_FACETS[num] if '-CORE-' in tid else DIAGNOSTIC_FACETS[num] if '-DIAG-' in tid else POSITIVE_FACETS[num]
        polarity={'pass':'accept','revise':'detect','unresolved':'source_limitation'}[row['expected_review']['verdict']]
    retrieval=set(skills)-{'lost_action','grouping'}
    # Match source relations, not hypothetical errors in a future candidate.
    if 'grouping' in skills:retrieval.update({'coupled','transit','entry','endpoint'})
    if 'lost_action' in skills:retrieval.update({'direction','entry'} if tid.endswith('05') else {'return'} if tid=='R2R-DIAG-31' else {'transit','entry','attribute'})
    from host.r2r.relations import route_family
    src=row['source'];family=route_family(src,src.get('split'))
    return dict(rule_ids=rules,retrieval_skills=sorted(retrieval),facets=facets,
                teaching_polarity=polarity,route_family=family,
                mapping_basis='Authored lesson and case-local contrast, not query keyword occurrence')
