"""Ensure source-preserving parent calibration reaches dependent diagnostics."""
import copy
import unittest
from host.compile import runtime_review_output
from host.template_selector import library
from host import protocol
from tools.rxr_diagnostic_repairs import PARENT, revise_parent


class ParentCalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows={row['template_id']:row for row in library('reviewer','rxr-en-us')}

    def test_window_negative_is_exactly_one_change_to_current_parent(self):
        parent=self.rows['RxR-REV-002'];child=self.rows['RxR-DIAG-29']
        old,new=PARENT[29][2:4]
        stages=copy.deepcopy(parent['review_input']['candidate']['subtasks'])
        self.assertEqual(stages[0].count(old),1)
        stages[0]=stages[0].replace(old,new,1)
        self.assertEqual(child['review_input']['candidate']['subtasks'],stages)
        self.assertNotIn('The source gives',stages[0])
        self.assertIn('A glass window is on your left and an open door in front of you.',stages[0])
        self.assertEqual(child['expected_review']['verdict'],'revise')
        protocol.reviewer(child['review_input']['original_instruction'],child['review_input']['candidate'],runtime_review_output(child))

    def test_window_negative_preserves_independent_door_and_bench_route(self):
        parent=self.rows['RxR-REV-002'];child=self.rows['RxR-DIAG-29']
        for clause in ('an open door in front of you','Go towards the open door which has a black bench on your right until you reach that open door.'):
            self.assertIn(clause,parent['review_input']['candidate']['subtasks'][0])
            self.assertIn(clause,child['review_input']['candidate']['subtasks'][0])
        self.assertEqual(parent['review_input']['candidate']['subtasks'][1],child['review_input']['candidate']['subtasks'][1])
        self.assertTrue(all(h['status']=='supported' for h in child['expected_review']['handoffs']))

    def test_stale_parent_is_rejected_not_silently_matched(self):
        parent=copy.deepcopy(self.rows['RxR-REV-002']);child=copy.deepcopy(self.rows['RxR-DIAG-29'])
        old=PARENT[29][2]
        parent['review_input']['candidate']['subtasks'][0]=parent['review_input']['candidate']['subtasks'][0].replace(old,'A different auxiliary description')
        with self.assertRaisesRegex(ValueError,'mutation absent'):
            revise_parent(child,parent,PARENT[29])


if __name__=='__main__': unittest.main()
