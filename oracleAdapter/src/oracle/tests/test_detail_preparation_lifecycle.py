import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from oracle.research.detail_scene_validation import prepare


class DetailPreparationLifecycleTests(unittest.TestCase):
    def temporary(self):
        directory=Path.cwd()/'.cache/oracle-self-tests';directory.mkdir(parents=True,exist_ok=True)
        return tempfile.TemporaryDirectory(dir=directory)

    def test_preparation_receipts_exist_while_work_runs_and_close_after_success(self):
        with self.temporary() as folder:
            root=Path(folder);out=root/'outputs/oracleAdapter/probe';out.parent.mkdir(parents=True)
            def work(*args):
                self.assertEqual(json.loads((out/'source-freeze.json').read_text())['status'],'OPEN')
                self.assertEqual(json.loads((out/'preparation-process.json').read_text())['pid'],42)
                (out/'manifest.json').write_text('{}')
                return {'status':'FROZEN_PRB_DETAIL01_COMPLETE660','task_count':660}
            with patch('oracle.research.detail_scene_validation._prepare',side_effect=work),patch('oracle.research.detail_scene_validation.process_identity',return_value={'pid':42,'start_ticks':'7'}):
                prepare(root,out,0)
            self.assertEqual(json.loads((out/'source-freeze.json').read_text())['status'],'CLOSED')
            self.assertEqual(json.loads((out/'preparation-state.json').read_text())['status'],'FROZEN_PRB_DETAIL01_COMPLETE660')

    def test_failure_preserves_evidence_and_never_marks_preparation_ready(self):
        with self.temporary() as folder:
            root=Path(folder);out=root/'outputs/oracleAdapter/probe';out.parent.mkdir(parents=True)
            with patch('oracle.research.detail_scene_validation._prepare',side_effect=RuntimeError('fixture failure')),patch('oracle.research.detail_scene_validation.process_identity',return_value={'pid':42,'start_ticks':'7'}):
                with self.assertRaises(RuntimeError):prepare(root,out,0)
            self.assertTrue((out/'preparation-failure.json').exists())
            self.assertEqual(json.loads((out/'preparation-state.json').read_text())['status'],'FAILED_PRESERVED')
            self.assertEqual(json.loads((out/'source-freeze.json').read_text())['status'],'CLOSED')
