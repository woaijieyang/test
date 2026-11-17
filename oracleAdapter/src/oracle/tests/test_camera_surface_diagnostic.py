import unittest
import json
import sys
from pathlib import Path
import numpy as np
from oracle.verification.camera_surface_diagnostic import inspect_query, rational_camera_distance,verify_historical_helpers


class CameraSurfaceDiagnostic(unittest.TestCase):
    def test_checked_in_fingerprints_match_frozen_parser_or_fail_explicitly(self):
        cfg=json.loads((Path(__file__).resolve().parents[1]/'configs/experiments/camera_surface_rejections_v1.json').read_text())
        if list(sys.version_info[:2])==cfg['historical_ast_python']:
            verify_historical_helpers(cfg)
        else:
            with self.assertRaisesRegex(ValueError,'frozen Python version'):verify_historical_helpers(cfg)

    class PathFinder:
        def __init__(self,snap,valid=True):self.snap=snap;self.valid=valid;self.calls=0
        def snap_point(self,q):self.calls+=1;return self.snap
        def is_navigable(self,q):return self.valid

    def test_rejection_precedence_preserves_original_acceptance(self):
        pf=self.PathFinder([.6,0,0],False)
        row=inspect_query([.59,0,0],[0,1,0],pf)
        self.assertEqual(row['primary_reason'],'snapped_not_navigable')
        self.assertIn('snap_residual',row['failed_checks'])
        self.assertIn('camera_horizontal',row['failed_checks'])
        self.assertEqual(pf.calls,1)

    def test_camera_boundary_is_not_relaxed(self):
        pf=self.PathFinder([.5,0,0])
        self.assertEqual(inspect_query([.5,0,0],[0,1,0],pf)['primary_reason'],'camera_horizontal')
        pf=self.PathFinder([.49,0,0])
        self.assertEqual(inspect_query([.49,0,0],[0,1,0],pf)['primary_reason'],'accepted')

    def test_nonfinite_query_does_not_call_native(self):
        pf=self.PathFinder([0,0,0])
        self.assertEqual(inspect_query([float('nan'),0,0],[0,1,0],pf)['primary_reason'],'query_nonfinite')
        self.assertEqual(pf.calls,0)

    def test_aabb_overlap_does_not_prove_triangle_intersects_camera_disk(self):
        # AABB contains x=.4,z=.4, but the closest edge has x+z=1.4.
        triangle=[[.4,0,1.],[1.,0,.4],[1.,0,1.]]
        r=rational_camera_distance(triangle,[0,1,0])
        self.assertFalse(r['inside_camera_horizontal'])
        self.assertTrue(r['lower_bound_verified'])
        self.assertAlmostEqual(r['distance_m'],2**.5*.7)

    def test_closed_height_boundary_is_retained_in_diagnostic(self):
        r=rational_camera_distance([[-1,0,-1],[1,0,-1],[0,0,1]],[0,2,0])
        self.assertTrue(r['inside_camera_horizontal'])
        self.assertTrue(r['lower_bound_verified'])
