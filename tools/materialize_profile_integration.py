"""One-time reviewed migration; run only on the isolated integration branch."""
from pathlib import Path
import hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
S='33d66756de8d545db001f3854194bf5d5b5a8592'
T='b69e04ddc7097b47f8d201beed2fa5e2d9ffd34e'
def git(*a):return subprocess.check_output(['git',*a],cwd=ROOT)
def read(ref,path):return git('show',ref+':'+path)
def write(path,data):
 p=ROOT/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data if isinstance(data,bytes) else data.encode())
def replace(text,old,new,count=1):
 if text.count(old)!=count:raise ValueError('Nonunique source patch: '+old[:100])
 return text.replace(old,new)
def main():
 p=ROOT/'provenance/profile_migration_inventory.json';report=json.loads(p.read_bytes())
 if report.get('materialized'):return
 if report['source_commit']!=S or report['target_commit']!=T:raise ValueError('Migration identity mismatch')
 shared_overrides={'.github/workflows/rxr-development.yml','tests/test_rxr_profile.py'}
 for row in report['differences']:
  path=row['path']
  use_target='rxr' in path.lower() and path not in shared_overrides
  if use_target:
   row['action']='preserve_target_rxr'
   continue
  if row['source']:
   write(path,read(S,path));row['action']='import_source_exact'
  else:
   (ROOT/path).unlink(missing_ok=True);row['action']='adopt_source_removal'
 # Source common compiler plus the existing target RxR dispatch; no change to R2R.
 text=read(S,'host/compile.py').decode()
 text=replace(text,'    if example.get("dataset_scope") == "R2R":',
 '    if example.get("dataset_scope") in ("RxR", "RxR_prompt_teaching_example"):\n        from host.rxr_teaching import card\n        return card(example, role, detailed, review_output=runtime_review_output)\n    if example.get("dataset_scope") == "R2R":')
 text=replace(text,"        if profile == 'r2r-en':\n            from host.r2r.selection import validate_selection", "        if profile == 'rxr-en-us':\n            from host.rxr_teaching import validate_selection\n            validate_selection(role, chosen, rows, selection_mode)\n        if profile == 'r2r-en':\n            from host.r2r.selection import validate_selection")
 text=replace(text,'                detailed = (position == 0)', '                from host.rxr_teaching import dynamic_is_detailed\n                detailed = dynamic_is_detailed(role, position)')
 write('host/compile.py',text)
 # Preserve packaged CLI/pins/configuration and all R2R dispatch improvements.
 text=read(S,'host/run.py').decode()
 text=replace(text,'            root/"host/rxr_assets.py",','            root/"host/rxr_assets.py",\n            root/"host/rxr_teaching.py",\n            root/"host/rxr_contract.py",',2)
 text=replace(text,'    events, snapshots = [], []','    runtime_protocol = protocol\n    if src.profile == "rxr-en-us":\n        from host import rxr_contract as runtime_protocol\n    events, snapshots = [], []')
 text=replace(text,'lambda out: protocol.generator(src.raw, out)','lambda out: runtime_protocol.generator(src.raw, out)')
 text=replace(text,'lambda out: protocol.feedback(src.raw, rv, out)','lambda out: runtime_protocol.feedback(src.raw, rv, out)')
 text=replace(text,'        source_payload = {"original_instruction": src.raw}', '        if src.profile == "rxr-en-us":\n            from host.rxr_teaching import validate_pair_bundle\n            validate_pair_bundle(selections, selection_mode)\n        source_payload = {"original_instruction": src.raw}')
 write('host/run.py',text)
 # Every RxR teaching call is complete, including compatibility calls requesting False.
 # Keep argument compatibility for offline builders; False never selects a summary.
 text=read(T,'host/rxr_teaching.py').decode()
 text=replace(text,'    return position < 2','    return True')
 start=text.index('def _stage_summary(');end=text.index('def validate_selection(')
 full='''def card(example, role, detailed, *, review_output):
    """Preserve every runtime output field; the legacy detail flag cannot compress."""
    if example.get('dataset_scope') not in SCOPES or example.get('language') != 'en-US':
        raise ValueError('RxR projection received foreign teaching')
    if example.get('role') != role or type(detailed) is not bool:
        raise ValueError('Invalid RxR teaching role or detail policy')
    notes = example['teaching_notes']
    if role == 'generator':
        output = example['output']
        teaching = dict(source=example['input']['original_instruction'],
                        decision=example['decision'], status=output['status'],
                        stages=output['subtasks'], handoffs=output['handoffs'],
                        issues=output['issues'], stage_evidence=output['stage_audit'])
        lesson = notes.get('case_rationale') or notes.get('reusable_rule') or notes.get('why_this_case_matters')
    elif role == 'reviewer':
        audit = review_output(example)
        teaching = dict(review_case=example['review_input'], verdict=audit['verdict'],
                        dimensions=audit['dimensions'], findings=audit['findings'],
                        coverage_evidence=audit['source_coverage'],
                        stage_checks=audit['stage_checks'], layer_checks=audit['layer_checks'],
                        handoffs=audit['handoffs'], prior_finding_reviews=audit['prior_finding_reviews'])
        lesson = notes.get('case_specific_focus') or notes.get('review_principle') or notes.get('reuse_rule')
    else:
        raise ValueError('Invalid RxR teaching role')
    if not isinstance(lesson, str) or not lesson.strip():
        raise ValueError('RxR teaching requires an actual transferable lesson')
    return deepcopy(dict(template_id=example['template_id'], teaching=teaching,
                         applicable_lesson=lesson, avoid=notes.get('anti_pattern')))


'''
 text=text[:start]+full+text[end:]
 text=text.replace('Summaries retain actual source, candidate, conditions and repair evidence.','Every Core, Dynamic and Diagnostic retains the complete runtime demonstration.').replace('# Reviewer pairs precede diagnostics, so the same first two cases are detailed.','# Every selected case is detailed, including Reviewer diagnostics.')
 write('host/rxr_teaching.py',text)
 for role in ('generator','reviewer'):
  path=f'{role}/dataset_rules/rxr_en_us.md';text=read(T,path).decode()
  if role=='generator':
   old='Teaching delivery: the first two selected Dynamic cases carry complete teaching evidence. Later cards are labelled summaries, retain the full source and candidate and their semantic evidence, and are not response objects. Fixed Core, detailed cards and summaries use teaching wrappers; always return the active phase Schema, never the wrapper or summary field names.'
   new='Teaching delivery: every selected Core and Dynamic case carries the complete source, candidate, five-element audit, handoffs and issues; no selected case is summarized or truncated. Teaching wrappers are not response objects. Always return the active phase Schema, never wrapper field names. Initial-output teaching in G1 demonstrates candidate content, not a replacement for its repair envelope.'
  else:
   old='Teaching cards are source/candidate demonstrations, not necessarily complete runtime response objects. The first two paired Dynamic cards are detailed; later summaries still preserve the actual findings, requirements, stage meanings and handoffs. Regardless of card format, return all fields of the active review Schema and never copy a teaching wrapper. A syntax-valid quote or a familiar noun does not prove entailment.'
   new='Every selected Core, paired Dynamic and Diagnostic carries its complete source/candidate demonstration and all review fields: coverage, layer checks, stage checks, dimensions, findings, handoffs and prior-finding dispositions. No selected case is summarized or truncated. The teaching wrapper is not the response object; return all fields of the active review Schema. On R1, examples with no prior findings do not replace the actual required prior-finding checks. A syntax-valid quote or a familiar noun does not prove entailment.'
  write(path,replace(text,old,new))
 # Tests affected by the explicit, authorized full-input policy.
 path='tests/test_example_injection.py';text=(ROOT/path).read_text();text=replace(text,"                        detail=is_fixed or c['template_id']==ids[0]","                        detail=True");write(path,text)
 path='tests/test_rxr_profile.py';text=(ROOT/path).read_text();text=text.replace('len(rxr["files"]), 7','len(rxr["files"]), 9').replace('len(metadata["files"]), 7','len(metadata["files"]), 9');write(path,text)
 path='tests/test_r2r_specialization.py';text=(ROOT/path).read_text();text=text.replace('            "host/rxr_assets.py",','            "host/rxr_assets.py",\n            "host/rxr_teaching.py",\n            "host/rxr_contract.py",');write(path,text)
 # README adopts source paths/settings while keeping target branch identity and RxR entry.
 text=read(S,'README.md').decode();text=text.replace('# LLM-decompose-v6.6.4','# LLM-decompose-v6.6.5',1)
 text=text.replace('## 入口文档','## 当前双数据集集成\n\n通用配置与 R2R 资产完整采用源分支固定提交；保留本分支 RxR 专属规则、已修复模板和校验。所有选中的动态模板均完整输入，不再压缩。当前验收以 `docs/PROFILE_INTEGRATION.md` 与 `provenance/profile_integration_validation.json` 为准；下方旧报告的数字和隔离基准属于各自历史阶段。\n\n## 入口文档\n\n- `docs/PROFILE_INTEGRATION.md`：迁移边界、CLI、完整教学和双基线验收。\n- `docs/RXR_REFINEMENT.md`：此前 RxR 语义与证据修复记录，完整教学以当前集成说明为准。',1)
 write('README.md',text)
 for path in ('docs/RXR_REFINEMENT.md','docs/RXR_ROLE_HIERARCHY.md','docs/RXR_TEACHING_REPAIR.md','docs/RXR_FINAL_CHECKS.md'):
  text=(ROOT/path).read_text();write(path,'> Historical scoped record. Current full-Dynamic policy, common/R2R integration and comparison baselines are specified in `PROFILE_INTEGRATION.md`. Earlier first-two/summary and frozen-old-R2R claims are not the current combined contract.\n\n'+text)
 # Update rule-byte pins only; prompt expectations require separately inspected measurements.
 path='provenance/rxr_role_conversion.json';data=json.loads((ROOT/path).read_bytes())
 def update(obj):
  if isinstance(obj,dict):
   for k,v in list(obj.items()):
    if isinstance(v,str):
     for role in ('generator','reviewer'):
      path=f'{role}/dataset_rules/rxr_en_us.md';old=hashlib.sha256(read(T,path)).hexdigest()
      if v==old:obj[k]=hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
    else:update(v)
  elif isinstance(obj,list):
   for x in obj:update(x)
 update(data);write(path,json.dumps(data,ensure_ascii=False,indent=2)+'\n')
 for row in report['differences']:
  path=row['path'];cur=ROOT/path
  row['integrated_sha256']=hashlib.sha256(cur.read_bytes()).hexdigest() if cur.is_file() else None
  if cur.is_file() and row['source'] and cur.read_bytes()!=read(S,path) and row['action']=='import_source_exact':row['action']='source_with_reviewed_profile_reconciliation'
 report['materialized']=True;write('provenance/profile_migration_inventory.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'materialized':True,'source':S,'target':T,'difference_count':len(report['differences'])}))
if __name__=='__main__':main()
