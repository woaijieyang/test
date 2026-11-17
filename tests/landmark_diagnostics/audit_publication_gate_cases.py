"""Synthetic unit cases for publication refusal, plus current real-run refusal."""
import copy,json,unittest
from pathlib import Path
from publication_gate import validate_report,require_acceptance

class PublicationGateTests(unittest.TestCase):
 def base(self):
  # Synthetic schema fixture, never written as an evaluation result.
  return {'status':'PASS','coverage_complete':True,'counts':{'PASS':33954,'actual_actions':1},'audit_issues':[],'failure_kinds':{},'max_independent_replay_error':0,'split_counts':{'train':{'PASS':26464},'val_seen':{'PASS':2939},'val_unseen':{'PASS':4551}}}
 def test_valid_report_schema(self):validate_report(self.base())
 def test_blocked_not_hidden_by_pass_label(self):
  v=json.loads(Path('outputs/landmark-connectivity/full-native-v8/validation.json').read_text());v['status']='PASS'
  with self.assertRaises(AssertionError):validate_report(v)
 def test_bad_report_cases(self):
  cases=[]
  for key,value in [('status','COMPLETE_NOT_ACCEPTED'),('coverage_complete',False),('audit_issues',[{'kind':'replay'}]),('failure_kinds',{'offmesh':1}),('max_independent_replay_error',float('nan')),('max_independent_replay_error',.001)]:
   v=self.base();v[key]=value;cases.append(v)
  v=self.base();v['counts']['STATIC_BLOCKED_PRESERVED']=1;cases.append(v)
  v=self.base();v['counts']['actual_actions']=0;cases.append(v)
  v=self.base();v['split_counts']['train']['PASS']-=1;cases.append(v)
  for i,v in enumerate(cases):
   with self.subTest(case=i),self.assertRaises(AssertionError):validate_report(v)
 def test_current_real_acceptance_refused(self):
  with self.assertRaisesRegex(AssertionError,'not accepted'):require_acceptance(Path.cwd())

if __name__=='__main__':unittest.main()
