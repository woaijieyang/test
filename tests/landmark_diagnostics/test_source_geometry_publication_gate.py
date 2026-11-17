"""Synthetic artifact-binding checks, not claims about any real benchmark."""
import copy,unittest
from publication_gate import validate_geometry_report
class SourceGeometryGateTests(unittest.TestCase):
 def fixture(self):
  tasks=[{'task_key':'train:1','scene':'sceneA','source_record_sha256':'a'*64},{'task_key':'val:2','scene':'sceneB','source_record_sha256':'b'*64}]
  rows=[{**t,'status':'PASS','geometry_kind':'NATIVE_LOADER_EXPORTED_TRIANGLES','native_trace_sha256':'c'*64,'geometry_sha256':'d'*64,'actual_position_contacts':0,'continuous_linear_contacts':0,'hypothetical_step_segments':0,'actual_actions':3} for t in tasks]
  g={'status':'PASS','coverage_complete':True,'verification_mode':'exact_continuous_linear','manifest_sha256':'e'*64,'profile_sha256':'f'*64,'native_validation_sha256':'0'*64,'body':{'height':1.5,'radius':.1},'foot_epsilon_m':1e-5,'radial_epsilon_m':1e-6,'records':rows,'audit_issues':[],'unresolved':[]};return tasks,g
 def check(self,tasks,g):validate_geometry_report(g,tasks,'e'*64,'f'*64,'0'*64,6)
 def test_matching_complete_expected_task_set(self):
  t,g=self.fixture();self.check(t,g)
 def test_sampled_and_hypothetical_curves_refused(self):
  for mode in ['sampled_005m','bounded_step_realization']:
   t,g=self.fixture();g['verification_mode']=mode
   with self.subTest(mode=mode),self.assertRaises(AssertionError):self.check(t,g)
 def test_native_pass_cannot_hide_missing_or_wrong_geometry_identity(self):
  for field in ['manifest_sha256','profile_sha256','native_validation_sha256']:
   t,g=self.fixture();g[field]='1'*64
   with self.subTest(field=field),self.assertRaises(AssertionError):self.check(t,g)
 def test_partial_duplicate_and_foreign_task_sets_refused(self):
  for kind in ['missing','duplicate','foreign']:
   t,g=self.fixture()
   if kind=='missing':g['records'].pop()
   elif kind=='duplicate':g['records'][1]=copy.deepcopy(g['records'][0])
   else:g['records'][1]['task_key']='other:3'
   with self.subTest(kind=kind),self.assertRaises(AssertionError):self.check(t,g)
 def test_contacts_source_parser_and_unapproved_steps_refused(self):
  changes=[('actual_position_contacts',1),('continuous_linear_contacts',1),('hypothetical_step_segments',1),('geometry_kind','GLB_SOURCE_PARSER'),('source_record_sha256','1'*64),('native_trace_sha256','missing'),('status','FAILED'),('actual_actions',0)]
  for field,value in changes:
   t,g=self.fixture();g['records'][0][field]=value
   with self.subTest(field=field),self.assertRaises(AssertionError):self.check(t,g)
 def test_missing_review_fields_refused(self):
  for field in ['audit_issues','unresolved']:
   t,g=self.fixture();del g[field]
   with self.subTest(field=field),self.assertRaises(AssertionError):self.check(t,g)
 def test_body_and_tolerances_cannot_be_relaxed(self):
  for kind in ['height','radius','foot_epsilon_m','radial_epsilon_m']:
   t,g=self.fixture()
   if kind=='height':g['body']['height']=1.4
   elif kind=='radius':g['body']['radius']=.09
   else:g[kind]=.01
   with self.subTest(kind=kind),self.assertRaises(AssertionError):self.check(t,g)
if __name__=='__main__':unittest.main()
