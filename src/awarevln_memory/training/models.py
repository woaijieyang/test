"""Trainable short-memory path, opt-in and separate from historical checkpoints.

Reuses PyTorch's TransformerEncoder, the project's exact prompt injection and
CBEM scorer. It never changes the pretrained decoder or action vocabulary.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
import torch
from torch import nn
from torch.nn import functional as F
from awarevln_memory.config import MemoryAdapterConfig
from awarevln_memory.memory.adapter import GatedPromptInjection
from awarevln_memory.cbem.config import CBEMConfig
from awarevln_memory.cbem.router import CBEMRouter
from .masks import block_causal_mask


@dataclass(frozen=True)
class ShortMemoryConfig:
    hidden_size: int
    memory_size: int = 768
    moments: int = 4
    slots: int = 4
    layers: int = 2
    heads: int = 12
    projection_size: int = 256
    max_age: int = 256
    dropout: float = 0.0
    schema: str = 'hamlet.short-memory.v1'

    def __post_init__(self):
        if self.schema != 'hamlet.short-memory.v1':raise ValueError('unsupported short memory schema')
        for key in ('hidden_size','memory_size','moments','slots','layers','heads','projection_size','max_age'):
            if getattr(self,key)<1:raise ValueError(f'positive {key} required')
        if self.slots!=4 or self.moments!=4:raise ValueError('first release requires past3+current and 4 moments')
        if self.memory_size%self.heads:raise ValueError('memory dimension must divide heads')
        if not 0<=self.dropout<1:raise ValueError('invalid dropout')

    def to_dict(self):return asdict(self)


def decoder_of(llm):
    decoder=getattr(llm,'model',None)
    if decoder is None:decoder=getattr(llm,'transformer',None)
    if decoder is None:raise TypeError('expected Llama-style .model or GPT2-style .transformer decoder')
    return decoder


def compact_prompts(embeddings, mask):
    if embeddings.ndim!=3 or tuple(mask.shape)!=tuple(embeddings.shape[:2]):
        raise ValueError('prompt shape/mask mismatch')
    values=[x[m.bool()] for x,m in zip(embeddings,mask)]
    if any(len(x)==0 for x in values):raise ValueError('empty prompt')
    if any(not torch.isfinite(x).all() for x in values):raise ValueError('nonfinite prompt')
    return values


def pad_embeddings(values):
    maxlen=max(len(x) for x in values)
    out=torch.stack([F.pad(x,(0,0,0,maxlen-len(x))) for x in values])
    mask=torch.arange(maxlen,device=out.device)[None,:]<torch.tensor([len(x) for x in values],device=out.device)[:,None]
    return out,mask


class MomentEncoder(nn.Module):
    def __init__(self,config):
        super().__init__();self.config=config
        self.tokens=nn.Parameter(torch.randn(config.moments,config.hidden_size)*.02)
        self.projection=nn.Sequential(nn.LayerNorm(config.moments*config.hidden_size),
                                      nn.Linear(config.moments*config.hidden_size,config.projection_size))

    def forward(self,llm,prompt_embeds,prompt_mask):
        # No target input exists in this interface.
        prompts=[p.to(dtype=next(llm.parameters()).dtype) for p in compact_prompts(prompt_embeds,prompt_mask)]
        values=[torch.cat([p,self.tokens.to(dtype=p.dtype)],0) for p in prompts]
        embeddings,mask=pad_embeddings(values)
        max_positions=getattr(llm.config,'max_position_embeddings',getattr(llm.config,'n_positions',None))
        if max_positions and embeddings.shape[1]>max_positions:raise ValueError('moment append exceeds context; no silent truncation')
        positions=(mask.long().cumsum(-1)-1).clamp_min(0)
        output=decoder_of(llm)(inputs_embeds=embeddings,attention_mask=mask,
                              position_ids=positions,use_cache=False,return_dict=True)
        hidden=output.last_hidden_state
        return torch.stack([hidden[b,len(p):len(p)+self.config.moments]
                            for b,p in enumerate(prompts)]).float()

    def contrast(self,moments):
        return F.normalize(self.projection(moments.float().flatten(1)),dim=-1)


class TemporalReader(nn.Module):
    def __init__(self,config):
        super().__init__();self.config=config
        self.down=nn.Linear(config.hidden_size,config.memory_size,bias=False)
        self.slot=nn.Parameter(torch.randn(config.moments,config.memory_size)*.02)
        self.age=nn.Embedding(config.max_age+1,config.memory_size)
        self.action=nn.Embedding(6,config.memory_size)
        layer=nn.TransformerEncoderLayer(config.memory_size,config.heads,config.memory_size*4,
                    dropout=config.dropout,batch_first=True,norm_first=True,activation='gelu')
        self.temporal=nn.TransformerEncoder(layer,config.layers,enable_nested_tensor=False)
        self.norm=nn.LayerNorm(config.memory_size)
        self.gate=nn.Sequential(nn.Linear(config.memory_size*2,config.memory_size),nn.GELU(),nn.Linear(config.memory_size,1))
        self.injection=GatedPromptInjection(MemoryAdapterConfig(
            llm_hidden_size=config.hidden_size,memory_hidden_size=config.memory_size,
            memory_heads=config.heads,memory_layers=config.layers,moment_tokens=config.moments,
            output_memory_tokens=config.moments,alpha_init=0.0))

    def router_features(self,moments):
        # Pool ONLY routing keys, never the temporal reader's four slots.
        return self.down(moments.float()).mean(-2)

    def forward(self,moments,valid,ages,actions):
        c=self.config
        if tuple(moments.shape[1:])!=(c.slots,c.moments,c.hidden_size):raise ValueError('memory shape mismatch')
        if valid.shape!=moments.shape[:2] or not valid[:,-1].all():raise ValueError('current slot must be valid')
        if ages.shape!=valid.shape or actions.shape!=valid.shape:raise ValueError('metadata shape mismatch')
        if (ages[valid]<0).any() or (actions[valid]<0).any() or (actions[valid]>=6).any():raise ValueError('invalid age/action')
        if not ages[:,-1].eq(0).all():raise ValueError('current age must be zero')
        if not torch.isfinite(moments[valid]).all():raise ValueError('nonfinite valid moments')
        clean=torch.where(valid[:,:,None,None],moments,torch.zeros_like(moments))
        x=self.down(clean.float())+self.slot[None,None]+self.age(ages.clamp(0,c.max_age))[:,:,None]+self.action(actions.clamp(0,5))[:,:,None]
        outputs=[]
        # Remove invalid padded slots before attention: no all-masked query rows/NaNs.
        for b in range(len(x)):
            seq=x[b,valid[b]].flatten(0,1)[None]
            slots=int(valid[b].sum())
            enc=self.temporal(seq,mask=block_causal_mask(slots,c.moments,x.device))
            outputs.append(self.norm(enc[0,-c.moments:]))
        current=self.down(clean[:,-1].float()).mean(1)
        output=torch.stack(outputs)
        probability=torch.sigmoid(self.gate(torch.cat([current,output.mean(1)],-1))).squeeze(-1)
        probability=probability*valid[:,:-1].any(-1)
        return output*probability[:,None,None],probability

    def inject(self,prompt,mask,memory):
        return self.injection(prompt,memory,mask)


class MemoryModules(nn.Module):
    def __init__(self,config):
        super().__init__();self.config=config
        self.moment=MomentEncoder(config);self.reader=TemporalReader(config)
        self.router=CBEMRouter(CBEMConfig(adapter_hidden_size=config.memory_size,
                         rank=min(128,config.memory_size),prefilter_top_k=3,selected_top_k=3,
                         archive_capacity=3,max_age=config.max_age,none_logit_init=0.0))

    def set_stage(self,stage):
        if stage not in ('tcl','reader','router'):raise ValueError('unknown training stage')
        self.requires_grad_(False)
        active={'tcl':self.moment,'reader':self.reader,'router':self.router}[stage]
        active.requires_grad_(True)
        return [name for name,p in self.named_parameters() if p.requires_grad]

    def read(self,current,past,valid,ages,actions,use_router=False):
        if past.shape[1]!=self.config.slots-1:raise ValueError('exactly three past slots required')
        if valid.shape!=past.shape[:2]:raise ValueError('past mask mismatch')
        selection=None
        if use_router:
            selection=self.router(current_query=self.reader.down(current.float()),
                     memory_items=self.reader.router_features(past),memory_mask=valid,
                     memory_types=torch.zeros_like(valid,dtype=torch.long),memory_ages=ages[:,:-1])
            selected=torch.zeros_like(valid)
            # Keep chronological positions; scorer top-k order is NOT temporal order.
            for b in range(len(valid)):
                selected[b,selection.selected_indices[b,selection.selected_mask[b]]]=True
            valid=valid&selected
        moments=torch.cat([past,current[:,None]],dim=1)
        mask=torch.cat([valid,torch.ones(len(valid),1,device=valid.device,dtype=torch.bool)],1)
        memory,probability=self.reader(moments,mask,ages,actions)
        return memory,probability,selection


def token_loss_per_example(logits,labels):
    shifted=labels[:,1:]
    mask=shifted.ne(-100)
    if not mask.any(-1).all():raise ValueError('each SFT example requires supervised tokens')
    loss=F.cross_entropy(logits[:,:-1].float().transpose(1,2),shifted,reduction='none',ignore_index=-100)
    return (loss*mask).sum(-1)/mask.sum(-1)


def teacher_forced(llm,prompt,prompt_mask,target_ids,target_mask):
    prompts=[p.to(dtype=next(llm.parameters()).dtype) for p in compact_prompts(prompt,prompt_mask)]
    targets=[ids[m.bool()] for ids,m in zip(target_ids,target_mask)]
    if any(len(t)==0 for t in targets):raise ValueError('empty target')
    values=[torch.cat([p,llm.get_input_embeddings()(t).to(p.dtype)],0) for p,t in zip(prompts,targets)]
    embeddings,mask=pad_embeddings(values)
    labels=torch.full(mask.shape,-100,dtype=torch.long,device=mask.device)
    for b,(p,t) in enumerate(zip(prompts,targets)):labels[b,len(p):len(p)+len(t)]=t
    maximum=getattr(llm.config,'max_position_embeddings',getattr(llm.config,'n_positions',None))
    if maximum and embeddings.shape[1]>maximum:raise ValueError('SFT exceeds context; refuse truncation')
    result=llm(inputs_embeds=embeddings,attention_mask=mask,
               position_ids=(mask.long().cumsum(-1)-1).clamp_min(0),use_cache=False,return_dict=True)
    return result.logits,labels


class StageModel(nn.Module):
    """Accelerate-compatible stage model; checkpoints store only `modules_`."""
    def __init__(self,llm,modules_,stage,temperature=.07,reason_weight=.3,
                 preservation_weight=.1,memory_dropout=.1):
        super().__init__();self.llm=llm;self.modules_=modules_;self.stage=stage
        if not 0<=memory_dropout<1 or temperature<=0:raise ValueError('invalid training coefficients')
        if llm is not None:llm.requires_grad_(False);llm.eval()
        self.modules_.set_stage(stage)
        self.temperature=temperature;self.reason_weight=reason_weight
        self.preservation_weight=preservation_weight;self.memory_dropout=memory_dropout

    def train(self,mode=True):
        super().train(mode)
        if self.llm is not None:
            # HF decoder checkpointing is guarded by self.training. Simply forcing
            # llm.eval() silently disables it and can cause an 8B activation OOM.
            checkpointing=bool(getattr(self.llm,'is_gradient_checkpointing',False))
            self.llm.train(mode and checkpointing)
            for layer in self.llm.modules():
                if isinstance(layer,nn.Dropout):layer.eval()
                if mode and checkpointing and float(getattr(layer,'attention_dropout',0.0))!=0:
                    raise ValueError('functional attention dropout must be zero for frozen deterministic checkpointing')
        if self.stage!='tcl':self.modules_.moment.eval()
        if self.stage!='reader':self.modules_.reader.eval()
        return self

    def forward(self,**batch):
        if self.stage=='tcl':return self._tcl(batch)
        if self.stage=='reader':return self._reader(batch)
        return self._router(batch)

    def _tcl(self,b):
        vectors=[];anchor_raw=None
        for key in ('anchor','positive','negative'):
            raw=self.modules_.moment(self.llm,b[key],b[key+'_mask'])
            vectors.append(self.modules_.moment.contrast(raw))
            if key=='anchor':anchor_raw=raw.mean(1).detach()
        a,p,n=vectors
        logits=torch.stack([(a*p).sum(-1),(a*n).sum(-1)],-1)/self.temperature
        loss=F.cross_entropy(logits,torch.zeros(len(a),dtype=torch.long,device=a.device))
        return {'loss':loss,'logits':logits,'raw_moment_summary':anchor_raw}

    def _reader(self,b):
        # Frozen moment checkpoint is bound to cache by the Dataset contract.
        valid=b['past_valid'].clone()
        if self.training and self.memory_dropout:
            valid &= (torch.rand(len(valid),1,device=valid.device)>=self.memory_dropout)
        memory,read,_=self.modules_.read(b['current_moment'],b['past_moments'],valid,b['ages'],b['actions'])
        adapted=self.modules_.reader.inject(b['prompt'],b['prompt_mask'],memory)
        logits,labels=teacher_forced(self.llm,adapted,b['prompt_mask'],b['target_ids'],b['target_mask'])
        per=token_loss_per_example(logits,labels)
        weights=torch.where(b['kind'].eq(1),self.reason_weight,1.0)
        loss=(per*weights).mean()
        preserve=b.get('preserve',torch.zeros_like(weights,dtype=torch.bool))
        if preserve.any() and self.preservation_weight:
            with torch.no_grad():
                teacher,_=teacher_forced(self.llm,b['prompt'],b['prompt_mask'],b['target_ids'],b['target_mask'])
            # Select supervised predictions BEFORE float32 softmax: bounded overhead.
            mask=labels[:,1:].ne(-100)&preserve[:,None]
            student_log=F.log_softmax(logits[:,:-1][mask].float(),-1)
            teacher_log=F.log_softmax(teacher[:,:-1][mask].float(),-1)
            kl=F.kl_div(student_log,teacher_log,log_target=True,reduction='batchmean')
            loss=loss+self.preservation_weight*kl
        return {'loss':loss,'logits':torch.stack([per.detach(),read.detach()],-1)}

    def _router(self,b):
        out=self.modules_.router(b['query'],b['items'],b['valid'],b['types'],b['ages'])
        labels=torch.gather(b['utility_sign'],1,out.coarse_indices)
        if not ((labels == -1) | (labels == 0) | (labels == 1)).all():
            raise ValueError('invalid candidate utility labels')
        measured=torch.gather(b.get('candidate_measured',b['utility_sign'].ne(0)),1,out.coarse_indices)
        usable=out.candidate_mask & measured.bool()
        margins=out.candidate_logits-out.none_logit[:,None]
        terms=[]
        if usable.any():
            targets=(labels[usable].float()+1)/2
            weights=torch.where(labels[usable].eq(0),.1,1.0)
            terms.append((F.binary_cross_entropy_with_logits(margins[usable],targets,reduction='none')*weights).mean())
        # ON/OFF labels supervise the set decision, not every item in that set.
        set_sign=b['set_sign'];set_valid=b['set_valid'].bool()
        set_valid &= out.candidate_mask.any(-1)
        if set_valid.any():
            best=out.candidate_logits.max(-1).values-out.none_logit
            targets=(set_sign[set_valid].float()+1)/2
            weights=torch.where(set_sign[set_valid].eq(0),.1,1.0)
            terms.append((F.binary_cross_entropy_with_logits(best[set_valid],targets,reduction='none')*weights).mean())
        if not terms:raise ValueError('router batch contains only unverified evidence')
        loss=torch.stack(terms).mean()
        # Report the EXACT runtime max-vs-NONE rule, not probability mass > .5.
        pred=out.use_memory.float()
        return {'loss':loss,'logits':torch.stack([pred,1-pred],-1)}
