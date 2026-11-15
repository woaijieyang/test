from host.template_selector import library, source, PROFILES, select_examples
from test_runtime_contract_v2 import SOURCE, generator_candidate, reviewer_output
def combo(repaired=True,r1=False):
 g=generator_candidate(repaired)
 return g,reviewer_output(g,repaired=repaired,r1=r1)
def turn(g,r,decision='accept'):
 return dict(candidate=g,responses=[dict(finding_index=i,decision=decision,source_quotes=[SOURCE],reason='Check against full source.') for i in range(len(r['findings']))])
from host import protocol
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
     from jsonschema import Draft202012Validator
     from referencing import Registry,Resource
     schemas={f.name:json.loads(f.read_bytes()) for f in (ROOT/'shared/template_schemas_v1_5_2').glob('*.json')}
     registry=Registry().with_resources((name,Resource.from_contents(data)) for name,data in schemas.items())
     for role in ('generator','reviewer'):
         validator=Draft202012Validator(schemas[role+'_template.schema.json'],registry=registry)
         for profile in PROFILES:
             for row in library(role,profile):
                 validator.validate(row)
 def test_compiled_reproducible(self):
     for profile in PROFILES:
         for role,phase,prefix in [('generator','initial','compiled_'),('generator','repair','compiled_repair_'),('reviewer','review','compiled_')]:
             prompt,_=compile_prompt(role,phase,profile=profile)
             self.assertEqual(prompt.encode(),(ROOT/role/(prefix+profile+'.txt')).read_bytes())
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
     v=freeze(src('Walk to door.'),['Wa','lk to door.'])
     self.assertEqual(v.rendered,'Wa\nlk to door.')
 def test_single_edited_not_erased(self):
     v=freeze(src(' Walk to the hall. '),['Proceed into the hall.'])
     self.assertEqual(v.mode,'ASSEMBLED_SINGLE')
     self.assertEqual(v.rendered,' Proceed into the hall. ')
 def test_unchanged_sentence_recovers_source_spaces(self):
     v=freeze(src('Turn  right. Stop at the door.'),['Turn right.','Stop by the closed door.'])
     self.assertEqual(v.rendered,'Turn  right.\nStop by the closed door.')
     self.assertIn('EDIT',v.ledger_json)
 def test_move_provenance(self):
    v=freeze(src('Pass the mosaic. First climb  four steps.'),['First climb four steps.','Pass the mosaic.']);self.assertIn('climb  four steps',v.rendered);ev=json.loads(v.ledger_json)['events'];self.assertTrue(any(x['op']=='MOVE' for x in ev))
 def test_rewritten_stage_retains_generator_whitespace(self):
     for candidate in ['Turn\nright, stop.','Turn right and  hover nearby.',r'Turn right and hover\nnow.']:
         self.assertEqual(freeze(src('Turn right, wait.'),[candidate]).rendered,candidate)
 def test_edit_seam(self):
     v=freeze(src('Go near the door. Wait by the table.'),['Go near the door, then wait beside the table.'])
     self.assertEqual(v.rendered,'Go near the door, then wait beside the table.')
     self.assertIn('EDIT',v.ledger_json)
 def test_ambiguous_no_guessed_span(self):
     v=freeze(src('Pass the desk. Pass the desk.'),['Pass the desk.','Wait here.'])
     events=json.loads(v.ledger_json)['events']
     self.assertTrue(any(e.get('alternatives') and e['src'] is None for e in events))
 def test_ambiguous_whitespace(self):
     self.assertEqual(freeze(src('Pass the desk. Pass  the desk.'),['Pass the desk and wait.']).rendered,'Pass the desk and wait.')
 def test_native_delimiter_choice(self):
    s=src('Go.\r\nWait. ');v=freeze(s,['Go.','Wait.']);self.assertEqual(json.loads(v.ledger_json)['cuts'][0]['old'],'\r\n');self.assertEqual(freeze(s,['Go.','Wait.'],' ').rendered,'Go. Wait. ')
 def test_unedited_rxr_unicode(self):
    s=src(' You’re by the door.\n','RxR','en-US');self.assertEqual(unchanged(s).rendered.encode(),s.raw.encode());self.assertEqual(s.features()['non_ascii'],['U+2019'])
 def test_role_two_calls_and_identity(self):
     g,r=combo()
     sink=[]
     out=run_record(Source('test','R2R','en',SOURCE),replay([g,r],sink),pins=PINS)
     self.assertEqual(out['disposition'],'accepted_candidate',out.get('error'))
     self.assertEqual(len(sink),2)
     self.assertEqual(out['instruction'],json.loads(sink[-1]['messages'][1]['content'])['rendered_instruction'])
     self.assertIsNone(out['diagnostic'])
 def test_feedback_and_fresh_recheck(self):
     g,r=combo(False); new,r1=combo(True,True);sink=[]
     out=run_record(Source('test','R2R','en',SOURCE),replay([g,r,turn(new,r,'partially_accept'),r1],sink),pins=PINS)
     self.assertEqual(out['disposition'],'accepted_candidate',out.get('error'))
     self.assertEqual([req['phase'] for req in sink],['initial','review','repair','recheck'])
     ctx=json.loads(sink[-1]['messages'][1]['content'])
     self.assertEqual(ctx['prior_review'],r)
     self.assertEqual(ctx['prior_rendered_instruction'],out['snapshots'][0]['rendered_instruction'])
     self.assertNotEqual(out['snapshots'][0]['bound_candidate'],out['snapshots'][1]['bound_candidate'])
 def test_rebut_without_new_text(self):
     g,rv=combo(True,True)
     _,r=combo(False)
     r['findings'][0]['candidate_evidence']=[dict(subtask_index=1,quote='go down the hall')]
     r['findings'][0]['repair']['instruction']='Add a stop at the kitchen exit.'
     r['source_coverage']=copy.deepcopy(rv['source_coverage'])
     for check,stage in zip(r['stage_checks'],g['stage_audit']):
         for key in ('entry','target','process','ending','conditions'):check[key]=copy.deepcopy(stage[key])
     r['handoffs']=[dict(g['handoffs'][0],status='gap')]
     out=run_record(src(SOURCE),replay([g,r,turn(g,r,'reject'),rv]),pins=PINS)
     self.assertEqual(out['disposition'],'accepted_candidate',out.get('error'))
     self.assertEqual(out['snapshots'][0]['bound_candidate'],out['snapshots'][1]['bound_candidate'])
 def test_two_role_conflict_exact_fallback(self):
     g,r=combo(False); r1=copy.deepcopy(r);r1['prior_finding_reviews']=[dict(finding_index=0,status='unresolved',candidate_evidence=[],explanation='Previous issue persists.')]
     out=run_record(src(SOURCE),replay([g,r,turn(g,r,'reject'),r1]),pins=PINS)
     self.assertEqual(out['disposition'],'fallback_unresolved_after_repair')
     self.assertEqual(out['instruction'],SOURCE)
     self.assertEqual(len(out['calls']),4)
 def test_needs_review_distinct_from_exact(self):
     s='Go there. ';g=limited(s);g.update(stage_audit=[],handoffs=[])
     _,r=combo(False);f=r['findings'][0];f.update(code='SOURCE_AMBIGUITY',affected_subtask_indices=[],source_quote='there',source_requirement_ids=['SRC-02'],candidate_evidence=[])
     f['repair']['affected_subtask_indices']=[]
     r.update(verdict='unresolved',stage_checks=[],handoffs=[],source_coverage=[dict(requirement_id='SRC-02',source_quote='there',requirement='Determine the referent.',candidate_evidence=[],status='requires_review')])
     r['dimensions']['source_fidelity']='source_limited'
     out=run_record(src(s),replay([g,r]),pins=PINS)
     self.assertEqual(out['disposition'],'fallback_unresolved',out.get('error'))
     self.assertEqual(out['instruction'],s)
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
     g,r=combo()
     protocol.reviewer(SOURCE,g,r)
     r['stage_checks'][0]['ending']['candidate_quotes']=['a new invented arrival']
     with self.assertRaises(ContractError):protocol.reviewer(SOURCE,g,r)
 def test_missed_focus_not_semantic_contradiction(self):
     g,r=combo(False)
     r['dimensions'].update(source_fidelity='pass',segmentation_adequacy='issue')
     r['findings'][0].update(code='UNDERSEGMENTED',dimension='segmentation_adequacy')
     protocol.reviewer(SOURCE,g,r)
     self.assertEqual(r['dimensions']['source_fidelity'],'pass')
 def test_roster_required_for_evaluation(self):
    with self.assertRaises(ContractError):summarize([{'task_key':'x','disposition':'accepted','base':{'sr':1},'candidate':{'sr':1}}],['x','y'])
