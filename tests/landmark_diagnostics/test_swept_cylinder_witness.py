import copy,math,random,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from swept_cylinder_witness import linear_sweep_witness,verify_witness
from swept_cylinder_reference import triangle_linear_sweep_distance

class WitnessTests(unittest.TestCase):
    def compare(self,triangle,a,b,collision=None):
        witness=linear_sweep_witness(triangle,a,b)
        reference=triangle_linear_sweep_distance(triangle,a,b)
        if witness is None:
            self.assertTrue(math.isinf(reference))
            if collision is not None:self.assertFalse(collision)
            return
        self.assertLessEqual(abs(witness['distance']-reference),1e-10)
        hit=verify_witness(triangle,a,b,witness)
        if collision is not None:self.assertEqual(hit,collision)
        return witness

    def test_between_endpoint_contact(self):
        triangle=[[0,0,-1],[0,2,-1],[0,0,1]];a=[-.5,0,0];b=[.5,0,0]
        self.assertGreater(triangle_linear_sweep_distance(triangle,a,a),.1)
        self.assertGreater(triangle_linear_sweep_distance(triangle,b,b),.1)
        self.compare(triangle,a,b,True)

    def test_far_side(self):
        self.compare([[2,0,-1],[2,2,-1],[2,0,1]],[-.5,0,0],[.5,0,0],False)

    def test_above_and_below_slab(self):
        for y in [-1,2]:
            with self.subTest(y=y):self.compare([[0,y,0],[1,y,0],[0,y,1]],[0,0,0],[.2,0,0],False)

    def test_stationary_and_vertical_motion(self):
        triangle=[[.05,.7,-1],[.05,.7,1],[.05,2,0]]
        self.compare(triangle,[0,0,0],[0,0,0],True)
        self.compare(triangle,[0,0,0],[0,1,0],True)

    def test_degenerate_line_and_point(self):
        self.compare([[.05,.3,0],[.05,.8,0],[.05,.3,0]],[0,0,0],[0,0,0],True)
        self.compare([[.05,.3,0]]*3,[0,0,0],[0,0,0],True)

    def test_large_coordinates(self):
        self.compare([[100000.05,.3,0],[100000.05,.8,1],[100000.05,.8,-1]],[100000,0,0],[100000,0,.2],True)

    def test_nonfinite_and_invalid_slab(self):
        with self.assertRaises(ValueError):linear_sweep_witness([[math.nan,0,0]]*3,[0,0,0],[1,0,0])
        with self.assertRaises(ValueError):linear_sweep_witness([[0,0,0]]*3,[0,0,0],[1,0,0],height=0)

    def test_certificate_tampering(self):
        tri=[[.05,.3,0]]*3;a=[0,0,0];b=[0,0,0];w=self.compare(tri,a,b,True)
        for field,value in [('time',.7),('relative_height',1.4),('exact_time',[2,1]),('exact_distance_squared',[0,1])]:
            bad=copy.deepcopy(w);bad[field]=value
            with self.subTest(field=field),self.assertRaises(AssertionError):verify_witness(tri,a,b,bad)

    def test_deterministic_random_crosscheck(self):
        rng=random.Random(20261017)
        for index in range(100):
            tri=[[rng.uniform(-2,2) for _ in range(3)] for _ in range(3)]
            a=[rng.uniform(-1,1) for _ in range(3)];b=[rng.uniform(-1,1) for _ in range(3)]
            with self.subTest(index=index):self.compare(tri,a,b)

if __name__=='__main__':unittest.main()

