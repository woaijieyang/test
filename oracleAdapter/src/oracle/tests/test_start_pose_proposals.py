import copy
import unittest
import json,math
from pathlib import Path
from oracle.research.start_pose_proposals import frozen_anchor, fixed_ring_offsets


class StartPoseProposals(unittest.TestCase):
    def test_actual_frozen_ring_configuration_is_complete_without_new_samples(self):
        cfg=json.loads((Path(__file__).resolve().parents[1]/'configs/experiments/global_bounded_mapping_v1.json').read_text())
        offsets=fixed_ring_offsets(cfg['rings'])
        self.assertEqual(len(offsets),264)
        self.assertEqual(offsets[0],(.1,0.))
        self.assertAlmostEqual(math.hypot(*offsets[-1]),.35)
        self.assertTrue(all(math.isfinite(v) for p in offsets for v in p))

    def data(self):
        task={'targets':[[.1,.1,0],[1,0,0]],'raw_heading':.3,'legacy_source_record_sha256':'source'}
        proposal={'proposed_targets':copy.deepcopy(task['targets']),'old_targets':[[0,0,0],[1,0,0]],
                  'original_heading':.3,'legacy_source_record_sha256':'source',
                  'choices':[{'anchor_kind':'bounded_camera_projection','anchor':[0,0,0]}]}
        return task,proposal

    def test_original_anchor_is_not_rebased_on_the_first_repair(self):
        task,proposal=self.data();self.assertEqual(frozen_anchor(task,proposal),[0,0,0])
        proposal['choices'][0]['anchor']=task['targets'][0]
        with self.assertRaises(ValueError):frozen_anchor(task,proposal)

    def test_changed_heading_or_reference_chain_is_rejected(self):
        task,proposal=self.data();task['raw_heading']=.4
        with self.assertRaises(ValueError):frozen_anchor(task,proposal)
        task,proposal=self.data();task['targets'][1]=[2,0,0]
        with self.assertRaises(ValueError):frozen_anchor(task,proposal)
