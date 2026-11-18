import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from adapter.source import Source
from host import protocol
from host.cli_journal import JournalCLI, save
from host.run import run_record
from shared.identity import ContractError
from test_runtime_contract_v2 import SOURCE, generator_candidate, reviewer_output


class SymmetricRepair(unittest.TestCase):
    def test_two_corrections_per_role_and_one_semantic_repair(self):
        g, g1 = generator_candidate(False), generator_candidate(True)
        r = reviewer_output(g, repaired=False)
        r1 = reviewer_output(g1, repaired=True, r1=True)
        fix = dict(candidate=g1, responses=[dict(finding_index=0, decision="accept",
                   source_quotes=["go down the hall"], reason="Restore the omitted traversal.")])
        g_bad=copy.deepcopy(g);del g_bad['handoffs']
        r_bad=copy.deepcopy(r);del r_bad['stage_checks'][0]['ending']['stop_scope']
        fix_bad=copy.deepcopy(fix);fix_bad['responses'][0]['source_quotes']=['absent']
        recheck_bad=copy.deepcopy(r1);recheck_bad['prior_finding_reviews'][0]['candidate_evidence'][0]['quote']='absent'
        replies=iter([g_bad,g,r_bad,r,fix_bad,fix,recheck_bad,r1]);requests=[]
        def transport(q):
            requests.append(q)
            return dict(output=next(replies),receipt=dict(request_id=str(len(requests)),model=q['model'],effort=q['effort']))
        out=run_record(Source('regression','R2R','en',SOURCE),transport)
        self.assertEqual(out['disposition'],'accepted_candidate',out['error'])
        self.assertEqual(out['technical_by_role'],{'generator':2,'reviewer':2})
        self.assertEqual(out['semantic_repairs'],1)
        self.assertEqual(len(requests),8)
        for before,after in [(2,3),(6,7)]:
            payload=lambda i:json.loads(requests[i]['messages'][1]['content'])
            self.assertEqual(payload(before)['candidate'],payload(after)['candidate'])
            self.assertEqual(payload(before)['rendered_instruction'],payload(after)['rendered_instruction'])
            self.assertEqual(out['calls'][before]['reviewed_snapshot'],out['calls'][after]['reviewed_snapshot'])
            self.assertIn('path',payload(after)['technical_feedback'])

    def test_task_scope_exception_and_unassessed_rows(self):
        cases=json.loads((Path(__file__).parent/'fixtures/inactive-review.json').read_bytes())
        for eid,case in cases.items():
            pay=case['payload'];v=case['review'];cand=pay['candidate']
            def validate(r,c=cand):protocol.reviewer(case['source'],c,r,rendered_instruction=pay['rendered_instruction'])
            if eid=='8797':
                validate(v)
                for field,value in [('code','OMISSION'),('source_quote','absent substring')]:
                    bad=copy.deepcopy(v);bad['findings'][0][field]=value
                    with self.assertRaises(ContractError):validate(bad)
            else:
                with self.assertRaises(ContractError):validate(v)
                cited=set(v['findings'][0]['source_requirement_ids'])
                for row in v['source_coverage']:
                    if row['requirement_id'] not in cited:row['status']='not_assessed_no_candidate'
                validate(v)
                for row in v['source_coverage']:
                    if row['requirement_id'] in cited:row['status']='not_assessed_no_candidate'
                with self.assertRaises(ContractError):validate(v)

    def test_quote_hint_is_unique_and_never_auto_consumed(self):
        for text,hint in [('A.  B.','A.  B.'),('A.  B. A.   B.',None)]:
            with self.assertRaises(ContractError) as err:protocol.quote('A. B.',text)
            self.assertEqual(err.exception.details.get('unique_whitespace_equivalent_hint'),hint)

    def test_active_or_pass_cannot_claim_unassessed(self):
        g=generator_candidate(True)
        for verdict in ('pass','revise','unresolved'):
            r=reviewer_output(g,repaired=True);r['verdict']=verdict
            r['source_coverage'][0].update(status='not_assessed_no_candidate',candidate_evidence=[])
            with self.subTest(verdict=verdict),self.assertRaises(ContractError):
                protocol.reviewer(SOURCE,g,r)


class CLIJournalTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.req={'model':'fixture','effort':'high','messages':[{'content':'fixture'}]}
        self.cli=JournalCLI(self.root/'ledger','task1',executable='fixture',sessions=self.root/'sessions')
        self.tid=str(uuid4());self.calls=0;self.behavior='success'
        s=self.root/'sessions/2026/11/16';s.mkdir(parents=True)
        save(s/(self.tid+'.jsonl'),{'type':'turn_context','payload':{'model':'fixture','effort':'high'}})
    def runner(self,args,**kwargs):
        self.calls+=1
        def emit(x):kwargs['stdout'].write(json.dumps(x).encode()+b'\n')
        emit({'type':'thread.started','thread_id':self.tid})
        if self.behavior=='unknown':raise TimeoutError('lost transport')
        if self.behavior=='route-once' and self.calls==1:
            emit({'type':'turn.failed','error':{'message':'workspace routing discovery failed'}})
            return type('Exit',(),{'returncode':1})()
        text='bad{' if self.behavior=='malformed' else '{"actual":1}'
        Path(args[args.index('--output-last-message')+1]).write_bytes(text.encode())
        emit({'type':'item.completed','item':{'type':'agent_message','text':text}})
        emit({'type':'turn.completed','usage':{'input_tokens':42}})
        return type('Exit',(),{'returncode':0})()
    def test_route_retry_then_restart_and_crash_lookup(self):
        self.behavior='route-once'
        with patch('host.cli_journal.subprocess.run',self.runner),patch('host.cli_journal.time.sleep'):
            first=self.cli(self.req);self.assertEqual(self.calls,2)
            exit_file=next(self.root.glob('ledger/*/attempt-1/exit.json'));exit_file.unlink()
            self.assertEqual(self.cli.recover(self.req),first)
            self.assertEqual(self.cli(self.req),first);self.assertEqual(self.calls,2)
            self.assertEqual(first['receipt']['parse_state'],'parsed')
    def test_concurrent_caller_cannot_execute_claimed_request(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        started=threading.Event(); release=threading.Event()
        def delayed(args,**kw):
            started.set();self.assertTrue(release.wait(5));return self.runner(args,**kw)
        with patch('host.cli_journal.subprocess.run',delayed),ThreadPoolExecutor(1) as pool:
            future=pool.submit(self.cli,self.req)
            try:
                self.assertTrue(started.wait(5))
                with self.assertRaises(RuntimeError):self.cli(self.req)
            finally:release.set()
            self.assertEqual(future.result()['output'],{'actual':1})
        self.assertEqual(self.calls,1)

    def test_timeout_unknown_never_resubmitted(self):
        self.behavior='unknown'
        with patch('host.cli_journal.subprocess.run',self.runner):
            with self.assertRaises(TimeoutError):self.cli(self.req)
            with self.assertRaises(RuntimeError):self.cli(self.req)
            self.assertEqual(self.calls,1)
    def test_malformed_completed_output_has_receipt(self):
        self.behavior='malformed'
        with patch('host.cli_journal.subprocess.run',self.runner):
            result=self.cli(self.req)
            self.assertEqual(result['output'],'bad{')
            self.assertEqual(result['receipt']['parse_state'],'malformed_json')
            self.assertEqual(self.cli(self.req),result);self.assertEqual(self.calls,1)
