"""Mechanical and authored semantic regression tests, not navigation scores."""
import copy,json,re,subprocess,unittest
from unittest.mock import patch
from adapter.source import Source
from renderer.freeze import freeze
from host import protocol
from host.compile import ROOT,compile_prompt,core_library,runtime_review_output
from host.run import run_record
from host.template_selector import library,select_examples
from r2r.selection import select_bundle,signals,validate_selection,teaching_index
from r2r.teaching import card
EVALUATED='9dd24a655a845d59698e835c0326fbf73db5fbb8'

def rows():
    return {r['template_id']:r for role in ('generator','reviewer') for r in core_library(role,'r2r-en')+library(role,'r2r-en')}

def fullpass(source,candidate):
    parts=candidate['subtasks'];checks=[]
    for s in candidate['stage_audit']:
        s=copy.deepcopy(s);s.update(status='supported',source_requirement_ids=['SRC-01']);checks.append(s)
    hands=copy.deepcopy(candidate['handoffs'])
    for h in hands:h['source_requirement_ids']=['SRC-01']
    return dict(verdict='pass',dimensions={d:'pass' for d in protocol.DIMENSIONS},source_coverage=[dict(requirement_id='SRC-01',source_quote=source,requirement='Preserve the complete source route.',candidate_evidence=[dict(subtask_index=i,quote=s) for i,s in enumerate(parts)],status='covered')],layer_checks=[dict(layer=l,status='not_applicable' if l=='L4_handoffs' and len(parts)==1 else 'pass',conclusion='The actual candidate satisfies this layer.',finding_indices=[]) for l in protocol.LAYERS],findings=[],stage_checks=checks,handoffs=hands,prior_finding_reviews=[])

def run(source,replies):
    seen=[];pending=copy.deepcopy(replies)
    def transport(req):
        seen.append(req)
        if not pending:raise AssertionError('Unexpected extra invocation')
        return {'output':pending.pop(0),'receipt':{'model':req['model'],'effort':req['effort'],'request_id':f'fixture-{len(seen)}'}}
    result=run_record(Source('r2r-fixture','R2R','en',source),transport,pins={r:dict(model='fixture',effort='low') for r in ('generator','reviewer')})
    return result,seen,pending

def partial_fixture():
    ex=json.loads((ROOT/'generator/repair_examples.json').read_bytes())[0]
    source=ex['input']['original_instruction'];good=copy.deepcopy(ex['output']['candidate'])
    def edit(x):
        if isinstance(x,str):return x.replace('Go around the right side of the center unit','Go around the left side of the center unit').replace('right side of the center unit','left side of the center unit')
        if isinstance(x,list):return [edit(v) for v in x]
        if isinstance(x,dict):return {k:(v if k=='source_quotes' else edit(v)) for k,v in x.items()}
        return x
    bad=edit(copy.deepcopy(good));r0=copy.deepcopy(ex['input']['review'])
    raw_r0=copy.deepcopy(r0)
    src=Source('r2r-fixture','R2R','en',source)
    bad_view=freeze(src,bad['subtasks'],'\n');good_view=freeze(src,good['subtasks'],'\n')
    # Author fixture quotes against the actual frozen stage, not the Source
    # envelope's trailing space. This is not a runtime quote repair facility.
    r0['source_coverage'][0]['candidate_evidence'][0]['quote']=bad_view.stages[0]
    r0['stage_checks'][0]['process']['candidate_quotes']=[bad_view.stages[0]]
    r0['findings'][0]['repair']['instruction']+=' Add a stop at the center unit before going to the doorway.'
    answer=copy.deepcopy(ex['output'])
    answer['responses'][0].update(decision='partially_accept',reason='Restore the supported right side; retain only the source doorway stop because the proposed center-unit stop is unsupported.')
    reviewed_good=copy.deepcopy(good);reviewed_good['subtasks']=list(good_view.stages)
    reviewed_good['stage_audit'][0]['process']['candidate_quotes']=[good_view.stages[0]]
    r1=fullpass(source,reviewed_good)
    r1['prior_finding_reviews']=[dict(finding_index=0,status='resolved',candidate_evidence=[dict(subtask_index=0,quote=good_view.stages[0])],explanation='The right-side traversal is restored while the unsupported intermediate stop is absent.')]
    return source,bad,r0,answer,r1,raw_r0,bad_view

