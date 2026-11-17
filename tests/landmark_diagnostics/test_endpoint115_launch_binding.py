"""Reject nominal-version names when actual controller worker binding is wrong."""
import ast,hashlib,json,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[2];P=Path(__file__).parent

def worker_binding(path):
 assignments=[n for n in ast.walk(ast.parse(path.read_text())) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='worker' for t in n.targets)]
 if len(assignments)!=1:raise ValueError('Ambiguous worker binding')
 n=assignments[0].value
 if not (isinstance(n,ast.BinOp) and isinstance(n.left,ast.Name) and n.left.id=='R' and isinstance(n.op,ast.Div) and isinstance(n.right,ast.Constant)):raise ValueError('Unsupported worker binding')
 return R/n.right.value

def require_intended(path):
 actual=worker_binding(path);expected=P/'endpoint115_motion_worker_v2.py'
 if actual!=expected:raise ValueError('Wrong worker')
 return hashlib.sha256(actual.read_bytes()).hexdigest()

class WorkerBinding(unittest.TestCase):
 def test_reject_recorded_wrong_v2(self):
  with self.assertRaisesRegex(ValueError,'Wrong worker'):require_intended(P/'run_endpoint115_full_validation_v2.py')
 def test_corrected_v3_matches_actual_native_regression(self):
  receipt=json.loads((R/'outputs/connectivity/endpoint115-horizontal-planner-regression-v1/validation.json').read_text())
  self.assertEqual(require_intended(P/'run_endpoint115_full_validation_v3.py'),receipt['worker_v2_sha256'])
 def test_actual_manifest_matches_intention(self):
  m=json.loads((R/'outputs/connectivity/endpoint115-full-motion-v3/manifest.json').read_text());worker=worker_binding(P/'run_endpoint115_full_validation_v3.py');self.assertEqual(m['sources'][str(worker)],require_intended(P/'run_endpoint115_full_validation_v3.py'));self.assertNotIn(str(P/'endpoint115_motion_worker.py'),m['sources'])
if __name__=='__main__':unittest.main()
