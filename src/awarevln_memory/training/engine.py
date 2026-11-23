"""Memory-only training on Hugging Face Accelerate (existing project dependency).

Accelerate owns DDP, mixed precision and accumulation; PyTorch owns AdamW and
scheduling. We store only the small memory module, never a duplicate 8B model.
Resume is at optimizer boundaries with a fixed global sample schedule.
"""
from __future__ import annotations
import io
import json
import math
import random
from collections import defaultdict
from pathlib import Path
import numpy as np
import torch
from torch.utils.data import DataLoader,Subset
from .artifacts import identity,digest,write_json,write_bytes,budget,training_path
from .checkpoints import save_modules,read_identity
from .datasets import collate_stage


def balanced_schedule(rows,count,seed):
    if not rows or count<1:raise ValueError('nonempty schedule required')
    groups=defaultdict(lambda:defaultdict(list))
    for i,row in enumerate(rows):groups[row['dataset']][row['family']].append(i)
    rng=random.Random(seed);datasets=sorted(groups);families={};cursors=defaultdict(int)
    for ds in datasets:
        families[ds]=sorted(groups[ds]);rng.shuffle(families[ds])
        for indices in groups[ds].values():rng.shuffle(indices)
    result=[]
    for i in range(count):
        ds=datasets[i%len(datasets)];round_index=i//len(datasets)
        fam=families[ds][round_index%len(families[ds])]
        ids=groups[ds][fam];key=(ds,fam)
        result.append(ids[cursors[key]%len(ids)]);cursors[key]+=1
    return result


def rng_state():
    n=np.random.get_state()
    return {'python':random.getstate(),'numpy':[n[0],n[1].tolist(),n[2],n[3],n[4]],
            'torch':torch.get_rng_state().tolist(),
            'cuda':[t.tolist() for t in torch.cuda.get_rng_state_all()] if torch.cuda.is_available() else []}


def restore_rng(state):
    def tuples(obj):return tuple(tuples(x) for x in obj) if isinstance(obj,list) else obj
    random.setstate(tuples(state['python']))
    n=state['numpy'];np.random.set_state((n[0],np.asarray(n[1],dtype=np.uint32),n[2],n[3],n[4]))
    torch.set_rng_state(torch.tensor(state['torch'],dtype=torch.uint8))
    if state['cuda']:
        if not torch.cuda.is_available():raise ValueError('CUDA checkpoint cannot resume on CPU')
        torch.cuda.set_rng_state_all([torch.tensor(v,dtype=torch.uint8) for v in state['cuda']])


def optimizer_groups(model,lr,gate_lr,weight_decay):
    groups=defaultdict(list);names={}
    for name,p in model.modules_.named_parameters():
        if not p.requires_grad:continue
        rate=gate_lr if ('.gate.' in name or name.endswith('.alpha')) else lr
        decay=0.0 if p.ndim<2 or name.endswith('.tokens') or '.norm.' in name else weight_decay
        key=(rate,decay);groups[key].append(p);names[name]={'lr':rate,'weight_decay':decay,'numel':p.numel()}
    if not groups:raise ValueError('no trainable memory parameters')
    if model.llm is not None and any(p.requires_grad for p in model.llm.parameters()):raise ValueError('backbone unexpectedly unfrozen')
    return [dict(params=params,lr=k[0],weight_decay=k[1]) for k,params in groups.items()],names