class Teaching(unittest.TestCase):
    def test_all_runtime_templates_use_active_contracts(self):
        for tid,r in rows().items():
            with self.subTest(id=tid):
                if r['role']=='generator':protocol.generator(r['input']['original_instruction'],r['output'])
                else:protocol.reviewer(r['review_input']['original_instruction'],r['review_input']['candidate'],r['expected_review'])
    def test_rule_parents_and_shared_references_resolve(self):
        data=json.loads((ROOT/'provenance/r2r_rule_links.json').read_bytes());by={r['id']:r for r in data['nodes']}
        for r in by.values():
            if r['parent']:
                p=by[r['parent']];self.assertEqual(p['level'],r['level']-1);self.assertEqual(p['role'],r['role'])
            self.assertIn(r['id'],(ROOT/r['path']).read_text())
        self.assertEqual({r['role'] for r in by.values()},{'generator','reviewer'})
        self.assertTrue(all(any(r['role']==role and r['level']==level for r in by.values()) for role in ('generator','reviewer') for level in (0,1,2)))
        shared=(ROOT/'shared/dataset_rules/r2r_en.md').read_text()
        for role in ('generator','reviewer'):
            for ref in set(re.findall(r'S-[A-Z]+',(ROOT/role/'dataset_rules/r2r_en.md').read_text())):self.assertIn(ref,shared)
    def test_reference_attachment_repairs(self):
        bank=rows();a=bank['R2R-GEN-030']['output']['subtasks'][1]
        self.assertIn('first room to the left of the staircase',a)
        g=bank['R2R-GEN-035']['output']['subtasks']
        self.assertIn('enter the hallway to the slight right past the chair',g[0]);self.assertNotIn('After passing the chair',g[1])
        r=bank['R2R-CORE-R07']['expected_review']
        self.assertEqual(r['findings'][0]['source_requirement_ids'],['SRC-02'])
        self.assertNotIn('Preserve the chair pass-by endpoint',json.dumps(r))
    def test_grouping_tolerance_and_precise_check(self):
        bank=rows()
        self.assertEqual(bank['R2R-CORE-R06']['expected_review']['verdict'],'pass')
        self.assertEqual(bank['R2R-DIAG-28']['expected_review']['verdict'],'pass')
        self.assertEqual(bank['R2R-CORE-R04']['expected_review']['findings'][0]['c_check'],'C10')
        self.assertEqual(bank['R2R-CORE-R06']['expected_review']['stage_checks'][0]['ending']['kind'],'terminal_goal_directive')
    def test_local_error_does_not_destroy_correct_handoff(self):
        bank=rows()
        for n in (21,22,23):
            a=bank[f'R2R-DIAG-{n}']['expected_review']
            self.assertEqual(a['handoffs'][0]['status'],'supported');self.assertEqual(a['stage_checks'][0]['status'],'supported')
            self.assertEqual(a['findings'][0]['affected_subtask_indices'],[1])
        a=bank['R2R-DIAG-23']['expected_review'];self.assertIn('right set of windows',a['stage_checks'][1]['target']['text'])
    def test_terminal_and_local_direction_repairs(self):
        bank=rows();a=bank['R2R-DIAG-14']['expected_review']['stage_checks'][0]
        self.assertEqual(a['ending']['stop_scope'],'terminal');self.assertIn('brown rug',a['ending']['candidate_quotes'][0])
        f=bank['R2R-DIAG-12']['expected_review']['findings'][0]
        self.assertEqual(f['source_requirement_ids'],['SRC-02']);self.assertIn('kitchen bar',f['candidate_evidence'][0]['quote'])
        self.assertEqual(bank['R2R-DIAG-09']['expected_review']['findings'][0]['c_check'],'C11')
    def test_source_identity_and_library_partition(self):
        index,_=teaching_index();self.assertEqual(len(index),119)
        self.assertEqual(sum(i['status']=='fixed_core' for i in index.values()),20)
        self.assertEqual(sum(i['status']=='source_archive' for i in index.values()),19)
        self.assertEqual(sum(i['status']=='retained_pair' for i in index.values()),4)
        self.assertEqual(sum(i['status']=='dynamic' for i in index.values()),76)
        for role in ('generator','reviewer'):
            for r in core_library(role,'r2r-en'):self.assertEqual(r['source']['split'],'val_seen')
    def test_compact_cards_are_not_old_protocol_lookalikes(self):
        for tid,r in rows().items():
            c=card(r,r['role'],True)
            self.assertTrue(c['lesson']);self.assertTrue(c['counter_boundary'])
            if c['format']=='lesson_summary':self.assertNotIn('findings',c);self.assertNotIn('repair',c)
            elif r['role']=='reviewer':protocol.validate('reviewer/output.schema.json',c['expected_output'])
            else:protocol.validate('generator/output.schema.json',c['expected_output'])
    def test_no_new_release_labels_in_model_inputs(self):
        for role,phases in [('generator',['initial','repair']),('reviewer',['review','recheck'])]:
            for phase in phases:
                p,_=compile_prompt(role,phase,profile='r2r-en',original_instruction='Go through the open door and wait.')
                self.assertNotRegex(p,r'LLM-decompose-v|\bv6\.6')
                self.assertIn('G-P0' if role=='generator' else 'R-P0',p)
                self.assertNotIn('RXR ROLE GUIDANCE',p)

