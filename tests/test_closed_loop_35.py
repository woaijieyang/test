import unittest,json,copy,hashlib
from pathlib import Path
from adapter.source import Source
from host import protocol
from host.template_selector import select_examples,library
from host.compile import compile_prompt
from host.run import run_record
from shared.identity import ContractError
ROOT=Path(__file__).resolve().parents[1]
def g(dataset):return json.loads((ROOT/'generator/templates'/dataset).read_text(encoding='utf-8'))
def r(dataset):return json.loads((ROOT/'reviewer/templates'/dataset).read_text(encoding='utf-8'))
class CompleteContractTests(unittest.TestCase):
 def test_01_exactly_140_role_entries(self):
  rows=[(role,ds,len(json.loads((ROOT/role/'templates'/ds).read_text(encoding='utf-8')))) for role in ('generator','reviewer') for ds in ('r2r.json','rxr_en_us.json')]
  self.assertEqual([x[2] for x in rows],[35,35,35,35]);self.assertEqual(sum(x[2] for x in rows),140)
 def test_02_70_distinct_training_sources_with_sha(self):
  for ds in ('r2r.json','rxr_en_us.json'):
   gs=g(ds);rs=r(ds);self.assertEqual(len({x['input']['original_instruction'] for x in gs}),35)
   for gg,rr in zip(gs,rs):
    self.assertEqual(gg['input']['original_instruction'],rr['input']['original_instruction'])
    self.assertEqual(gg['provenance']['split'],'train')
    self.assertEqual(rr['provenance']['source_sha256'],gg['provenance']['source_sha256'])
    self.assertEqual(hashlib.sha256(gg['input']['original_instruction'].encode()).hexdigest(),gg['provenance']['source_sha256'])
 def test_03_every_generator_audit_and_handoff_validated(self):
  for ds in ('r2r.json','rxr_en_us.json'):
   for e in g(ds):
    protocol.generator(e['input']['original_instruction'],e['output'])
    self.assertEqual(len(e['output']['stage_audit']),len(e['output']['subtasks']))
    self.assertEqual(len(e['output']['handoffs']),max(0,len(e['output']['subtasks'])-1))
 def test_04_every_reviewer_example_validated(self):
  for ds in ('r2r.json','rxr_en_us.json'):
   for e in r(ds):protocol.reviewer(e['input']['original_instruction'],e['input']['candidate'],e['output'])
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
 def test_10_source_selection_default_eight_deterministic(self):
  for profile in ('r2r-en','rxr-en-us'):
   for role in ('generator','reviewer'):
    text='Walk past the first door then turn left after the stairs and stop.'
    a=select_examples(role,profile,text);b=select_examples(role,profile,text)
    self.assertEqual(a,b);self.assertEqual(len(a),8);self.assertEqual(len(a),len(set(a)))
 def test_11_exact_source_not_echoed_as_template(self):
  for profile,ds in [('r2r-en','r2r.json'),('rxr-en-us','rxr_en_us.json')]:
   source=g(ds)[20]['input']['original_instruction']
   for role in ('generator','reviewer'):
    chosen=select_examples(role,profile,source)
    byid={x['example_id']:x for x in library(role,profile)}
    self.assertNotIn(source,[byid[x]['input']['original_instruction'] for x in chosen])
 def test_12_all_mode_explicitly_35(self):
  for profile in ('r2r-en','rxr-en-us'):
   for role in ('generator','reviewer'):
    self.assertEqual(len(select_examples(role,profile,'',mode='all')),35)
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
  ex=g('r2r.json')[20];rev=r('r2r.json')[20]
  src=Source('smoke','R2R','en',ex['input']['original_instruction'])
  requests=[]
  def model(req):
   requests.append(req)
   out=ex['output'] if req['role']=='generator' else rev['output']
   return {'output':copy.deepcopy(out),'receipt':{'model':req['model'],'effort':req['effort'],'request_id':f'fixture-{len(requests)}'}}
  out=run_record(src,model,pins={'generator':{'model':'TEST','effort':'low'},'reviewer':{'model':'TEST','effort':'low'}})
  self.assertTrue(out['disposition'].startswith('accepted'),out.get('error'))
  self.assertEqual([len(x['selected_example_ids']) for x in requests],[8,8])
  self.assertNotIn('stage_audit',requests[1]['messages'][1]['content'])
  self.assertEqual(out['example_selection']['generator'],requests[0]['selected_example_ids'])
  self.assertEqual(out['example_selection']['reviewer'],requests[1]['selected_example_ids'])
 def test_16_repair_demo_schema_and_dispositions(self):
  for x in json.loads((ROOT/'generator/repair_examples.json').read_text(encoding='utf-8')):
   protocol.reviewer(x['input']['original_instruction'],x['input']['candidate'],x['input']['review'])
   protocol.feedback(x['input']['original_instruction'],x['input']['review'],x['output'])
 def test_17_regressions_not_used_as_fewshot(self):
  forbidden={'1099','1148','1149','115','1330','406'}
  for role in ('generator','reviewer'):
   ids={x['provenance']['id'] for x in json.loads((ROOT/role/'templates/r2r.json').read_text(encoding='utf-8'))}
   self.assertFalse(ids & forbidden, ids&forbidden)
if __name__=='__main__':unittest.main()
