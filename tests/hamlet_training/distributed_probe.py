"""CPU-only two-process integration probe using explicitly synthetic fixtures.

Run with torch.distributed.run; not a training-data producer or GPU acceptance.
"""
import argparse
import json
from pathlib import Path
import torch
from torch.utils.data import Dataset
from transformers import GPT2Config,GPT2LMHeadModel
from awarevln_memory.training.models import ShortMemoryConfig,MemoryModules,StageModel
from awarevln_memory.training.engine import train_stage
from awarevln_memory.training.checkpoints import read_identity


class ProbeData(Dataset):
    def __init__(self):
        rng=torch.Generator().manual_seed(12)
        self.items=[];self.rows=[]
        for i in range(8):
            self.items.append(dict(prompt=torch.randn(5,16,generator=rng),
                current_moment=torch.randn(4,16,generator=rng),past_moments=torch.randn(3,4,16,generator=rng),
                past_valid=torch.tensor([True,True,True]),ages=torch.tensor([3,2,1,0]),
                actions=torch.tensor([1,2,1,4]),target_ids=torch.tensor([1,2,3]),
                kind=torch.tensor(0),preserve=torch.tensor(False)))
            self.rows.append({'dataset':'r2r' if i%2 else 'rxr','family':str(i)})
    def __len__(self):return len(self.items)
    def __getitem__(self,i):return self.items[i]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    torch.set_num_threads(1);torch.manual_seed(42)
    llm=GPT2LMHeadModel(GPT2Config(vocab_size=24,n_embd=16,n_layer=1,n_head=2,n_positions=32,
                                  resid_pdrop=0,embd_pdrop=0,attn_pdrop=0))
    modules=MemoryModules(ShortMemoryConfig(hidden_size=16,memory_size=8,heads=2,layers=1,projection_size=8))
    model=StageModel(llm,modules,'reader',memory_dropout=.1)
    result=train_stage(model,ProbeData(),ProbeData(),args.output,
        {'base_identity':'synthetic-ddp-base','protocol_identity':'synthetic-ddp','data_identity':'test-only'},
        parent_sha='synthetic-moment',epochs=2,step_cap=4,micro_batch=1,accumulation=2,
        lr=.001,gate_lr=.001,eval_steps=2,patience=10,cpu=True,diagnostic=True)
    assert result['step']==4
    root=Path(args.output);checkpoint=root/'checkpoint-4';read_identity(checkpoint)
    assert (checkpoint/'rng-rank-0.json').is_file() and (checkpoint/'rng-rank-1.json').is_file()
    if torch.distributed.get_rank()==0:
        print(json.dumps({'status':'PASSED','world_size':2,'device':'CPU','optimizer_steps':4,
                           'scope':'synthetic integration only, NOT A6000/8B/navigation validation'}))
    torch.distributed.barrier();torch.distributed.destroy_process_group()


if __name__=='__main__':main()