class Selection(unittest.TestCase):
    def test_count_pair_order_and_real_trace_for_all_sources(self):
        bank={r['template_id']:r for r in library('reviewer','r2r-en')}
        for row in library('generator','r2r-en'):
            q=row['input']['original_instruction'];b=select_bundle(q);g=b['generator'];r=b['reviewer']
            self.assertTrue(4<=len(g)<=6);self.assertTrue(2<=len(r)-len(g)<=3)
            self.assertEqual([bank[i]['pair_id'] for i in r[:len(g)]],g)
            self.assertNotIn(row['template_id'],g)
            self.assertEqual([e['template_id'] for e in b['evidence']['generator']['selected']],g)
            self.assertEqual(b,select_bundle(q))
            for t in b['evidence']['generator']['selected']:
                if t['selection_reason']=='uncovered_skill':self.assertTrue(t['optional_coverage'])
                for spans in t['matched_source_spans'].values():
                    for s in spans:self.assertEqual(q[s['start']:s['end']],s['quote'])
    def test_explicit_counts_and_entry_validation(self):
        for n in (4,5,6):self.assertEqual(len(select_bundle('Go through the doorway.',count=n)['generator']),n)
        for bad in (True,3,7,8,4.0,'4'):
            with self.assertRaises(ValueError):select_bundle('Go.',count=bad)
        b=select_bundle('Go.')
        with self.assertRaises(ValueError):validate_selection('generator',b['generator'][:2])
        with self.assertRaises(ValueError):validate_selection('reviewer',b['reviewer'][::-1])
        with self.assertRaises(ValueError):compile_prompt('generator','initial',profile='r2r-en',selected_ids=b['generator'][:2])
    def test_soft_weak_match_and_exact_spans(self):
        b=select_bundle('');self.assertEqual(len(b['generator']),4)
        self.assertTrue(all(t['selection_reason']=='broad_calibration' for t in b['evidence']['generator']['selected']))
        q='Enter the hall and choose the first room to the left of the staircase.'
        self.assertIn('entity_frame',signals(q));self.assertFalse({'KEEP','SPLIT'}&set(signals(q)))
    def test_index_tampering_fails_closed(self):
        index,h=teaching_index();bad=copy.deepcopy(index);bad['R2R-GEN-030']['content_sha256']='0'*64
        with patch('r2r.selection.teaching_index',return_value=(bad,h)):
            with self.assertRaises(ValueError):select_bundle('Go to the room left of the stairs.')
    def test_trace_candidate_order_has_no_set_iteration_dependence(self):
        code="import json;from r2r.selection import select_bundle;print(json.dumps(select_bundle('Walk through the hall and enter the second door on the left, then wait.'),sort_keys=True))"
        import os,sys
        results=[subprocess.check_output([sys.executable,'-B','-c',code],cwd=ROOT,env=dict(os.environ,PYTHONHASHSEED=str(n))) for n in (0,1,42)]
        self.assertEqual(results[0],results[1]);self.assertEqual(results[0],results[2])

