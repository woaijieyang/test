from pathlib import Path
import json
import tempfile
import unittest
from oracle.common.artifacts import content_digest
from oracle.research.cohort_review import read_prefix,selected_entries


class CohortReviewTests(unittest.TestCase):
    def test_complete_scope_is_required_without_replacing_parent(self):
        rows=[{'record':dict(task_key='a',dataset='r2r')},{'record':dict(task_key='b',dataset='landmark_rxr')}]
        self.assertEqual(set(selected_entries(rows,{'r2r':1})),{'a'})
        with self.assertRaises(ValueError):selected_entries(rows,{'r2r':2})
        with self.assertRaises(ValueError):selected_entries(rows+[rows[0]],{'r2r':1})

    def test_snapshot_chain_and_payload_identity_are_verified(self):
        core={'seq':1,'prev':'0'*64,'key':'a','payload':{'task_key':'a'}}
        row={**core,'entry_sha256':content_digest(core)}
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'segment.snapshot';p.write_text(json.dumps(row)+chr(10))
            values,count,last=read_prefix([p]);self.assertEqual(count,1);self.assertEqual(values['a'],{'task_key':'a'})
            row['payload']['task_key']='different';p.write_text(json.dumps(row)+chr(10))
            with self.assertRaises(ValueError):read_prefix([p])

    def test_inflight_partial_line_cannot_be_sealed_as_a_complete_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'segment.snapshot';p.write_bytes(b'{')
            with self.assertRaises(ValueError):read_prefix([p])