def evaluate(model,dataset,device,batch_size=1):
    from accelerate.utils import send_to_device
    old=model.training;model.eval();losses=[];detail=defaultdict(list);raw_moments=[]
    # An explicit generator avoids consuming training's dropout RNG at iterator creation.
    loader=DataLoader(dataset,batch_size=batch_size,collate_fn=collate_stage,
                      generator=torch.Generator().manual_seed(0))
    with torch.no_grad():
        for batch in loader:
            batch=send_to_device(batch,device);out=model(**batch)
            n=len(next(iter(batch.values())))
            losses.extend([float(out['loss'])]*n)
            if model.stage=='tcl':
                detail['contrastive_margin'].extend((out['logits'][:,0]-out['logits'][:,1]).cpu().tolist())
                detail['positive_rank_accuracy'].extend((out['logits'][:,0]>out['logits'][:,1]).float().cpu().tolist())
                raw_moments.append(out['raw_moment_summary'].cpu())
            elif model.stage=='reader':
                for i,kind in enumerate(batch['kind']):detail['reason_loss' if int(kind) else 'act_loss'].append(float(out['logits'][i,0]))
                detail['read_probability'].extend(out['logits'][:,1].cpu().tolist())
            elif model.stage=='router':
                prediction=out['logits'][:,0]>out['logits'][:,1]
                for sign,pred,valid in zip(batch['set_sign'],prediction,batch['set_valid']):
                    if bool(valid):detail[{1:'helpful_use',-1:'harmful_use',0:'neutral_use'}[int(sign)]].append(float(pred))
    if raw_moments:
        all_moments=torch.cat(raw_moments,0)
        detail['raw_moment_between_example_variance']=[float(all_moments.var(0,unbiased=False).mean())]
    model.train(old)
    if not losses or not all(math.isfinite(x) for x in losses):raise ValueError('invalid development loss')
    return {'loss':sum(losses)/len(losses),'n':len(losses),
            'diagnostics':{k:{'mean':sum(v)/len(v),'n':len(v)} for k,v in detail.items() if v}}


