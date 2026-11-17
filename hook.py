"""Optional instruction projection and response fences over the native Goal hook.
No model call, action parser, queue, simulator, reasoning or clock implementation.
"""
import copy,hashlib
from goalAdapter.native_goal_hook import NativeGoalHook
from ..base.contracts import ContractError
from .context import render_instruction
class LLMContextGoalHook(NativeGoalHook):
 def __init__(self,*args,context_mode,context_policy,**kwargs):
  super().__init__(*args,**kwargs)
  if context_mode not in ('A','B','C') or not isinstance(context_policy,str) or not context_policy.strip():raise ContractError('LLM_CONTEXT_CONFIG')
  self.context_mode=context_mode;self.context_policy=context_policy
  self.response_binding=None;self.consumed_responses=set();self.request_bindings={}
 def begin(self,episode):
  fresh=self.goal is None
  super().begin(episode)
  if fresh:self.response_binding=None;self.consumed_responses=set();self.request_bindings={}
 def current_text(self):
  current=super().current_text();snapshot=self.goal.snapshot();state=snapshot['state']
  if self.goal._rule_assembly.get('original_instruction_fallback') is True:
   if len(self.goal._rule_assembly['units'])!=1 or current!=self.goal.task.raw_text:raise ContractError('LLM_FALLBACK_NOT_ORIGINAL')
   self.log('ORIGINAL_INSTRUCTION_FALLBACK',mode=self.context_mode,text_sha256=hashlib.sha256(current.encode()).hexdigest(),completion_source='model',externally_verified=False)
   return current
  units={u['unit_id']:u for u in self.goal._rule_assembly['units']}
  completed=[units[t['unit_id']]['text'] for t in state['todos'] if t['status']=='completed']
  text=render_instruction(self.context_mode,current,completed,self.goal.task.raw_text,self.context_policy)
  if self.goal.snapshot()!=snapshot:raise ContractError('LLM_CONTEXT_STATE_CHANGED')
  self.log('INSTRUCTION_CONTEXT_BINDING',mode=self.context_mode,current_todo_id=self.goal.current['todo_id'],revision=snapshot['revision'],completed_todo_ids=[t['todo_id'] for t in state['todos'] if t['status']=='completed'],text_sha256=hashlib.sha256(text.encode()).hexdigest(),text=text,externally_verified=False)
  return text
 def before_model_call(self,call_id):
  if call_id in self.request_bindings:raise ContractError('LLM_REQUEST_ID_REUSED')
  super().before_model_call(call_id);s=self.goal.snapshot()
  b=dict(task_key=self.goal.task.task_key,assembly_sha256=s['state']['assembly_sha256'],todo_id=self.goal.current['todo_id'],revision=s['revision'],request_id=call_id)
  self.response_binding=b;self.request_bindings[call_id]=copy.deepcopy(b)
 def _check_response(self,call_id):
  b=self.response_binding
  if b is None or b['request_id']!=call_id or call_id in self.consumed_responses:raise ContractError('LLM_STALE_OR_DUPLICATE_RESPONSE')
  s=self.goal.snapshot();current=self.goal.current
  if current is None or b!=dict(task_key=self.goal.task.task_key,assembly_sha256=s['state']['assembly_sha256'],todo_id=current['todo_id'],revision=s['revision'],request_id=call_id):raise ContractError('LLM_RESPONSE_SCOPE')
 def reason_completed(self,call_id,body):
  self._check_response(call_id)
  changed=super().reason_completed(call_id,body);self.consumed_responses.add(call_id)
  return changed
 def model_stop(self,call_id,body):
  self._check_response(call_id)
  changed=super().model_stop(call_id,body);self.consumed_responses.add(call_id)
  return changed
 def observe_committed(self,binding):
  # Notification after a native transaction: view refresh only, never commit.
  if self.request_bindings.get(binding.get('request_id'))!=binding:raise ContractError('LLM_COMMITTED_SOURCE')
  s=self.goal.snapshot()
  if binding['task_key']!=self.goal.task.task_key or binding['assembly_sha256']!=s['state']['assembly_sha256'] or s['revision']<=binding['revision']:raise ContractError('LLM_COMMITTED_SCOPE')
  if not any(x['todo_id']==binding['todo_id'] and x['source_call_id']==binding['request_id'] for x in s['state']['accepted_results']):raise ContractError('LLM_COMMITTED_NOT_RECORDED')
  return copy.deepcopy(self.goal.current)
