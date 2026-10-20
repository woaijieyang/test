import unittest
from oracle.common.task_index import merkle_index,verify_entry


class TaskIndexTests(unittest.TestCase):
    def test_each_task_has_independent_frozen_membership_proof(self):
        rows=[{'task_key':str(i),'sha256':str(i)*64} for i in range(3)]
        root,entries=merkle_index(rows)
        for entry in entries:self.assertEqual(verify_entry(entry,root,3),entry['record'])
        changed={**entries[1],'record':{**entries[1]['record'],'task_key':'wrong'}}
        with self.assertRaises(ValueError):verify_entry(changed,root,3)
        with self.assertRaises(ValueError):verify_entry({**entries[0],'index':3},root,3)
