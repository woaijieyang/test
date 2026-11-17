import unittest
from scene_evidence_comparison import compare,CLEAR
FAIL='SOURCE_FAILURE_PRESERVED'
class SceneEvidenceComparisonTests(unittest.TestCase):
 def rows(self,passed):return [{'task_key':k,'status':CLEAR if k in passed else FAIL} for k in 'abcd']
 def test_more_passes_do_not_hide_regression(self):
  r=compare('abcd',{'old':{'a','b'}},self.rows({'b','c','d'}));self.assertEqual(r['candidate_strict_passed'],3);self.assertFalse(r['all_baselines_preserved']);self.assertEqual(r['comparisons']['old']['regressed'],['a'])
 def test_complete_strict_with_preserved_baselines(self):
  r=compare('abcd',{'original':{'a'},'derived':{'a','b'}},self.rows(set('abcd')));self.assertTrue(r['all_baselines_preserved']);self.assertTrue(r['all_tasks_strict'])
 def test_partial_is_not_complete(self):
  r=compare('abcd',{'old':{'a'}},self.rows({'a','b'}));self.assertTrue(r['all_baselines_preserved']);self.assertFalse(r['all_tasks_strict']);self.assertEqual(r['candidate_unresolved'],['c','d'])
 def test_missing_and_foreign_identity_rejected(self):
  for rows in [self.rows({'a'})[:-1],self.rows({'a'})+[{'task_key':'x','status':CLEAR}]]:
   with self.subTest(rows=len(rows)),self.assertRaises(ValueError):compare('abcd',{},rows)
 def test_duplicate_identity_rejected(self):
  with self.assertRaises(ValueError):compare('abcd',{},[self.rows({'a'})[0]]*4)
  with self.assertRaises(ValueError):compare('aabc',{},self.rows({'a'}))
 def test_weaker_or_unknown_proof_rejected(self):
  for status in ['PASS','PASS_DIAGNOSTIC','SAMPLED_SOURCE_CLEAR','INFRASTRUCTURE_FAILURE']:
   rows=self.rows({'a'});rows[0]['status']=status
   with self.subTest(status=status),self.assertRaises(ValueError):compare('abcd',{},rows)
 def test_step_hypothesis_stays_unresolved(self):
  rows=self.rows({'a'});rows[1]['status']='STEP_REALIZATION_EXISTS_PROTOCOL_REVIEW_REQUIRED';r=compare('abcd',{},rows);self.assertEqual(r['candidate_strict_passed'],1)
 def test_foreign_baseline_rejected(self):
  with self.assertRaises(ValueError):compare('abcd',{'old':{'x'}},self.rows({'a'}))
if __name__=='__main__':unittest.main()
