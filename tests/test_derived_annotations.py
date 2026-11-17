import unittest,sys,copy,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from build_derived_annotations import diff
class AnnotationDifferences(unittest.TestCase):
 def test_original_nan_timestamps_are_not_false_changes(self):
  before={'instruction':{'start_time':float('nan')},'position':[1.,2.,3.]}
  self.assertEqual(diff(before,copy.deepcopy(before)),[])
 def test_coordinate_changes_have_exact_field_paths(self):
  self.assertEqual(diff({'position':[1.,2.,3.]},{'position':[1.,2.,4.]}),[{'field':'/position/2','before':3.,'after':4.}])
 def test_deleting_unrelated_fields_is_rejected(self):
  with self.assertRaises(ValueError):diff({'id':1},{})
 def test_task_removal_is_rejected(self):
  with self.assertRaises(ValueError):diff([1,2],[1])
