"""Opt-in learned Moment/Recent-4 runtime; historical HAMLETRuntime is untouched."""
from __future__ import annotations
import json
from collections import deque
from pathlib import Path
import torch
from transformers.generation.logits_process import LogitsProcessorList
from awarevln_memory.training.artifacts import digest,identity,require_clean_encoding_dtype
from awarevln_memory.training.checkpoints import load_modules,check_files
from awarevln_memory.training.datasets import action_code
from .model import _ForceFirstGeneratedToken


class RecentState:
    def __init__(self):self.reset(None)
    def reset(self,episode):self.episode=episode;self.events=deque(maxlen=3);self.last_call=0
    def before(self,episode,call_id,current):
        if self.episode!=str(episode):self.reset(str(episode))
        if type(call_id) is not int or call_id<=self.last_call:raise ValueError('policy calls must increase within an episode')
        by_call={e['call_id']:e for e in self.events}
        past=[];valid=[];actions=[]
        for t in range(call_id-3,call_id):
            e=by_call.get(t);valid.append(e is not None)
            past.append(e['moment'].to(current.device) if e else torch.zeros_like(current))
            actions.append(action_code(e['executed_actions']) if e else 4)
        return (torch.stack(past)[None],torch.tensor([valid],device=current.device),
                torch.tensor([[3,2,1,0]],device=current.device),torch.tensor([actions+[4]],device=current.device))
    def commit(self,call_id,current):
        if call_id<=self.last_call:raise ValueError('duplicate commit')
        self.events.append({'call_id':call_id,'moment':current.detach().clone(),'executed_actions':[]})
        self.last_call=call_id
    def executed(self,action):
        action_code([action])
        if self.events:self.events[-1]['executed_actions'].append(action)


def bundle_identity(root,bundle):
    root=Path(root).resolve();bundle=Path(bundle).resolve()
    if root not in bundle.parents:raise ValueError('inference bundle must be inside the authorized workspace')
    files=[]
    for name in ('bundle.json','identity.json','memory.safetensors'):
        p=bundle/name
        if p.is_symlink() or not p.is_file():raise ValueError('bundle must contain independently owned regular files')
        files.append({'path':str(p),'sha256':digest(p)})
    config=json.loads((bundle/'bundle.json').read_text())
    if config.get('schema')!='hamlet.inference-bundle.v1':raise ValueError('unsupported trained bundle')
    check_files(config['base_inventory'])
    # Imports/weight loading in runtime additionally verify parent/config/weight identity.
    return {'method':'hamlet-trained','bundle':str(bundle),'sha256':identity(files),'files':files}


class TrainedHAMLETRuntime:
    def __init__(self,model,bundle,output_path):
        self.model=model;root=Path(bundle)
        self.config=json.loads((root/'bundle.json').read_text())
        if self.config.get('schema')!='hamlet.inference-bundle.v1':raise ValueError('wrong bundle schema')
        check_files(self.config['base_inventory'])
        self.modules,doc=load_modules(root,expected_base=self.config['base_inventory']['sha256'],
                expected_protocol=identity(self.config['protocol']))
        if doc['checkpoint_sha256']!=self.config['checkpoint_sha256']:raise ValueError('bundle/checkpoint mismatch')
        self.use_router=self.config['use_router']
        if doc['stage'] not in ('reader','router') or (self.use_router and doc['stage']!='router'):raise ValueError('untrained deployment component')
        llm=model.get_llm();first_parameter=next(llm.parameters());self.device=first_parameter.device
        # The moment cache was generated with the frozen base decoder's dtype.
        # A deployment dtype change alters all moment vectors even if model
        # weights and RGB inputs are identical.  Refuse such a silent drift.
        require_clean_encoding_dtype(self.config['protocol'].get('clean_encoding_dtype'),
                                     first_parameter.dtype)
        h=getattr(llm.config,'hidden_size',None)
        if h!=self.modules.config.hidden_size:raise ValueError('base model hidden dimension mismatch')
        self.modules.to(self.device).eval().requires_grad_(False)
        self.state=RecentState()
        self.path=Path(output_path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.log=self.path.open('x',encoding='utf8')

    def _record(self,row):self.log.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n');self.log.flush()

    @torch.inference_mode()
    def generate(self,*,episode,call_id,frame,input_ids,images,**kwargs):
        if len(input_ids)!=1:raise ValueError('one-episode runtime is required by the original evaluator')
        if images is not None and len(images)!=8:raise ValueError('eight-frame protocol changed')
        original_kwargs=dict(kwargs)
        mask=kwargs.pop('attention_mask',None)
        if images is not None:
            _,_,mask,_,prompt,_=self.model.prepare_inputs_labels_for_multimodal(input_ids,None,mask,None,None,images)
        else:prompt=self.model.get_input_embeddings()(input_ids)
        if prompt is None:raise ValueError('no multimodal prompt embeddings')
        if mask is None:mask=torch.ones(prompt.shape[:2],dtype=torch.bool,device=prompt.device)
        current=self.modules.moment(self.model.get_llm(),prompt,mask)
        past,valid,ages,actions=self.state.before(episode,int(call_id),current[0])
        memory,read,selection=self.modules.read(current,past,valid,ages,actions,use_router=self.use_router)
        alpha=float(self.modules.reader.injection.alpha)
        changed=bool(read.gt(0).any()) and alpha!=0
        if changed:
            adapted=self.modules.reader.inject(prompt,mask,memory)
            if self.config['mode_lock']:
                mode=self.model._base_reason_act_token_ids(prompt,mask)
                processors=LogitsProcessorList(list(kwargs.pop('logits_processor',[]) or []))
                processors.append(_ForceFirstGeneratedToken(mode));kwargs['logits_processor']=processors
            result=self.model.get_llm().generate(inputs_embeds=adapted,attention_mask=mask,**kwargs)
        else:
            # Exact original generate interface; no appended moments, no extra forced mode.
            result=self.model.generate(input_ids,images=images,**original_kwargs)
        self.state.commit(int(call_id),current[0])
        self._record({'event':'read','episode':str(episode),'call_id':int(call_id),'frame':int(frame),
                      'past_mask':valid[0].tolist(),'read_probability':float(read[0]),'alpha':alpha,
                      'injected':changed,'router_used':bool(selection.use_memory[0]) if selection else None,
                      'checkpoint_sha256':self.config['checkpoint_sha256']})
        return result

    def action_decision(self,action_id,call_id):
        # This callback precedes env.step: it is NOT an executed-action observation.
        self._record({'event':'proposed_action','action':int(action_id),'call_id':int(call_id)})
    def record_executed_action(self,action_id):
        self.state.executed(int(action_id));self._record({'event':'executed_action','action':int(action_id)})
    def end_episode(self,episode):
        self._record({'event':'episode_end','episode':str(episode)});self.state.reset(None)
    def close(self):
        if not self.log.closed:self.log.close()
