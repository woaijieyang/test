from host.template_selector import library, source, PROFILES, select_examples
from test_runtime_contract_v2 import SOURCE, generator_candidate, reviewer_output
import unittest,json,copy,hashlib
from pathlib import Path
from adapter.source import Source
from host import protocol
from host.template_selector import select_examples,library
from host.compile import compile_prompt
from host.run import run_record
from shared.identity import ContractError
ROOT=Path(__file__).resolve().parents[1]
def g(dataset):return library('generator','r2r-en' if dataset=='r2r.json' else 'rxr-en-us')
class CompleteContractTests(unittest.TestCase):
 def test_01_curated_libraries_by_role_and_profile(self):
     for profile, expected in [('r2r-en',(35,61)),('rxr-en-us',(45,74))]:
         for role,n in zip(('generator','reviewer'),expected):
             rows=library(role,profile)
             self.assertEqual(len(rows),n)
             self.assertEqual(len({r['template_id'] for r in rows}),n)
 def test_02_paired_sources_preserve_identity(self):
     for profile in PROFILES:
         gs={r['template_id']:r for r in library('generator',profile)}
         paired=[r for r in library('reviewer',profile) if r.get('pair_id')]
         self.assertEqual(len(paired),len(gs))
         for r in paired:
             self.assertEqual(source(r),source(gs[r['pair_id']]))
 def test_03_every_generator_audit_and_handoff_validated(self):
  for ds in ('r2r.json','rxr_en_us.json'):
   for e in g(ds):
    protocol.generator(e['input']['original_instruction'],e['output'])
    self.assertEqual(len(e['output']['stage_audit']),len(e['output']['subtasks']))
    self.assertEqual(len(e['output']['handoffs']),max(0,len(e['output']['subtasks'])-1))
 def test_04_uploaded_examples_match_teaching_schemas(self):
     from jsonschema import Draft202012Validator
     from referencing import Registry,Resource
     schemas={f.name:json.loads(f.read_bytes()) for f in (ROOT/'shared/template_schemas_v1_5_2').glob('*.json')}
     registry=Registry().with_resources((name,Resource.from_contents(data)) for name,data in schemas.items())
     for role in ('generator','reviewer'):
         validator=Draft202012Validator(schemas[role+'_template.schema.json'],registry=registry)
         for profile in PROFILES:
             for row in library(role,profile):
                 validator.validate(row)
 def test_05_generator_cannot_omit_audit(self):
  e=g('r2r.json')[20];o=copy.deepcopy(e['output']);o.pop('stage_audit')
  with self.assertRaises(ContractError):protocol.generator(e['input']['original_instruction'],o)
 def test_06_generator_cannot_omit_handoff(self):
  e=next(x for x in g('r2r.json')[20:] if len(x['output']['handoffs'])>0)
  o=copy.deepcopy(e['output']);o['handoffs']=[]
  with self.assertRaises(ContractError):protocol.generator(e['input']['original_instruction'],o)
 def test_07_generator_cannot_invent_source_quote(self):
  e=g('r2r.json')[20];o=copy.deepcopy(e['output']);o['stage_audit'][0]['source_quotes']=['This room is on the moon.']
  with self.assertRaises(ContractError):protocol.generator(e['input']['original_instruction'],o)
 def test_08_generator_cannot_use_summary_only_process(self):
  e=g('r2r.json')[20];o=copy.deepcopy(e['output']);o['stage_audit'][0]['process']['candidate_quotes']=['This sentence is absent from executable stage.']
  with self.assertRaises(ContractError):protocol.generator(e['input']['original_instruction'],o)
 def test_09_intermediate_terminal_approach_not_allowed(self):
  e=next(x for x in g('rxr_en_us.json')[20:] if len(x['output']['subtasks'])>1)
  o=copy.deepcopy(e['output']);o['stage_audit'][0]['ending']['kind']='terminal_goal_directive'
  o['stage_audit'][0]['ending']['text']='Final direction; arrival/STOP not specified.'
  with self.assertRaises(ContractError):protocol.generator(e['input']['original_instruction'],o)
 def test_10_adaptive_selection_is_deterministic(self):
     for profile in PROFILES:
         for role in ('generator','reviewer'):
             a=select_examples(role,profile,SOURCE)
             self.assertEqual(a,select_examples(role,profile,SOURCE))
             self.assertTrue((6 <= len(a) <= 8) if role == "generator" else (8 <= len(a) <= 12))
             self.assertEqual(len(a),len(set(a)))
 def test_11_exact_source_not_echoed_as_template(self):
     for profile in PROFILES:
         for role in ('generator','reviewer'):
             rows=library(role,profile)
             text=source(rows[0]);selected=select_examples(role,profile,text)
             self.assertNotIn(text,[source(r) for r in rows if r['template_id'] in selected])
 def test_12_all_mode_selects_entire_profile(self):
     for profile in PROFILES:
         for role in ('generator','reviewer'):
             self.assertEqual(select_examples(role,profile,'',mode='all'),[r['template_id'] for r in library(role,profile)])
 def test_13_same_canonical_contract_both_roles(self):
  std=(ROOT/'shared/semantic_contract.md').read_text(encoding='utf-8');self.assertEqual((ROOT/'generator/acceptance.md').read_text(encoding='utf-8'),std)
  for role,phase in [('generator','initial'),('reviewer','review'),('generator','repair')]:
   p,_=compile_prompt(role,phase,profile='r2r-en',examples=False)
   self.assertIn(std,p)
 def test_14_repair_has_correct_envelope_teaching(self):
  p,s=compile_prompt('generator','repair',profile='r2r-en',original_instruction='go through second doorway')
  self.assertIn('TWO REPAIR-ENVELOPE EXAMPLES',p)
  self.assertIn('ACTIVE OUTPUT SCHEMA',p)
  self.assertEqual(set(s['required']),{'candidate','responses'})
 def test_15_reviewer_does_not_receive_generator_audit(self):
     g0=generator_candidate(True); rv=reviewer_output(g0,repaired=True)
     requests=[]
     def replay(req):
         requests.append(req)
         return {'output':g0 if req['role']=='generator' else rv,'receipt':{'model':'fixture','effort':'low','request_id':str(len(requests))}}
     out=run_record(Source('smoke','R2R','en',SOURCE),replay,pins={r:{'model':'fixture','effort':'low'} for r in ('generator','reviewer')})
     self.assertEqual(out['disposition'],'accepted_candidate')
     self.assertNotIn('stage_audit',requests[1]['messages'][1]['content'])
     for req in requests:self.assertEqual(req['selected_example_ids'],out['example_selection'][req['role']])
 def test_16_repair_demo_schema_and_dispositions(self):
  for x in json.loads((ROOT/'generator/repair_examples.json').read_text(encoding='utf-8')):
   protocol.reviewer(x['input']['original_instruction'],x['input']['candidate'],x['input']['review'])
   protocol.feedback(x['input']['original_instruction'],x['input']['review'],x['output'])
 def test_17_regressions_not_used_as_fewshot(self):
     for role in ('generator','reviewer'):
         for row in library(role,'r2r-en'):
             self.assertNotEqual(row['source']['split'],'val_unseen')
if __name__=='__main__':unittest.main()
