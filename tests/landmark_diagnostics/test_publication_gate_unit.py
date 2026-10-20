"""Portable publication-gate unit fixtures; historical real-run tests remain explicit audits."""
import copy,json,unittest,tempfile
from pathlib import Path
from publication_gate import validate_report,require_acceptance
class PublicationGateUnitTests(unittest.TestCase):
 def base(self):
  return {'status':'PASS','coverage_complete':True,'counts':{'PASS':33954,'actual_actions':1},'audit_issues':[],'failure_kinds':{},'max_independent_replay_error':0,'split_counts':{'train':{'PASS':26464},'val_seen':{'PASS':2939},'val_unseen':{'PASS':4551}}}
 def test_complete_synthetic_schema(self):validate_report(self.base())
 def test_pass_label_cannot_hide_blocked_records(self):
  value=self.base();value['counts']={'PASS':30498,'STATIC_BLOCKED_PRESERVED':3456,'actual_actions':1}
  with self.assertRaises(AssertionError):validate_report(value)
 def test_invalid_coverage_motion_and_replay(self):
  cases=[]
  for key,value in [('status','COMPLETE_NOT_ACCEPTED'),('coverage_complete',False),('audit_issues',[{'kind':'replay'}]),('failure_kinds',{'offmesh':1}),('max_independent_replay_error',float('nan')),('max_independent_replay_error',.001)]:
   v=self.base();v[key]=value;cases.append(v)
  for kind in ['STATIC_BLOCKED_PRESERVED','zero_actions','wrong_split']:
   v=self.base()
   if kind=='STATIC_BLOCKED_PRESERVED':v['counts'][kind]=1
   elif kind=='zero_actions':v['counts']['actual_actions']=0
   else:v['split_counts']['train']['PASS']-=1
   cases.append(v)
  for i,v in enumerate(cases):
   with self.subTest(case=i),self.assertRaises(AssertionError):validate_report(v)
 def test_unaccepted_receipt_refused_without_historical_outputs(self):
  parent=Path.cwd()/'.cache/publication-unit-fixtures';parent.mkdir(parents=True,exist_ok=True)
  with tempfile.TemporaryDirectory(prefix='fixture-',dir=parent) as tmp:
   root=Path(tmp);assert root.resolve().is_relative_to(parent.resolve());p=root/'outputs/landmark-connectivity/acceptance.json';p.parent.mkdir(parents=True);p.write_text('{"status":"NOT_ACCEPTED"}')
   with self.assertRaisesRegex(AssertionError,'not accepted'):require_acceptance(root)
if __name__=='__main__':unittest.main()
