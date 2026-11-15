"""Deterministic proofs for plumbing, not semantic model evaluation."""
import copy,json,sys,hashlib,unittest
from pathlib import Path
from adapter.source import Source,from_record
from renderer.freeze import freeze,unchanged
from host.run import run_record,receipt_for_navigation
from host.compile import ROOT,compile_prompt
from host.protocol import generator,reviewer,feedback
from shared.identity import ContractError,canonical,text_hash
from evaluation.paired import summarize

CASES=json.loads((ROOT/'evaluation/source_cases.json').read_bytes());RR={c['id']:c for c in CASES if c['dataset']=='R2R'}
TEACH=[json.loads(p.read_bytes()) for p in sorted((ROOT/'templates').glob('[0-9]*.json'))]
PINS={r:{'model':'local-fixture','effort':'not-a-model-run'} for r in ('generator','reviewer')}
def src(s,ds='R2R',lang='en'):return Source('fixture',ds,lang,s)
def ok(*rows):return {'status':'ok','subtasks':list(rows),'issues':[]}
def limited(s):return {'status':'needs_review','subtasks':[],'issues':[{'code':'UNSUPPORTED_COMPLETION','source_quote':s,'problem':'No supported ending'}]}
def pass_rev(s,t):return {'verdict':'pass','dimensions':{k:'pass' for k in ['fidelity','closure_handoff','segmentation_adequacy']},'findings':[],'stage_checks':[{'subtask_index':0,'entry_context':'Actual episode start','required_history':['Follow the stated process'],'completion_condition':'Reach the stated endpoint','completion_basis':'explicit_event','source_quotes':[s],'candidate_quotes':[t],'completion_quote':t,'carryover_requirements':[]}],'handoffs':[]}
def defect(s,t,empty=False,lim=False):
    v=pass_rev(s,t);v['verdict']='unresolved' if lim else 'revise';v['dimensions']['closure_handoff']='source_limited' if lim else 'issue';v['findings']=[{'code':'UNSUPPORTED_COMPLETION','check_id':'C08','dimension':'closure_handoff','subtask_indices':[] if empty else [0],'source_quote':s,'candidate_evidence':[] if empty else [{'index':0,'quote':t}],'problem':'Fixture only: missing end','consequence':'No supported finish','repair_option':'Consider the source trigger.'}]
    if empty:v['stage_checks']=[]
    else:v['stage_checks'][0].update(completion_condition=None,completion_basis='unspecified',completion_quote=None)
    return v

def replay(outputs, sink=None):
    def invoke(req):
        if sink is not None:sink.append(copy.deepcopy(req))
        out=outputs.pop(0);return {'output':out,'receipt':{'model':'local-fixture','effort':'not-a-model-run','request_id':f'offline-{req["phase"]}'}}
    return invoke

