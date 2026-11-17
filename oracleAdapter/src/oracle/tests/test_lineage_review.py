import unittest
import tempfile
from pathlib import Path


class LineageReviewTests(unittest.TestCase):
    def test_unfinished_continuation_is_rejected_before_creating_any_merge(self):
        from oracle.research.lineage_review import review
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);child=root/'outputs/oracleAdapter/child';child.mkdir(parents=True)
            output=root/'outputs/oracleAdapter/merged'
            try:review(root,child,root/'outputs/oracleAdapter/review/validation.json',output)
            except Exception as exc:
                self.assertIsInstance(exc,ValueError)
                self.assertIn('not completed',str(exc))
            else:self.fail('Partial continuation was accepted')
            self.assertFalse(output.exists())

    def helpers(self):
        try:
            from oracle.research.lineage_review import verify_partition,verify_task_meaning
        except ImportError as exc:self.fail('Full lineage audit not implemented: '+str(exc))
        return verify_partition,verify_task_meaning

    def test_parent_and_child_must_partition_full_scope_without_duplicates(self):
        verify,_=self.helpers()
        verify({'a','b','c'},['a','b'],['c'])
        with self.assertRaises(ValueError):verify({'a','b','c'},['a'],['c'])
        with self.assertRaises(ValueError):verify({'a','b','c'},['a','b'],['b','c'])
        with self.assertRaises(ValueError):verify({'a','b','c'},['a','a'],['b','c'])

    def test_only_explicit_source_revision_may_change(self):
        _,verify=self.helpers()
        old=dict(task_key='x',targets=[[0,0,0]],privileges=['goal'],module_source_sha256='old')
        new={**old,'module_source_sha256':'new'}
        verify(old,new,'old','new')
        with self.assertRaises(ValueError):verify(old,{**new,'targets':[[1,0,0]]},'old','new')
        with self.assertRaises(ValueError):verify(old,{**new,'privileges':['goal','official_actions']},'old','new')
        with self.assertRaises(ValueError):verify(old,new,'wrong','new')
