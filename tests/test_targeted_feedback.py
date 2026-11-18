"""Real source records and explicitly synthetic offline counterfactuals."""
import copy
import json
import unittest
from pathlib import Path

from adapter.source import Source
from host import protocol
from host.run import run_record
from shared.identity import ContractError

CASES = json.loads((Path(__file__).parent/'fixtures/targeted-feedback.json').read_bytes())


def simulate(case, replies):
    requests = []
    def replay(req):
        requests.append(req)
        if len(requests) > len(replies):
            raise AssertionError('unexpected model call')
        return dict(output=replies[len(requests)-1],
                    receipt=dict(model=req['model'], effort=req['effort'], request_id=str(len(requests))))
    out = run_record(Source('probe','R2R','en',case['source']),replay)
    return out, [json.loads(r['messages'][1]['content']) for r in requests]


class FeedbackTests(unittest.TestCase):
    def test_1511_feedback_then_review(self):
        case=CASES['1511']
        corrected=copy.deepcopy(case['g'])
        corrected['subtasks'][0]=corrected['subtasks'][0].replace('fireplace is is behind','fireplace is behind')
        # Deliberately invalid reviewer reply: receiving R0 already proves revalidation + freeze.
        out,reqs=simulate(case,[case['g'],corrected,{},{},{}])
        self.assertEqual([c['phase'] for c in out['calls']],['initial','initial','review','review','review'])
        self.assertEqual(reqs[1]['technical_feedback']['path'],'/stage_audit/0/entry/candidate_quotes/0')
        self.assertEqual(reqs[1]['previous_output'],case['g'])
        self.assertEqual(reqs[1]['original_instruction'],case['source'])
        self.assertEqual(reqs[2]['rendered_instruction'].strip(),'\n'.join(corrected['subtasks']))
        self.assertEqual(out['quote_corrections'],1)
        self.assertEqual(out['diagnostic']['step'],'reviewer_validation')

    def test_unfixed_quote_falls_back_after_two_corrections(self):
        case=CASES['1511']
        out,_=simulate(case,[case['g'],case['g'],case['g']])
        self.assertEqual(out['quote_corrections'],2)
        self.assertEqual(len(out['calls']),3)
        self.assertEqual(out['disposition'],'fallback_technical')
        self.assertEqual(out['instruction'],case['source'])

    def test_two_technical_corrections_and_one_semantic_repair(self):
        case=CASES['1243']; g=copy.deepcopy(case['g']); g['subtasks']=['Go down the stairs.']
        audit=g['stage_audit'][0]
        for k in ('conditions','target'):audit[k]=dict(text=None,candidate_quotes=[])
        for k in ('ending','process'):audit[k].update(text='Descend.',candidate_quotes=['Go down the stairs'])
        audit['ending']['stop_scope']='none'
        bad=copy.deepcopy(g);del bad['handoffs']
        fix=dict(candidate=case['g'],responses=[dict(finding_index=0,decision='accept',source_quotes=['stop at the very bottom'],reason='Restore terminal stop.')])
        wrong=copy.deepcopy(fix);wrong['responses'][0]['source_quotes']=['absent phrase']
        r1=copy.deepcopy(case['pass_review'])
        r1['prior_finding_reviews']=[dict(finding_index=0,status='resolved',candidate_evidence=[dict(subtask_index=0,quote='stop at the very bottom')],explanation='Restored.')]
        out,requests=simulate(case,[bad,g,case['gap'],wrong,fix,r1])
        self.assertEqual(out['disposition'],'accepted_source_exact',out['error'])
        self.assertEqual((out['technical_corrections'],out['quote_corrections'],out['semantic_repairs']),(2,1,1))
        self.assertEqual(requests[1]['technical_attempt'],1)
        self.assertEqual(requests[4]['technical_attempt'],2)
        self.assertEqual(requests[4]['review'],case['gap'])
        self.assertEqual([c['phase'] for c in out['calls']],['initial','initial','review','repair','repair','recheck'])

    def test_1243_gap_can_reach_repair_and_recheck(self):
        case=CASES['1243']
        g=copy.deepcopy(case['g'])
        g['subtasks']=['Go down the stairs.']
        audit=g['stage_audit'][0]
        for field in ('conditions','target'):
            audit[field]=dict(text=None,candidate_quotes=[])
        for field in ('ending','process'):
            audit[field].update(text='Descend the stairs.',candidate_quotes=['Go down the stairs'])
        audit['ending']['stop_scope']='none'
        g1=dict(candidate=case['g'],responses=[dict(finding_index=0,decision='accept',
            source_quotes=['stop at the very bottom'],reason='Restore the missing bottom stop.')])
        r1=copy.deepcopy(case['pass_review'])
        r1['prior_finding_reviews']=[dict(finding_index=0,status='resolved',
            candidate_evidence=[dict(subtask_index=0,quote='stop at the very bottom')],explanation='Stop restored.')]
        out,_=simulate(case,[g,case['gap'],g1,r1])
        self.assertEqual(out['disposition'],'accepted_source_exact',out.get('error'))
        self.assertEqual([c['phase'] for c in out['calls']],['initial','review','repair','recheck'])

    def test_unmatched_gap_and_false_pass_rejected(self):
        case=CASES['1243']; candidate=dict(status='ok',subtasks=['Go down the stairs.'],issues=[])
        for change in ('pass','wrong_stage','false_quote','missing_finding'):
            r=copy.deepcopy(case['gap'])
            if change=='pass':r['verdict']='pass'
            elif change=='wrong_stage':r['findings'][0]['affected_subtask_indices']=[1]
            elif change=='false_quote':r['findings'][0]['source_quote']='never in source'
            else:r['findings']=[]
            with self.subTest(change=change),self.assertRaises(ContractError):
                protocol.reviewer(case['source'],candidate,r)

    def test_485_paraphrase_and_stay_with_real_evidence(self):
        case=CASES['485'];g=copy.deepcopy(case['g'])
        g['stage_audit'][-1]['ending']['text']='Approach the pool table. Arrival and a physical halt are not claimed.'
        protocol.generator(case['source'],g)
        g['stage_audit'][-1]['ending']['stop_scope']='terminal'
        with self.assertRaises(ContractError):protocol.generator(case['source'],g)
        case=CASES['1243']
        g=json.loads(json.dumps(case['g']).replace('stop at','stay at'))
        protocol.generator(case['source'].replace('stop at','stay at'),g)
        with self.assertRaises(ContractError):protocol.generator(case['source'],g)
