import unittest,json
from host.compile import compile_prompt, runtime_review_output
from host.template_selector import PROFILES,select_examples,library

class InjectionTests(unittest.TestCase):
    def test_actual_source_is_used_even_with_frozen_ids(self):
        from host.run import request
        text='Walk out of the room, veering left.'
        ids=select_examples('generator','r2r-en',text)
        req=request('generator','initial',dict(original_instruction=text),dict(model='fixture',effort='high'),'r2r-en',ids)
        self.assertIn('participial action',req['messages'][0]['content'])
        self.assertEqual(req['selected_example_ids'],ids)

    def test_cards_preserve_decision_and_keep_diagnostic_evidence(self):
        from host.compile import core_library
        for profile in PROFILES:
            for role,phase in [('generator','initial'),('reviewer','recheck')]:
                source='Stop in the room. Stop beside the bed.'
                ids=select_examples(role,profile,source)
                text,schema=compile_prompt(role,phase,profile=profile,selected_ids=ids,original_instruction=source)
                cards=[json.loads(line) for line in text.splitlines() if line.startswith('{') and '"template_id"' in line and ('"applicable_lesson"' in line or '"format"' in line)]
                fixed=core_library(role,profile)
                self.assertEqual([c['template_id'] for c in cards],[r['template_id'] for r in fixed]+ids)
                originals={r['template_id']:r for r in [*fixed,*library(role,profile)]}
                for c in cards:
                    e=originals[c['template_id']]
                    if profile=='r2r-en':
                        self.assertTrue(c['lesson']);self.assertTrue(c['counter_boundary'])
                        self.assertEqual(c['source'],(e.get('input') or e['review_input'])['original_instruction'])
                        if 'expected_output' in c:
                            expected=e['output'] if role=='generator' else e['expected_review']
                            self.assertEqual(c['expected_output'],expected)
                        elif role=='generator':
                            self.assertEqual(c['stages'],e['output']['subtasks'])
                            self.assertEqual(c['decision']['status'],e['output']['status'])
                            self.assertEqual(c['boundary_evidence'],[dict(after_stage=h['from_subtask_index'],completed_event=h['preceding_exit']['candidate_quote'],next_action_context=h['next_entry']['candidate_quote']) for h in e['output']['handoffs']])
                        else:
                            self.assertEqual(c['candidate'],e['review_input']['candidate'])
                            self.assertEqual(c['verdict'],e['expected_review']['verdict'])
                            for shown,finding in zip(c['evidence_excerpt'],e['expected_review']['findings']):
                                self.assertEqual(shown['source'],finding['source_quote'])
                                self.assertEqual(shown['candidate'],finding['candidate_evidence'])
                            self.assertEqual(len(c['local_repair']),len(e['expected_review']['findings']))
                    else:
                        self.assertTrue(c['applicable_lesson']);t=c['teaching']
                        is_fixed=c['template_id'] in {x['template_id'] for x in fixed}
                        detail=is_fixed or c['template_id']==ids[0]
                        if role=='generator':
                            self.assertEqual(t['stages'],e['output']['subtasks'])
                            self.assertEqual(t['handoffs'],e['output']['handoffs'])
                            self.assertEqual('stage_evidence' in t,detail)
                        else:
                            self.assertEqual(t['findings'],runtime_review_output(e)['findings'])
                            self.assertEqual(t['review_case'],e['review_input'])
                            self.assertEqual('coverage_evidence' in t,detail)
                            if is_fixed:
                                self.assertEqual(len(t['stage_checks']),len(e['review_input']['candidate']['subtasks']))
                                self.assertEqual(len(t['layer_checks']),7)
                self.assertIn('two distinct stops',text)
                blank,other_schema=compile_prompt(role,phase,profile=profile,original_instruction=source,examples=False)
                self.assertEqual(other_schema,schema);self.assertNotIn('APPLY THE EXAMPLES',blank)
