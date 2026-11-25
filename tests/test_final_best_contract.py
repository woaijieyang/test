from host.template_selector import library, source, PROFILES, select_examples
from test_runtime_contract_v2 import SOURCE, generator_candidate, reviewer_output
import copy, json, unittest
from adapter.source import from_record, Source
from host.compile import compile_prompt, core_library
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
        # A capability may be taught by mandatory Core after source promotion.
        # Do not require an unrelated Dynamic destination to be weakened merely
        # to keep that capability represented in the optional pool.
        teaching=core_library('generator','r2r-en')+library('generator','r2r-en')
        rows=[r for r in teaching if r['output']['stage_audit'] and
              r['output']['stage_audit'][-1]['ending']['kind']=='terminal_goal_directive']
        self.assertTrue(rows)
        for row in rows:
            with self.subTest(template=row['template_id']):
                protocol.generator(source(row),row['output'])
                for stage in row['output']['stage_audit'][:-1]:
                    self.assertNotEqual(stage['ending']['kind'],'terminal_goal_directive')
                ending=row['output']['stage_audit'][-1]['ending']
                self.assertEqual(ending['stop_scope'],'none')
                self.assertTrue(ending['candidate_quotes'])

    def test_final_approach_permission_cannot_close_an_intermediate_stage(self):
        from host import protocol
        row=next(r for r in core_library('generator','r2r-en')
                 if r['template_id']=='R2R-CORE-G02')
        bad=copy.deepcopy(row['output'])
        bad['stage_audit'][0]['ending']['kind']='terminal_goal_directive'
        with self.assertRaises(ContractError):protocol.generator(source(row),bad)

    def test_named_source_destination_without_stop_stays_an_event(self):
        from host import protocol
        bank={r['template_id']:r for r in library('generator','r2r-en')}
        for tid in ('R2R-GEN-022','R2R-GEN-028','R2R-GEN-032'):
            row=bank[tid]
            with self.subTest(template=tid):
                self.assertEqual(row['output']['stage_audit'][-1]['ending']['kind'],'explicit_event')
                self.assertEqual(row['output']['stage_audit'][-1]['ending']['stop_scope'],'none')
                protocol.generator(source(row),row['output'])

if __name__=='__main__':
    unittest.main()
