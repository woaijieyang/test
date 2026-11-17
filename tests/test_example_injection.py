import unittest,json
from host.compile import compile_prompt
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
        for profile in PROFILES:
            for role,phase in [('generator','initial'),('reviewer','recheck')]:
                source='Stop in the room. Stop beside the bed.'
                ids=select_examples(role,profile,source)
                text,schema=compile_prompt(role,phase,profile=profile,selected_ids=ids,original_instruction=source)
                cards=[json.loads(line) for line in text.splitlines() if line.startswith('{') and '"applicable_lesson"' in line]
                from host.compile import core_library
                fixed=core_library(role,profile)
                expected=[r['template_id'] for r in fixed]+ids
                self.assertEqual([c['template_id'] for c in cards],expected)
                originals={r['template_id']:r for r in [*fixed,*library(role,profile)]}
                for c in cards:
                    e=originals[c['template_id']];self.assertTrue(c['applicable_lesson'])
                    t=c['teaching']
                    is_first_in_group = c['template_id'] in (
                        (fixed[0]['template_id'] if fixed else None),
                        (ids[0] if ids else None)
                    )
                    if role=='generator':
                        self.assertEqual(t['stages'],e['output']['subtasks'])
                        self.assertEqual(t['handoffs'],e['output']['handoffs'])
                        self.assertEqual('stage_evidence' in t,is_first_in_group)
                    else:
                        self.assertEqual(t['findings'],e['expected_review']['findings'])
                        self.assertEqual(t['review_case'],e['review_input'])
                        self.assertEqual('coverage_evidence' in t,is_first_in_group)
                self.assertIn('two distinct stops',text)
                blank,other_schema=compile_prompt(role,phase,profile=profile,original_instruction=source,examples=False)
                self.assertEqual(other_schema,schema);self.assertNotIn('APPLY THE EXAMPLES',blank)
