from host.template_selector import library, source, PROFILES, select_examples
from test_runtime_contract_v2 import SOURCE, generator_candidate, reviewer_output
from host import protocol
import json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from host.compile import compile_prompt, runtime_review_output
from host.protocol import generator,reviewer
class RolesRepairTests(unittest.TestCase):
 def test_role_specific_profile_counts(self):
     for profile, expected in [('r2r-en',(25,55)),('rxr-en-us',(35,64))]:
         for role,n in zip(('generator','reviewer'),expected):
             rows=library(role,profile)
             self.assertEqual(len(rows),n)
             self.assertEqual(len({r['template_id'] for r in rows}),n)
     from host.compile import core_library
     self.assertEqual(len(core_library('generator','rxr-en-us')),10)
     self.assertEqual(len(core_library('reviewer','rxr-en-us')),10)
 def test_r2r_and_rxr_examples_are_not_mixed(self):
     for profile,ds in PROFILES.items():
         for role in ('generator','reviewer'):
             ids=select_examples(role,profile,SOURCE)
             self.assertTrue(all(i.startswith(ds+'-') for i in ids))
             prompt,_=compile_prompt(role,'initial' if role=='generator' else 'review',profile=profile,selected_ids=ids)
             self.assertTrue(all(i in prompt for i in ids))

 def test_teaching_examples_against_teaching_contract(self):
     from jsonschema import Draft202012Validator
     from referencing import Registry,Resource
     schemas={f.name:json.loads(f.read_bytes()) for f in (ROOT/'shared/template_schemas_v1_5_2').glob('*.json')}
     registry=Registry().with_resources((name,Resource.from_contents(data)) for name,data in schemas.items())
     for role in ('generator','reviewer'):
         validator=Draft202012Validator(schemas[role+'_template.schema.json'],registry=registry)
         for profile in PROFILES:
             for row in library(role,profile):
                 validator.validate(row)
             from host.compile import core_library
             for row in core_library(role,profile):
                 validator.validate(row)
 def test_generator_examples_validate(self):
     for profile in PROFILES:
         for row in library('generator',profile):
             protocol.generator(source(row),row['output'])
         from host.compile import core_library
         for row in core_library('generator',profile):
             protocol.generator(source(row),row['output'])
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
 def test_reviewer_evidence_projection_rejects_ambiguous_stage_mapping(self):
     example = {
         "expected_review": {
             "verdict": "revise",
             "source_coverage": [{
                 "requirement_id": "SRC-1",
                 "candidate_evidence": ["Turn right"]
             }],
             "findings": [], "prior_finding_reviews": [],
             "layer_checks": []
         },
         "review_input": {
             "candidate": {
                 "subtasks": ["Turn right and continue.", "Turn right and stop."]
             }
         }
     }
     with self.assertRaisesRegex(ValueError, "Ambiguous Reviewer teaching evidence"):
         runtime_review_output(example)

 def test_reviewer_evidence_projection_accepts_unique_and_explicit_stage(self):
     example = {
         "expected_review": {
             "verdict": "revise",
             "source_coverage": [{
                 "requirement_id": "SRC-1",
                 "candidate_evidence": ["Turn left"]
             }],
             "findings": [{
                 "candidate_evidence": [{"subtask_index": 1, "quote": "Turn right"}]
             }],
             "prior_finding_reviews": [], "layer_checks": []
         },
         "review_input": {
             "candidate": {"subtasks": ["Turn left and continue.", "Turn right and stop."]}
         }
     }
     audit = runtime_review_output(example)
     self.assertEqual(audit["source_coverage"][0]["candidate_evidence"],
                      [{"subtask_index": 0, "quote": "Turn left"}])
     self.assertEqual(audit["findings"][0]["candidate_evidence"],
                      [{"subtask_index": 1, "quote": "Turn right"}])

if __name__=='__main__':unittest.main()