class ClosedLoop(unittest.TestCase):
    def test_reject_false_grouping_without_text_edit_can_release(self):
        row=rows()['R2R-CORE-R06'];source=row['review_input']['original_instruction'];a=copy.deepcopy(row['expected_review']);audits=[]
        for s in a['stage_checks']:
            s=copy.deepcopy(s);s.pop('status');s.pop('source_requirement_ids');audits.append(s)
        g=dict(status='ok',subtasks=copy.deepcopy(row['review_input']['candidate']['subtasks']),stage_audit=audits,handoffs=[],issues=[])
        old=json.loads(subprocess.check_output(['git','show',EVALUATED+':reviewer/templates/R2R/core/R06_R2R-CORE-R06.json'],cwd=ROOT))
        r0=runtime_review_output(old);repair=dict(candidate=g,responses=[dict(finding_index=0,decision='reject',source_quotes=[source.strip()],reason='All source objectives and dependencies remain explicit; the proposed count preference supplies no material defect.')])
        r1=a;r1['prior_finding_reviews']=[dict(finding_index=0,status='resolved',candidate_evidence=[dict(subtask_index=0,quote=g['subtasks'][0])],explanation='The unchanged candidate already preserves the source route and final approach; the prior objection is unsupported.')]
        result,requests,pending=run(source,[g,r0,repair,r1])
        self.assertFalse(pending);self.assertEqual(len(requests),4);self.assertIsNone(result['error'])
        self.assertTrue(result['disposition'].startswith('accepted_'));self.assertEqual(result['snapshots'][0]['candidate'],result['snapshots'][1]['candidate'])
        self.assertEqual(requests[0]['selected_example_ids'],requests[2]['selected_example_ids']);self.assertEqual(requests[1]['selected_example_ids'],requests[3]['selected_example_ids'])
        self.assertNotIn('stage_audit',json.loads(requests[1]['messages'][1]['content'])['candidate'])
    def test_partially_accept_correct_diagnosis_without_extra_stop(self):
        source,bad,r0,answer,r1,_,view=partial_fixture()
        protocol.reviewer(source,dict(status='ok',subtasks=list(view.stages),issues=[]),r0,rendered_instruction=view.rendered)
        result,requests,pending=run(source,[bad,r0,answer,r1])
        self.assertFalse(pending);self.assertEqual(len(requests),4);self.assertIsNone(result['error'],result['error'])
        self.assertEqual([r['phase'] for r in requests],['initial','review','repair','recheck'])
        self.assertEqual(result['instruction'],source)
        self.assertEqual(result['snapshots'][-1]['rendered_instruction'],result['instruction'])
    def test_source_envelope_whitespace_is_not_fabricated_stage_evidence(self):
        source,bad,_,_,_,raw,view=partial_fixture()
        protocol.reviewer(source,bad,raw)
        with self.assertRaisesRegex(Exception,'Unverifiable exact quotation'):
            protocol.reviewer(source,dict(status='ok',subtasks=list(view.stages),issues=[]),raw,rendered_instruction=view.rendered)
    def test_source_limited_route_uses_existing_two_call_fallback(self):
        bank=rows();g=bank['R2R-CORE-G10'];r=bank['R2R-CORE-R10'];source=g['input']['original_instruction']
        result,requests,pending=run(source,[g['output'],r['expected_review']])
        self.assertEqual(len(requests),2);self.assertFalse(pending);self.assertEqual(result['disposition'],'fallback_unresolved');self.assertEqual(result['instruction'],source)
    def test_false_resolved_without_evidence_is_rejected(self):
        row=rows()['R2R-CORE-R06'];old=json.loads(subprocess.check_output(['git','show',EVALUATED+':reviewer/templates/R2R/core/R06_R2R-CORE-R06.json'],cwd=ROOT));prior=runtime_review_output(old)
        current=copy.deepcopy(row['expected_review']);current['prior_finding_reviews']=[dict(finding_index=0,status='resolved',candidate_evidence=[],explanation='Unsupported claim of resolution')]
        with self.assertRaises(Exception):protocol.reviewer(row['review_input']['original_instruction'],row['review_input']['candidate'],current,prior_review=prior,prior_candidate=old['review_input']['candidate'],prior_rendered_instruction='\n'.join(old['review_input']['candidate']['subtasks']))

if __name__=='__main__':unittest.main()
