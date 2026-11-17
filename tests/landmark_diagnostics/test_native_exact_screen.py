import ast,unittest
from pathlib import Path
import numpy as np
from swept_cylinder_reference import triangle_linear_sweep_distance
SOURCE=Path(__file__).with_name('audit_native_exact_scene_traces.py')
class ExactScreenBroadphaseTests(unittest.TestCase):
 def build(self,triangles):
  tri=np.asarray(triangles,float);node=next(n for n in ast.walk(ast.parse(SOURCE.read_text())) if isinstance(n,ast.FunctionDef) and n.name=='contact');scope={'np':np,'tri':tri,'lo':tri.min(axis=1),'hi':tri.max(axis=1),'regions':{},'cache':{},'queries':0,'clears':0,'triangle_linear_sweep_distance':triangle_linear_sweep_distance};exec(compile(ast.Module(body=[node],type_ignores=[]),str(SOURCE),'exec'),scope);return scope
 def test_broadphase_matches_direct_all_triangle_scan(self):
  triangles=[[[.45,.2,-.3],[.45,1.2,.3],[.45,.2,.3]],[[1.1,.8,-.4],[1.1,1.7,.4],[1.1,.8,.4]],[[-1,-.2,-1],[2,-.2,-1],[-1,-.2,2]],[[-1,2.5,-1],[2,2.5,-1],[-1,2.5,2]],[[.2,.03,-.2],[.7,.03,-.2],[.4,.03,.2]]]
  cases=[([0,0,0],[1,0,0]),([-.8,0,0],[-.6,0,0]),([.45,0,0],[.45,0,0]),([0,0,0],[1,.6,0]),([1,.6,0],[0,0,0]),([0,1.1,0],[1,1.1,0]),([0,0,.8],[1,0,.8]),([1.2,.4,0],[.9,.4,0])];scope=self.build(triangles)
  for a,b in cases:
   a=np.array(a,float);b=np.array(b,float);expected=any(triangle_linear_sweep_distance(t,a,b)<.1-1e-6 for t in scope['tri'])
   with self.subTest(a=a.tolist(),b=b.tolist()):self.assertEqual(scope['contact'](a,b) is not None,expected)
 def test_clear_endpoints_do_not_skip_interior_collision(self):
  scope=self.build([[[.5,.2,-.3],[.5,1.2,.3],[.5,.2,.3]]]);a=np.array([0,0,0]);b=np.array([1,0,0]);self.assertIsNone(scope['contact'](a,a));self.assertIsNone(scope['contact'](b,b));self.assertIsNotNone(scope['contact'](a,b))
 def test_exact_tuple_cache_does_not_round_positions(self):
  scope=self.build([[[.5,.2,-.3],[.5,1.2,.3],[.5,.2,.3]]]);a=np.array([.400002,0,0]);b=np.array([.399998,0,0]);self.assertIsNotNone(scope['contact'](a,a));self.assertIsNone(scope['contact'](b,b));before=scope['queries'];scope['contact'](a,a);self.assertEqual(scope['queries'],before);self.assertEqual(before,2)
if __name__=='__main__':unittest.main()
