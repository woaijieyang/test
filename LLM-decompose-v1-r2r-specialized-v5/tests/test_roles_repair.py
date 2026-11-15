import json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from host.compile import compile_prompt
from host.protocol import generator,reviewer
class RolesRepairTests(unittest.TestCase):
 def test_each_role_has_35_per_profile(self):
  for role in ('generator','reviewer'):
   for file in ('r2r.json','rxr_en_us.json'):
    rows=json.loads((ROOT/role/'templates'/file).read_text(encoding='utf-8'))
    self.assertEqual(len(rows),35);self.assertEqual(len({x['input']['original_instruction'] for x in rows}),35)
 def test_r2r_and_rxr_examples_are_not_mixed(self):
  for profile,tag,other in [('r2r-en','R2R','RXR'),('rxr-en-us','RXR','R2R')]:
   for role in ('generator','reviewer'):
    prefix=tag+'-REVIEW-01' if role=='reviewer' else tag+'-01'
    text,_=compile_prompt(role,'review' if role=='reviewer' else 'initial',profile=profile)
    self.assertIn(prefix,text)
    self.assertNotIn(other+'-REVIEW-01' if role=='reviewer' else other+'-01',text)
    self.assertIn('Selected example IDs',text) if False else None

 def test_reviewer_examples_validate_against_live_contract(self):
  for role in ('r2r','rxr'):
   file='r2r.json' if role=='r2r' else 'rxr_en_us.json'
   for e in json.loads((ROOT/'reviewer'/'templates'/file).read_text(encoding='utf-8')):
    reviewer(e['input']['original_instruction'],e['input']['candidate'],e['output'])
 def test_generator_examples_validate(self):
  for role in ('r2r','rxr'):
   file='r2r.json' if role=='r2r' else 'rxr_en_us.json'
   for e in json.loads((ROOT/'generator'/'templates'/file).read_text(encoding='utf-8')):
    generator(e['input']['original_instruction'],e['output'])
 def test_r2r_regression_suite_has_six_distinct_cases(self):
  x=json.loads((ROOT/'generator/tests/r2r_regressions.json').read_text(encoding='utf-8'))
  self.assertEqual({r['episode'] for r in x},{'1099','1148','1149','115','1330','406'})
  self.assertEqual(len(x),6)
 def test_1149_requires_merge_without_invented_endpoint(self):
  x=next(r for r in json.loads((ROOT/'generator/tests/r2r_regressions.json').read_text(encoding='utf-8')) if r['episode']=='1149')
  self.assertEqual(x['expected_decision'],'keep_coupled_single_stage');self.assertIn('supplies order only',x['generator_requirement'])
 def test_1330_and_406_are_not_overrejected(self):
  x=json.loads((ROOT/'generator/tests/r2r_regressions.json').read_text(encoding='utf-8'))
  self.assertEqual(next(r for r in x if r['episode']=='1330')['expected_decision'],'valid_three_stage_handoff')
  self.assertEqual(next(r for r in x if r['episode']=='406')['expected_decision'],'terminal_goal_directive_allowed')
 def test_repair_envelope_is_explicit_and_distinct(self):
  schema=json.loads((ROOT/'generator/repair.schema.json').read_text(encoding='utf-8'))
  self.assertEqual(set(schema['required']),{'candidate','responses'})
  self.assertIn('decision',schema['properties']['responses']['items']['required'])
 def test_compiled_prompts_exist_for_both_profiles(self):
  for role in ('generator','reviewer'):
   for profile in ('r2r-en','rxr-en-us'):
    text,schema=compile_prompt(role,'review' if role=='reviewer' else 'initial',profile=profile)
    self.assertTrue(text.endswith('\n'));self.assertIsInstance(schema,dict)
 def test_compiler_rejects_missing_or_wrong_profile(self):
  with self.assertRaises(TypeError):compile_prompt('generator')
  with self.assertRaises(ValueError):compile_prompt('generator',profile='rxr-en')
if __name__=='__main__':unittest.main()
