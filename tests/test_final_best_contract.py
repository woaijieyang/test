from host.template_selector import library, source, PROFILES, select_examples
from test_runtime_contract_v2 import SOURCE, generator_candidate, reviewer_output
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
        from host.compile import ROOT
        contract=(ROOT/'shared/semantic_contract.md').read_text(encoding='utf8')
        for role,phase in [('generator','initial'),('reviewer','review')]:
            prompt,_=compile_prompt(role,phase,profile='r2r-en')
            self.assertIn(contract,prompt)

    def test_terminal_goal_directive_is_valid_basis(self):
        from host import protocol
        rows=[r for r in library('generator','r2r-en') if r['output']['stage_audit'] and r['output']['stage_audit'][-1]['ending']['kind']=='terminal_goal_directive']
        self.assertTrue(rows)
        for r in rows:protocol.generator(source(r),r['output'])

if __name__=='__main__':
    unittest.main()
