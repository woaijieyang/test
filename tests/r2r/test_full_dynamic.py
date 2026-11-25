"""Full runtime field preservation for every eligible R2R Dynamic case."""
import copy
import unittest
from host.compile import compile_prompt
from host.template_selector import library
from host.r2r.teaching import card, dynamic_is_detailed
from host.r2r.selection import select_bundle
from tests.r2r.test_refinement import parsed_cards

class FullDynamic(unittest.TestCase):
    def test_every_eligible_template_preserves_entire_output_and_source(self):
        for role in ('generator','reviewer'):
            for example in library(role,'r2r-en'):
                with self.subTest(role=role,template=example['template_id']):
                    before=copy.deepcopy(example)
                    value=card(example,role,True)
                    self.assertEqual(value['expected_output'],example['output'] if role=='generator' else example['expected_review'])
                    self.assertEqual(value['source'],(example.get('input') or example['review_input'])['original_instruction'])
                    if role=='reviewer':self.assertEqual(value['candidate'],example['review_input']['candidate'])
                    value['expected_output'].clear()
                    self.assertEqual(example,before)
                    with self.assertRaisesRegex(ValueError,'summary projection is disabled'):card(example,role,False)

    def test_all_positions_and_all_four_phases_remain_full(self):
        for source in ('Turn left at the chair and stop in the second doorway.',
                       'Return to the room and walk down two steps, then wait on the second step.'):
            bundle=select_bundle(source)
            for role,phase in [('generator','initial'),('reviewer','review'),('generator','repair'),('reviewer','recheck')]:
                ids=bundle[role]
                for i in range(len(ids)):self.assertTrue(dynamic_is_detailed(role,ids,i))
                text,_=compile_prompt(role,phase,profile='r2r-en',original_instruction=source,selected_ids=ids)
                cards=parsed_cards(text)
                self.assertEqual(len(cards),10+len(ids))
                self.assertTrue(all('expected_output' in c for c in cards))
                self.assertFalse(any(c['format']=='lesson_summary' for c in cards))
                self.assertEqual(text.count('ACTIVE OUTPUT SCHEMA for this phase'),1)

if __name__=='__main__':unittest.main()
