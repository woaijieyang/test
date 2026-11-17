"""Offline contracts only. Never calls a provider or reads real credentials."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"backends"))
from transport import Task, ResponsesBackend, execute_once

TASK=Task('generator','Original task bytes: hello\n',{'type':'object'})
def response(**changes):
    value=dict(status='completed',id='fake-response',model='fake-reported-model',
        output=[dict(type='message',content=[dict(type='output_text',text='{"ok":true}')])])
    value.update(changes)
    return value
def validate(value):
    if value != {'ok': True}: raise ValueError('schema/source contract failed')

class Contracts(unittest.TestCase):
    def setUp(self):
        root=Path.cwd()/'outputs'/'backend-contract-tests';root.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=root);self.root=Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def backend(self, send):
        return ResponsesBackend(endpoint='https://example.invalid/v1/responses',
            api_key_env='VLN_OFFLINE_TEST_FAKE_KEY',model='fake-request-model',effort='medium',send=send)

    def test_isolated_exact_input_and_identity(self):
        requests=[]
        b=self.backend(lambda payload:(requests.append(payload) or response()))
        r=execute_once(b,TASK,self.root/'a',validate)
        self.assertEqual(requests[0]['input'],TASK.compiled_prompt)
        self.assertFalse(requests[0]['store'])
        self.assertNotIn('previous_response_id',requests[0])
        self.assertIsNone(r.child_thread_id)
        self.assertEqual(r.response_id,'fake-response')
        self.assertNotEqual(r.declared_model,r.reported_model)
        self.assertIsNone(r.reported_effort)

    def test_existing_attempt_no_second_request(self):
        requests=[];b=self.backend(lambda p:(requests.append(p) or response()))
        execute_once(b,TASK,self.root/'a',validate)
        with self.assertRaises(FileExistsError):execute_once(b,TASK,self.root/'a',validate)
        self.assertEqual(len(requests),1)

    def test_incomplete_and_refusal_and_missing_identity(self):
        bad=[response(status='incomplete'),response(id=None),response(model=None),
             response(output=[dict(type='message',content=[dict(type='refusal',refusal='no')])])]
        for i,value in enumerate(bad):
            with self.assertRaises(RuntimeError):execute_once(self.backend(lambda p,v=value:v),TASK,self.root/str(i),validate)
            self.assertTrue((self.root/str(i)/'failure.json').exists())
            self.assertFalse((self.root/str(i)/'validation.json').exists())

    def test_invalid_output_preserved_not_accepted(self):
        value=response(output=[dict(type='message',content=[dict(type='output_text',text='bad JSON')])])
        with self.assertRaises(ValueError):execute_once(self.backend(lambda p:value),TASK,self.root/'a',validate)
        self.assertTrue((self.root/'a'/'receipt.json').exists())
        self.assertFalse((self.root/'a'/'validation.json').exists())

    def test_no_secret_in_failure_or_traceback(self):
        secret='FAKE_TEST_SECRET_NEVER_A_REAL_KEY'
        def fail(p):raise RuntimeError('Authorization: Bearer '+secret)
        with patch.dict(os.environ,VLN_OFFLINE_TEST_FAKE_KEY=secret):
            with self.assertRaises(RuntimeError) as error:
                execute_once(self.backend(fail),TASK,self.root/'a',validate)
            self.assertNotIn(secret,str(error.exception))
            self.assertTrue(error.exception.__suppress_context__)
        for p in self.root.rglob('*'):
            if p.is_file():self.assertNotIn(secret,p.read_text())

    def test_secret_echo_not_saved(self):
        secret='FAKE_TEST_SECRET_NEVER_A_REAL_KEY'
        with patch.dict(os.environ,VLN_OFFLINE_TEST_FAKE_KEY=secret):
            with self.assertRaises(RuntimeError):
                execute_once(self.backend(lambda p:response(echo=secret)),TASK,self.root/'a',validate)
        self.assertFalse((self.root/'a'/'response.json').exists())
        for p in self.root.rglob('*'):
            if p.is_file():self.assertNotIn(secret,p.read_text())

    def test_https_and_no_embedded_secrets(self):
        for endpoint in ('http://example.invalid','https://key@example.invalid','https://example.invalid/?key=secret'):
            with self.assertRaises(ValueError):
                ResponsesBackend(endpoint=endpoint,api_key_env='TEST',model='fake',effort='medium')

    def test_private_file_and_conflicting_sources(self):
        path=self.root/'api-key.local.json';path.write_text(json.dumps({'api_key':'FAKE_LOCAL_FILE_SECRET'}))
        path.chmod(0o600)
        b=self.backend(lambda p:response());b.api_key_file=str(path.resolve())
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(b._key(),'FAKE_LOCAL_FILE_SECRET')
            execute_once(b,TASK,self.root/'a',validate)
        with patch.dict(os.environ,VLN_OFFLINE_TEST_FAKE_KEY='FAKE_OTHER_SECRET'):
            with self.assertRaises(RuntimeError):b._key()
        for p in (self.root/'a').rglob('*'):
            if p.is_file():self.assertNotIn('FAKE_LOCAL_FILE_SECRET',p.read_text())

    def test_invalid_file_no_secret_in_error(self):
        path=self.root/'api-key.local.json';path.write_text('FAKE_MALFORMED_SECRET');path.chmod(0o600)
        b=self.backend(lambda p:response());b.api_key_file=str(path.resolve())
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(RuntimeError) as error:b._key()
        self.assertNotIn('FAKE_MALFORMED_SECRET',str(error.exception))

if __name__=='__main__':unittest.main(verbosity=2)