def train_stage(model,train_dataset,dev_dataset,output,contract,*,parent_sha=None,
                epochs=4,step_cap=5000,micro_batch=1,accumulation=8,lr=5e-5,
                gate_lr=2e-5,weight_decay=.01,warmup_ratio=.03,eval_steps=100,
                seed=42,mixed_precision='no',resume=None,patience=2,cpu=False,
                diagnostic=False):
    from accelerate import Accelerator
    from accelerate.utils import set_seed,DistributedDataParallelKwargs
    from safetensors.torch import load_file
    if micro_batch<1 or accumulation<1 or eval_steps<1:raise ValueError('positive batch/interval required')
    if mixed_precision not in ('no','bf16'):
        raise ValueError('this checkpoint contract supports no/bf16 training, not unsaved FP16 GradScaler state')
    if not 0<=warmup_ratio<1 or lr<=0 or gate_lr<=0:raise ValueError('invalid optimizer configuration')
    accelerator=Accelerator(cpu=cpu,mixed_precision=mixed_precision,
            gradient_accumulation_steps=accumulation,
            kwargs_handlers=[DistributedDataParallelKwargs(find_unused_parameters=True)])
    root=training_path(output)
    if not resume and accelerator.is_main_process:root.mkdir(parents=True,exist_ok=False)
    accelerator.wait_for_everyone()
    set_seed(seed,device_specific=True)
    b=budget(len(train_dataset),epochs,micro_batch,accelerator.num_processes,accumulation,step_cap)
    schedule=balanced_schedule(train_dataset.rows,b['max_steps']*b['effective_batch'],seed)
    configuration=dict(stage=model.stage,budget=b,micro_batch=micro_batch,accumulation=accumulation,
                       lr=lr,gate_lr=gate_lr,weight_decay=weight_decay,warmup_ratio=warmup_ratio,
                       eval_steps=eval_steps,seed=seed,mixed_precision=mixed_precision,patience=patience,
                       diagnostic=diagnostic,schedule_sha256=identity(schedule),world_size=accelerator.num_processes)
    run_contract=dict(contract,training_identity=identity(configuration))
    groups,names=optimizer_groups(model,lr,gate_lr,weight_decay)
    optimizer=torch.optim.AdamW(groups,betas=(.9,.999),eps=1e-8)
    warmup=max(1,round(b['max_steps']*warmup_ratio)) if warmup_ratio else 0
    def schedule_factor(step):
        if warmup and step<warmup:return step/max(1,warmup)
        progress=(step-warmup)/max(1,b['max_steps']-warmup)
        return .5*(1+math.cos(math.pi*min(1,max(0,progress))))
    scheduler=torch.optim.lr_scheduler.LambdaLR(optimizer,schedule_factor)
    start=0;best=float('inf');bad=0;history=[];rng=None
    if resume:
        res=training_path(resume);meta=read_identity(res)
        state=json.loads((res/'training_state.json').read_text())
        if meta['contract']!=run_contract or state['configuration']!=configuration or meta['parent_sha256']!=parent_sha:
            raise ValueError('resume configuration/data/parent drift')
        for record in state['files']:
            if digest(res/record['name'])!=record['sha256']:raise ValueError('resume artifact changed')
        model.modules_.load_state_dict(load_file(str(res/'memory.safetensors')),strict=True)
        optimizer.load_state_dict(torch.load(res/'optimizer.pt',map_location='cpu',weights_only=True))
        scheduler.load_state_dict(json.loads((res/'scheduler.json').read_text()))
        start=state['step'];best=state['best'];bad=state['bad'];history=state['history']
        rng=json.loads((res/f'rng-rank-{accelerator.process_index}.json').read_text())
        if start>=b['max_steps']:raise ValueError('checkpoint already reached budget')
        if not root.is_dir():raise ValueError('resume output directory missing')
    elif accelerator.is_main_process:
        write_json(root/'run_contract.json',{'contract':run_contract,'configuration':configuration,'trainable':names})
    subset=Subset(train_dataset,schedule[start*b['effective_batch']:])
    loader=DataLoader(subset,batch_size=micro_batch,shuffle=False,collate_fn=collate_stage,
                      generator=torch.Generator().manual_seed(seed),num_workers=0,drop_last=False)
    model,optimizer,loader=accelerator.prepare(model,optimizer,loader)
    # Scheduler remains unwrapped: exactly one scheduler step per optimizer step.
    if rng is not None:restore_rng(rng)
    optimizer.zero_grad(set_to_none=True);model.train();step=start
    recent=[];last_gradients={};saved=[]
    for batch in loader:
        with accelerator.accumulate(model):
            out=model(**batch);loss=out['loss']
            if not torch.isfinite(loss):raise FloatingPointError('nonfinite loss; retain failing run')
            accelerator.backward(loss)
            if accelerator.sync_gradients:
                unwrapped=accelerator.unwrap_model(model)
                last_gradients={n:float(p.grad.detach().float().norm()) for n,p in unwrapped.modules_.named_parameters() if p.grad is not None}
                if not all(math.isfinite(v) for v in last_gradients.values()):raise FloatingPointError('nonfinite memory gradient')
                accelerator.clip_grad_norm_(model.parameters(),1.0)
            optimizer.step()
            if accelerator.sync_gradients:scheduler.step()
            optimizer.zero_grad(set_to_none=True)
        recent.append(float(loss.detach()))
        if not accelerator.sync_gradients:continue
        step+=1
        if step%eval_steps and step!=b['max_steps']:continue
        accelerator.wait_for_everyone()
        unwrapped=accelerator.unwrap_model(model)
        metrics=evaluate(unwrapped,dev_dataset,accelerator.device,micro_batch)
        # Every rank evaluates the same dev sequentially (no duplicate aggregation).
        row={'step':step,'train_loss_local':sum(recent)/len(recent),'dev':metrics,'gradient_norms':last_gradients}
        recent=[];history.append(row)
        if metrics['loss']<best*(1-1e-4):best=metrics['loss'];bad=0
        else:bad+=1
        target=root/f'checkpoint-{step}'
        if accelerator.is_main_process:
            save_modules(target,unwrapped.modules_,stage=unwrapped.stage,contract=run_contract,parent_sha=parent_sha,step=step)
            buffer=io.BytesIO();torch.save(optimizer.state_dict(),buffer);write_bytes(target/'optimizer.pt',buffer.getvalue())
            write_json(target/'scheduler.json',scheduler.state_dict())
        accelerator.wait_for_everyone()
        write_json(target/f'rng-rank-{accelerator.process_index}.json',rng_state())
        accelerator.wait_for_everyone()
        if accelerator.is_main_process:
            files=[target/'optimizer.pt',target/'scheduler.json']+list(target.glob('rng-rank-*.json'))
            write_json(target/'training_state.json',{'step':step,'best':best,'bad':bad,'history':history,
                'configuration':configuration,'files':[{'name':p.name,'sha256':digest(p)} for p in files]})
        saved.append(str(target))
        accelerator.wait_for_everyone()
        if bad>=patience:break
    if accelerator.is_main_process:
        report={'status':'OPTIMIZATION_FINISHED_PENDING_ACCEPTANCE','diagnostic':diagnostic,
                'stage':accelerator.unwrap_model(model).stage,'steps':step,'saved':saved,
                'budget':b,'history':history,'navigation_validated':False}
        # Unique report by last step; failed runs keep their evidence.
        write_json(root/f'report-step-{step}.json',report)
    accelerator.wait_for_everyone()
    return {'step':step,'saved':saved,'history':history,'budget':b}
