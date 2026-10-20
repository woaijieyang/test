from pathlib import Path
import tempfile
import unittest
from oracle.common.journal import ResultJournal


class JournalTests(unittest.TestCase):
    def test_restart_preserves_failure_and_rejects_duplicate(self):
        with tempfile.TemporaryDirectory() as folder:
            with ResultJournal(folder) as journal:journal.append('task:attempt1',{'status':'FAILURE_PRESERVED'})
            with ResultJournal(folder) as journal:
                self.assertEqual(journal.records['task:attempt1']['status'],'FAILURE_PRESERVED')
                with self.assertRaises(ValueError):journal.append('task:attempt1',{'status':'PASS'})

    def test_torn_tail_is_preserved_and_new_segment_can_resume(self):
        with tempfile.TemporaryDirectory() as folder:
            with ResultJournal(folder) as journal:
                journal.append('a',{'status':'PASS'});first=journal.path
            with first.open('ab') as stream:stream.write(b'{"seq":2')
            original=first.read_bytes()
            with ResultJournal(folder) as journal:
                self.assertEqual(set(journal.records),{'a'})
                journal.append('b',{'status':'FAILURE_PRESERVED'})
                self.assertNotEqual(journal.path,first)
            self.assertEqual(first.read_bytes(),original)
            with ResultJournal(folder) as journal:self.assertEqual(set(journal.records),{'a','b'})

    def test_complete_record_tamper_is_not_treated_as_torn_tail(self):
        with tempfile.TemporaryDirectory() as folder:
            with ResultJournal(folder) as journal:
                journal.append('a',{'status':'FAILURE_PRESERVED'});path=journal.path
            path.write_bytes(path.read_bytes().replace(b'FAILURE_PRESERVED',b'PASS'))
            with self.assertRaises(ValueError):ResultJournal(folder)
