import json, unittest
from adapter.source import from_record, Source
from host.compile import compile_prompt
from host.protocol import reviewer
from shared.identity import ContractError

class FinalBestContract(unittest.TestCase):
    def test_r2r_nested_vlnce_english(self):
        s = from_record({'dataset':'r2r','split':'val_unseen','episode_id':7,
                         'instruction':{'instruction_text':' Walk  to the door. '}})
        self.assertEqual((s.dataset,s.language,s.raw,s.key),
                         ('R2R','en',' Walk  to the door. ','r2r:val_unseen:7'))
        self.assertEqual(s.prefix,' ')
        self.assertEqual(s.suffix,' ')

    def test_rxr_guide_jsonl_en_us(self):
        s = from_record({'dataset':'rxr','split':'train','instruction_id':19,
                         'language':'en-US','instruction':'Walk toward the window.'})
        self.assertEqual(s.key,'rxr:train:en-US:19')
        self.assertEqual(s.raw,'Walk toward the window.')

    def test_language_and_conflict_rejected(self):
        with self.assertRaises(ContractError):
            from_record({'dataset':'rxr','split':'train','instruction_id':1,
                         'language':'en-GB','instruction':'Walk.'})
        with self.assertRaises(ContractError):
            from_record({'dataset':'r2r','split':'train','episode_id':1,
                         'instruction_text':'Walk.','original_instruction':'Turn.'})

    def test_both_roles_receive_same_acceptance_contract(self):
        g,_=compile_prompt('generator','initial')
        r,_=compile_prompt('reviewer','review')
        required=['C01 Coverage','C10 Segmentation adequacy','terminal_goal_directive',
                  'previous exit','next entry']
        for phrase in required:
            self.assertIn(phrase,g)
            self.assertIn(phrase,r)

    def test_terminal_goal_directive_is_valid_basis(self):
        s='Walk toward the front door.'
        candidate={'status':'ok','subtasks':[s],'issues':[]}
        review={
          'verdict':'pass',
          'dimensions':{'fidelity':'pass','closure_handoff':'pass','segmentation_adequacy':'pass'},
          'findings':[],
          'stage_checks':[{
            'subtask_index':0,'entry_context':'The source starting context.',
            'required_history':['Walk toward the front door.'],
            'completion_condition':'The final instructed objective is to walk toward the front door; arrival is not asserted.',
            'completion_basis':'terminal_goal_directive',
            'source_quotes':['Walk toward the front door.'],
            'candidate_quotes':['Walk toward the front door.'],
            'completion_quote':'Walk toward the front door.',
            'carryover_requirements':[]
          }],
          'handoffs':[]
        }
        reviewer(s,candidate,review)

if __name__=='__main__':
    unittest.main()