class Checks(unittest.TestCase):
 def test_manifest(self):
    j=json.loads((ROOT/'provenance/lineage.json').read_bytes());self.assertEqual(j['input_manifest_checks'],19)
    for k,v in j['bases'].items():self.assertEqual(hashlib.sha256((ROOT/f'provenance/v13/{k}.md').read_bytes()).hexdigest(),v['original_sha256'])
 def test_all_templates(self):
    self.assertEqual(len(TEACH),15)
    for e in TEACH:
        generator(e['source'],e['acceptable']);generator(e['source'],e['contrast']);self.assertIn(e['source_quote'],e['source']);self.assertTrue(any(e['candidate_contrast_quote'] in t for t in e['contrast']['subtasks']))
 def test_compiled_reproducible(self):
    for r,p,f in [('generator','initial','compiled.txt'),('reviewer','review','compiled.txt'),('generator','repair','compiled_repair.txt')]:self.assertEqual(compile_prompt(r,p)[0].encode(),(ROOT/r/f).read_bytes());self.assertIn((ROOT/f'{r}/prompt.md').read_text(),compile_prompt(r,p)[0])
 def test_record_input(self):self.assertEqual(from_record(dict(task_key='K',dataset='rxr',language='en-US',instruction={'instruction_text':'  Hi.\n'})).raw,'  Hi.\n')
 def test_bad_profile_blank_and_conflicts(self):
    for f in [lambda:src(' A ','RxR','en-IN'),lambda:src(' \t\n'),lambda:from_record(dict(dataset='R2R',task_key='X',language='en',original_instruction='a',instruction_text='b')),lambda:from_record(dict(dataset='r2r',task_key='K',language='en',original_instruction='abc',original_instruction_sha256='fake'))]:
        with self.assertRaises(ContractError):f()
 def test_format_scopes(self):
    f=src(' A  B\nC.  \n','RxR','en-US').features();self.assertEqual((f['body_LF'],f['suffix_LF'],f['body_double_space'],f['prefix'],f['suffix']),(True,True,True,' ','  \n'));self.assertFalse(src('A.  \n').features()['body_double_space'])
 def test_real_boundary(self):
    for i in ('2','53','700'):
        c=RR[i];v=freeze(src(c['source']),c['current_subtasks']);self.assertEqual(v.mode,'BOUNDARY_ONLY');self.assertEqual(v.rendered,c['source'][:0]+ '\n'.join(c['current_subtasks'])+' ')
    self.assertIn('walk  into',freeze(src(RR['2']['source']),RR['2']['current_subtasks']).rendered)
 def test_exact_native(self):
    s=src(RR['188']['source']);self.assertIn('\r\n',s.raw);self.assertEqual(unchanged(s).rendered.encode(),s.raw.encode());self.assertEqual(freeze(s,[s.raw]).rendered,s.raw)
 def test_native_internal_not_new_stage(self):
    s=src(' \tExit.\r\nTurn right.  Wait.\n');v=freeze(s,['Exit.\r\nTurn right.','Wait.']);self.assertEqual(v.rendered,' \tExit.\r\nTurn right.\nWait.\n');self.assertEqual(len(json.loads(v.ledger_json)['cuts']),1);self.assertEqual(len(v.stages),2)
 def test_zero_width_delimiter(self):
    v=freeze(src('Exit.Turn left. '),['Exit.','Turn left.']);self.assertEqual(json.loads(v.ledger_json)['cuts'][0]['old'],'')
 def test_split_word(self):
    with self.assertRaises(ContractError):freeze(src('Walk to door.'),['Wa','lk to door.'])
 def test_single_edited_not_erased(self):
    e=TEACH[5];v=freeze(src(e['source']+' '),e['acceptable']['subtasks']);self.assertEqual(v.mode,'ASSEMBLED_SINGLE');self.assertTrue(v.rendered.endswith(' '));self.assertNotEqual(v.rendered,e['source']+' ')
 def test_recovery_of_copy_space(self):
    v=freeze(src('Turn  right and walk towards the door. When you reach it, stop.'),['Turn right and walk towards the door until you reach it, then stop.']);self.assertIn('Turn  right',v.rendered);self.assertEqual(v.mode,'ASSEMBLED_SINGLE');self.assertIn('EDIT',v.ledger_json)
 def test_move_provenance(self):
    v=freeze(src('Pass the mosaic. First climb  four steps.'),['First climb four steps.','Pass the mosaic.']);self.assertIn('climb  four steps',v.rendered);ev=json.loads(v.ledger_json)['events'];self.assertTrue(any(x['op']=='MOVE' for x in ev))
 def test_no_invented_double_or_lf(self):
    for t in ['Turn\nright, stop.','Turn right and  hover nearby.','Turn right and hover\\nnow.']:
        with self.assertRaises(ContractError):freeze(src('Turn right, wait.'),[t])
 def test_edit_seam(self):
    s=src('Go near the door. Wait by the table.');v=freeze(s,['Go near the door, then wait beside the table.']);self.assertTrue(any(x['op']=='EDIT_SEAM' for x in json.loads(v.ledger_json)['events']))
 def test_ambiguous_no_guessed_span(self):
    s=src('Pass the desk. Pass the desk.');v=freeze(s,['Pass the desk and wait.']);e=[x for x in json.loads(v.ledger_json)['events'] if x.get('alternatives')];self.assertTrue(e);self.assertTrue(all(x['src'] is None and x['op']=='EDIT' for x in e))
 def test_ambiguous_whitespace(self):
    with self.assertRaises(ContractError):freeze(src('Pass the desk. Pass  the desk.'),['Pass the desk and wait.'])
 def test_native_delimiter_choice(self):
    s=src('Go.\r\nWait. ');v=freeze(s,['Go.','Wait.']);self.assertEqual(json.loads(v.ledger_json)['cuts'][0]['old'],'\r\n');self.assertEqual(freeze(s,['Go.','Wait.'],' ').rendered,'Go. Wait. ')
 def test_unedited_rxr_unicode(self):
    s=src(' You’re by the door.\n','RxR','en-US');self.assertEqual(unchanged(s).rendered.encode(),s.raw.encode());self.assertEqual(s.features()['non_ascii'],['U+2019'])
 def test_role_two_calls_and_identity(self):
    s='Walk to the exit. ';a=run_record(src(s),replay([ok(s),pass_rev(s,s)]),pins=PINS);self.assertEqual((len(a['calls']),a['disposition'],a['instruction']),(2,'accepted_source_exact',s));self.assertNotIn('sr',json.loads(a['calls'][1]['request']['messages'][1]['content']))
 def test_feedback_and_fresh_recheck(self):
    s='Walk to the gate and wait.';t='Walk to the gate.';ans={'candidate':ok(s),'responses':[{'finding_index':0,'decision':'partially_accept','source_quotes':[s],'reason':'Restore wait; no added crossing.'}]};a=run_record(src(s),replay([ok(t),defect(s,t),ans,pass_rev(s,s)]),pins=PINS);self.assertEqual(a['disposition'],'accepted_source_exact');self.assertEqual([x['phase'] for x in a['calls']],['initial','review','repair','recheck']);v=json.loads(a['calls'][-1]['request']['messages'][1]['content']);self.assertEqual(set(v),{'candidate','original_instruction','rendered_instruction'});self.assertNotEqual(a['calls'][1]['reviewed_snapshot'],a['calls'][-1]['reviewed_snapshot'])
 def test_rebut_without_new_text(self):
    s='Wait at the exit doors.';init=ok(s);rv=defect(s,s);ans={'candidate':init,'responses':[{'finding_index':0,'decision':'reject','source_quotes':[s],'reason':'No action of exiting is stated.'}]};a=run_record(src(s),replay([init,rv,ans,pass_rev(s,s)]),pins=PINS);self.assertEqual(a['disposition'],'accepted_source_exact');self.assertEqual(a['snapshots'][0]['bound_candidate'],a['snapshots'][1]['bound_candidate'])
 def test_two_role_conflict_exact_fallback(self):
    s='Approach the door. ';init=ok(s);rv=defect(s,s,lim=True);ans={'candidate':init,'responses':[{'finding_index':0,'decision':'reject','source_quotes':[s],'reason':'Fixture rebuttal.'}]};a=run_record(src(s),replay([init,rv,ans,rv]),pins=PINS);self.assertEqual(a['disposition'],'fallback_unresolved');self.assertEqual(len(a['calls']),4);self.assertEqual(a['instruction'],s)
 def test_needs_review_distinct_from_exact(self):
    s=RR['188']['source'];a=run_record(src(s),replay([limited(s),defect(s,s,empty=True,lim=True)]),pins=PINS);self.assertEqual(a['disposition'],'fallback_unresolved');self.assertEqual(a['render_mode'],'SOURCE_EXACT');self.assertEqual(a['instruction'].encode(),s.encode())
 def test_bad_quoted_candidate(self):
    s='Walk to the gate.';r=pass_rev(s,s);r['stage_checks'][0]['completion_quote']='imaginary room';a=run_record(src(s),replay([ok(s),r]),pins=PINS);self.assertEqual(a['disposition'],'fallback_technical')
 def test_missing_handoff(self):
    s='Go up. Wait.';r=pass_rev(s,'Go up.');r['stage_checks']*=2;r['stage_checks'][1]=dict(r['stage_checks'][1],subtask_index=1)
    with self.assertRaises(ContractError):reviewer(s,ok('Go up.','Wait.'),r)
 def test_empty_pass_blocked(self):
    s='Turn there.';r=pass_rev(s,s);r['stage_checks']=[]
    with self.assertRaises(ContractError):reviewer(s,limited(s),r)
 def test_native_binding(self):
    s='Wait by the chair. ';r=run_record(src(s),replay([ok(s),pass_rev(s,s)]),pins=PINS);kw=dict(full_prompt_utf8=('Human:'+s).encode(),input_ids=[1,4,9],tokenizer_id='fixture',template_id='fixture',image_ids=['fixture-image'],truncated=False,request_id='fixture');v=receipt_for_navigation(r,instruction_seen=s,**kw);self.assertEqual(v['instruction_sha256'],text_hash(s));
    with self.assertRaises(ContractError):receipt_for_navigation(r,instruction_seen=s.strip(),**kw)
 def test_paired_denominator(self):
    a=summarize([{'task_key':str(i),'base':{'sr':b},'candidate':{'sr':c},'disposition':d} for i,(b,c,d) in enumerate([(1,1,'fallback_unresolved'),(0,1,'accepted_candidate'),(1,0,'accepted_candidate')])]);self.assertEqual((a['n'],a['recoveries'],a['regressions'],a['sr_delta_pp']),(3,1,1,0))
 def test_model_change_is_technical(self):
    a=run_record(src('Go.'),lambda req:{'receipt':{'model':'other','effort':'none','request_id':'x'},'output':ok('Go.')},pins=PINS);self.assertEqual(a['disposition'],'fallback_technical')

 def test_all_supplied_smoke_cases(self):
    from evaluation.smoke24 import smoke
    x=smoke();self.assertEqual(len(x),24);self.assertEqual(sum(r['dataset']=='R2R' for r in x),17)
 def test_merged_cut_replacement_ledger(self):
    s=src('Start at the clock.  Go to the hall. Stop at the lamp.');v=freeze(s,['Start at the clock.','Go to the hall. Wait at the lamp.']);self.assertEqual(v.mode,'ASSEMBLED_MULTI');self.assertEqual(json.loads(v.ledger_json)['cuts'][0]['old'],'  ')
 def test_frame_semantics_not_inferred_by_renderer(self):
    s='Walk toward the cupboard.';x=defect(s,s,lim=True);reviewer(s,ok(s),x);x['stage_checks'][0]['completion_condition']='At the cupboard'
    with self.assertRaises(ContractError):reviewer(s,ok(s),x)
 def test_missed_focus_not_semantic_contradiction(self):
    s=TEACH[10]['source'];v=pass_rev(s,s);v['verdict']='revise';v['dimensions']['segmentation_adequacy']='issue';v['findings']=[{'code':'MISSED_OBJECTIVE','dimension':'segmentation_adequacy','check_id':'C10','subtask_indices':[0],'source_quote':'walk to the iron gate, turn left into the courtyard','candidate_evidence':[{'index':0,'quote':'walk to the iron gate, turn left into the courtyard'}],'problem':'Separate reached gate and courtyard goal buried','consequence':'At the gate the agent begins a different maneuver, into the courtyard','repair_option':'Separate at gate, start courtyard leg from that same gate'}];reviewer(s,ok(s),v);self.assertEqual(v['dimensions']['fidelity'],'pass')
 def test_roster_required_for_evaluation(self):
    with self.assertRaises(ContractError):summarize([{'task_key':'x','disposition':'accepted','base':{'sr':1},'candidate':{'sr':1}}],['x','y'])
