import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from build_endpoint115_derivative import apply_fields
class FieldChanges(unittest.TestCase):
 def test_exact_patch_preserves_input(self):
  before={'position':[1.,2.,3.],'nested':{'id':7}};original=copy.deepcopy(before);changes=[{'field':'/position/1','before':2.,'after':2.1}];after=apply_fields(before,changes);self.assertEqual(before,original);self.assertEqual(after,{'position':[1.,2.1,3.],'nested':{'id':7}})
 def test_stale_value_rejected(self):
  with self.assertRaises(ValueError):apply_fields({'x':[2.]},[{'field':'/x/0','before':1.,'after':3.}])
 def test_duplicate_rejected(self):
  with self.assertRaises(ValueError):apply_fields({'x':[1.]},[{'field':'/x/0','before':1.,'after':2.},{'field':'/x/0','before':2.,'after':3.}])
 def test_missing_field_rejected(self):
  with self.assertRaises(KeyError):apply_fields({'x':[1.]},[{'field':'/other/0','before':1.,'after':2.}])
 def test_extra_edit_not_equal_to_expected(self):
  with self.assertRaises(ValueError):apply_fields({'x':[1.]},[{'field':'/x/0','before':1.,'after':1.}])
if __name__=='__main__':unittest.main()
