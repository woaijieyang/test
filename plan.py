"""Source-bound reviewed LLM text. Not a semantic verifier or progress store."""
import copy,hashlib,json
from ..base.contracts import ContractError,strict_json,exact_fields
SCHEMA='llm_task_units/1'
def sha(text):return hashlib.sha256(text.encode('utf-8')).hexdigest()
def _units(key,candidate_hash,candidate,review):
 return [dict(unit_id='llm-task-'+sha(key+':'+candidate_hash+':'+str(i))[:24],
  text=text,source_spans=[],context_spans=[],source_quotes=list(review['stage_checks'][i]['source_quotes']),
  assembly_rule='REVIEWED_LLM_TEXT_NOT_SOURCE_SLICE',issues=[],**{'[skill]':'none'}) for i,text in enumerate(candidate['subtasks'])]
def _check_source(raw,candidate_json,cm,review_json,rm):
 if not isinstance(raw,str) or not raw.strip():raise ContractError('LLM_EMPTY_SOURCE')
 c=strict_json(candidate_json);review=strict_json(review_json)
 exact_fields(c,('status','subtasks','issues'))
 if c['status']!='ok' or not isinstance(c['subtasks'],list) or not c['subtasks'] or c['issues']!=[] or any(not isinstance(s,str) or not s.strip() for s in c['subtasks']):raise ContractError('LLM_CANDIDATE_NOT_ACCEPTABLE')
 for meta in (cm,rm):
  if meta.get('instruction_sha256')!=sha(raw) or meta.get('candidate_sha256')!=sha(candidate_json):raise ContractError('LLM_SOURCE_RECEIPT_BINDING')
 if not cm.get('record_id') or cm['record_id']!=rm.get('record_id'):raise ContractError('LLM_RECORD_BINDING')
 if (cm.get('model'),cm.get('reasoning_effort')) not in (('gpt-6.1-sol','medium'),('gpt-5.6-sol','high')):raise ContractError('LLM_UNAPPROVED_MODEL')
 if not cm.get('actual_model_metadata_source') or not cm.get('child_thread_id'):raise ContractError('LLM_HOST_RECEIPT_MISSING')
 if rm.get('review_owner')!='primary' or not rm.get('primary_thread_id') or rm['primary_thread_id']==cm['child_thread_id']:raise ContractError('LLM_PRIMARY_REVIEW_REQUIRED')
 exact_fields(review,('verdict','findings','stage_checks'))
 if review['verdict']!='pass' or review['findings']!=[] or not isinstance(review['stage_checks'],list):raise ContractError('LLM_PRIMARY_NOT_PASS')
 checks=review['stage_checks']
 if [x.get('subtask_index') for x in checks]!=list(range(len(c['subtasks']))):raise ContractError('LLM_REVIEW_COVERAGE')
 for row in checks:
  exact_fields(row,('subtask_index','entry_context','required_history','completion_condition','carryover_requirements','source_quotes'))
  if not isinstance(row['completion_condition'],str) or not row['completion_condition'].strip():raise ContractError('LLM_REVIEW_COMPLETION')
  if not isinstance(row['source_quotes'],list) or not row['source_quotes'] or any(not isinstance(q,str) or not q or q not in raw for q in row['source_quotes']):raise ContractError('LLM_REVIEW_SOURCE_QUOTE')
  for f in ('required_history','carryover_requirements'):
   if not isinstance(row[f],list) or any(not isinstance(x,str) for x in row[f]):raise ContractError('LLM_REVIEW_FIELD')
 return c,review
def build(task_key,raw,candidate_json,candidate_meta,review_json,review_meta):
 if not isinstance(task_key,str) or not task_key:raise ContractError('LLM_TASK_KEY')
 c,review=_check_source(raw,candidate_json,candidate_meta,review_json,review_meta)
 a=dict(schema=SCHEMA,task_key=task_key,raw_instruction=raw,instruction_sha256=sha(raw),
  candidate_json=candidate_json,candidate_sha256=sha(candidate_json),candidate_meta=copy.deepcopy(candidate_meta),
  review_json=review_json,review_sha256=sha(review_json),review_meta=copy.deepcopy(review_meta),
  units=_units(task_key,sha(candidate_json),c,review),semantic_completeness_proven=False,
  source_policy='Original source retained; generated text bound to raw candidate and primary review, not fictitious character spans')
 return validate(a)
def validate(a):
 exact_fields(a,('schema','task_key','raw_instruction','instruction_sha256','candidate_json','candidate_sha256','candidate_meta','review_json','review_sha256','review_meta','units','semantic_completeness_proven','source_policy'))
 if a['schema']!=SCHEMA or not isinstance(a['task_key'],str) or not a['task_key'] or a['semantic_completeness_proven'] is not False:raise ContractError('LLM_ASSEMBLY_IDENTITY')
 if a['instruction_sha256']!=sha(a['raw_instruction']) or a['candidate_sha256']!=sha(a['candidate_json']) or a['review_sha256']!=sha(a['review_json']):raise ContractError('LLM_ASSEMBLY_HASH')
 c,review=_check_source(a['raw_instruction'],a['candidate_json'],a['candidate_meta'],a['review_json'],a['review_meta'])
 if a['units']!=_units(a['task_key'],a['candidate_sha256'],c,review):raise ContractError('LLM_UNITS_CHANGED')
 return a
