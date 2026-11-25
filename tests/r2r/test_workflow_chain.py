"""Exercise the source-to-release chain and actual active rule witnesses."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from adapter.source import from_record
from host.compile import ROOT, compile_prompt, teaching_card
from host.run import run_record
from host.r2r.phase_teaching import phase_examples, validate_phase_pairs
from host.r2r.relations import facet_signals
from host.r2r.selection import select_bundle, teaching_index, validate_bundle, validate_selection, _verify
from host.template_selector import library
from shared.identity import text_hash

PINS = {role: {'model': 'chain-fixture', 'effort': 'low'} for role in ('generator', 'reviewer')}


def source_record(text):
    return from_record({'dataset': 'R2R', 'language': 'en', 'split': 'val_unseen',
                        'episode_id': 999, 'path_id': 12345, 'scan': 'private-test-scan',
                        'instruction': {'instruction_text': text},
                        'gt_path': ['forbidden-trajectory'], 'navigation_score': 1})


class EntryGuards(unittest.TestCase):
    def test_explicit_current_source_echo_rejected(self):
        rows={r['template_id']:r for r in library('generator','r2r-en')}
        ids=['R2R-GEN-001','R2R-GEN-008','R2R-GEN-010','R2R-GEN-013']
        source=rows[ids[0]]['input']['original_instruction']
        with self.assertRaisesRegex(ValueError,'echoes task source'):
            compile_prompt('generator',profile='r2r-en',selected_ids=ids,original_instruction=source)

    def test_same_family_explicit_duplicate_rejected(self):
        with self.assertRaisesRegex(ValueError,'Repeated R2R teaching source or route family'):
            validate_selection('generator',['R2R-GEN-001','R2R-GEN-003','R2R-GEN-008','R2R-GEN-010'],source_text='Walk on.')

    def test_task_family_explicit_guard(self):
        index,_=teaching_index();ids=['R2R-GEN-001','R2R-GEN-008','R2R-GEN-010','R2R-GEN-013']
        with self.assertRaisesRegex(ValueError,'matches task route family'):
            validate_selection('generator',ids,source_text='A different instruction.',source_family=index[ids[0]]['route_family'])

    def test_metadata_must_match_authored_content(self):
        row=library('generator','r2r-en')[0];index,_=teaching_index();item=index[row['template_id']]
        for field,value in [('lesson','fabricated lesson'),('route_family','fabricated family'),('pair_id','fabricated pair')]:
            changed=deepcopy(item);changed[field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'differs from authored evidence'):
                _verify(row,changed)

    def test_pair_order_guard_before_transport(self):
        source='Enter the hallway and wait.';bundle=select_bundle(source)
        bad=deepcopy(bundle);bad['reviewer'][:2]=bad['reviewer'][:2][::-1]
        with self.assertRaisesRegex(ValueError,'paired selection differs'):
            validate_bundle(source,{role:bad[role] for role in ('generator','reviewer')})
        calls=[]
        with patch('host.r2r.selection.select_bundle',return_value=bad):
            result=run_record(source_record(source),lambda req:calls.append(req),pins=PINS)
        self.assertEqual(result['disposition'],'fallback_technical');self.assertFalse(result['navigation_eligible'])
        self.assertEqual(result['instruction'],source);self.assertEqual(calls,[])

    def test_individually_valid_phase_cases_must_pair(self):
        gs=phase_examples('generator','repair');rs=phase_examples('reviewer','recheck')
        with patch('host.r2r.phase_teaching.phase_examples',side_effect=lambda role,phase:gs if role=='generator' else rs[::-1]):
            with self.assertRaisesRegex(ValueError,'pair identity mismatch'):validate_phase_pairs()
            calls=[];source='  Walk to the door and stop. \r\n'
            result=run_record(source_record(source),lambda req:calls.append(req),pins=PINS)
        self.assertEqual(result['instruction'],source);self.assertEqual(result['disposition'],'fallback_technical')
        self.assertFalse(result['navigation_eligible']);self.assertEqual(calls,[])


class TeachingChain(unittest.TestCase):
    def test_surface_motion_cues_and_boundaries(self):
        for text in ('Walk a few paces along the woven runner toward the lamp, then wait.',
                     'On the woven runner, walk toward the lamp.', 'Follow the blue rug to the doorway.'):
            self.assertIn('surface_motion',facet_signals(text))
        for text in ('From the runner, walk toward the lamp.', 'Walk straight forward and stop on the rug.',
                     'Walk onto the runner on the floor.', 'Walk to the room with a rug on the floor.'):
            self.assertNotIn('surface_motion',facet_signals(text))
        index,_=teaching_index()
        for role,tid in [('generator','R2R-CORE-G09'),('reviewer','R2R-CORE-R09')]:
            row=json.loads((ROOT/index[tid]['path']).read_bytes())
            for detailed in (True,False):
                contrast=teaching_card(row,role,detailed)['decision_boundary']
                self.assertIn('along the woven runner',contrast['counter_boundary'])
                self.assertIn('From the woven runner',contrast['counter_boundary'])
                self.assertIn('final standing placement',contrast['operation'])

    def test_all_active_p2_have_projected_case_witness(self):
        data=json.loads((ROOT/'provenance/r2r_operation_coverage.json').read_bytes())
        rules=json.loads((ROOT/'provenance/r2r_rule_links.json').read_bytes())['nodes']
        self.assertEqual(set(data['active_p2_witnesses']),{r['id'] for r in rules if r['level']==2})
        self.assertEqual(len(data['active_p2_witnesses']),22);self.assertFalse(data['active_p2_without_witness'])
        index,_=teaching_index()
        for item in data['records']:
            if 'projected_pointer' not in item:continue  # separately validated G1/R1 examples
            row=index[item['template_id']];self.assertIn(row['status'],('fixed_core','dynamic'))
            asset=json.loads((ROOT/row['path']).read_bytes())
            for detailed in (True,False):
                projected=teaching_card(asset,item['role'],detailed)
                value=projected[item['projected_pointer'].lstrip('/')]
                self.assertEqual(value['counter_boundary'] if isinstance(value,dict) else value,
                                 item['counter_boundary'] if isinstance(value,dict) else item['operation'])

    def test_real_adapter_payload_snapshot_and_release_chain(self):
        g=phase_examples('generator','repair')[0];r=phase_examples('reviewer','recheck')[0]
        source=g['input']['original_instruction'];src=source_record(source)
        outputs=[g['expected_output']['candidate'],g['input']['review'],g['expected_output'],r['expected_output']]
        requests=[]
        def transport(req):
            requests.append(deepcopy(req))
            return {'output':deepcopy(outputs[len(requests)-1]),'receipt':{'model':req['model'],'effort':req['effort'],'request_id':str(len(requests))}}
        result=run_record(src,transport,pins=PINS)
        self.assertEqual([q['phase'] for q in requests],['initial','review','repair','recheck'])
        self.assertEqual(result['instruction'],source);self.assertEqual(result['disposition'],'accepted_source_exact')
        self.assertEqual(result['instruction_sha256'],text_hash(source));self.assertTrue(result['navigation_eligible'])
        payloads=[json.loads(q['messages'][1]['content']) for q in requests]
        self.assertEqual([set(p) for p in payloads],[{'original_instruction'},
            {'original_instruction','candidate','rendered_instruction'}, {'original_instruction','candidate','review'},
            {'original_instruction','candidate','rendered_instruction','prior_candidate','prior_review','prior_rendered_instruction'}])
        for req,payload in zip(requests,payloads):
            self.assertEqual(payload['original_instruction'],source)
            self.assertNotIn('private-test-scan',req['messages'][1]['content'])
            self.assertNotIn('forbidden-trajectory',req['messages'][1]['content'])
            self.assertEqual(req['profile'],'r2r-en')
        self.assertEqual(payloads[1]['candidate'],payloads[2]['candidate'])
        self.assertEqual(payloads[2]['review'],payloads[3]['prior_review'])
        self.assertEqual(payloads[1]['rendered_instruction'],payloads[3]['prior_rendered_instruction'])
        for i,j in [(0,2),(1,3)]:
            self.assertEqual(requests[i]['template_bundle'],requests[j]['template_bundle'])
            self.assertEqual(requests[i]['dataset_rules'],requests[j]['dataset_rules'])
        self.assertEqual(result['snapshot_sha256'],result['snapshots'][-1]['render_snapshot_sha256'])
        self.assertEqual(result['calls'][-1]['reviewed_snapshot'],result['snapshots'][-1]['bound_candidate'])
