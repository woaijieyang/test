"""Actual CPU optimizer/checkpoint exercise using the deployed stage models."""
from pathlib import Path
import torch
from torch.utils.data import Dataset
from test_models import tiny,reader_batch
from awarevln_memory.training.models import StageModel
from awarevln_memory.training.engine import train_stage,balanced_schedule
from awarevln_memory.training.checkpoints import load_modules

class TensorRows(Dataset):
    """Synthetic test fixture ONLY; never used by production CLI."""
    def __init__(self):
        b=reader_batch();self.items=[]
        for i in range(2):
            self.items.append({k:v[i] for k,v in b.items() if k not in ('prompt_mask','target_mask')})
        self.rows=[{'dataset':d,'family':str(i)} for i,d in enumerate(('r2r','rxr'))]
    def __len__(self):return len(self.items)
    def __getitem__(self,i):return self.items[i]


def test_real_accelerate_training_and_resume(tmp_path):
    torch.set_num_threads(1)
    llm,m=tiny();model=StageModel(llm,m,'reader',memory_dropout=.1)
    data=TensorRows();contract={'base_identity':'test-base','protocol_identity':'test-protocol','data_identity':'test-data'}
    run=tmp_path/'run'
    result=train_stage(model,data,data,run,contract,parent_sha='test-moment',epochs=4,step_cap=4,
                       micro_batch=1,accumulation=2,lr=.001,gate_lr=.001,eval_steps=2,patience=100,cpu=True,diagnostic=True)
    assert result['step']==4
    final={k:v.clone() for k,v in model.modules_.state_dict().items()}
    assert (run/'checkpoint-2'/'training_state.json').is_file()
    loaded,doc=load_modules(run/'checkpoint-4',stage='reader')
    assert doc['parent_sha256']=='test-moment'
    assert all(torch.equal(final[k],v) for k,v in loaded.state_dict().items())
    # Resume in a new output directory using identical frozen schedule/contract.
    # The API intentionally requires it to exist but does not overwrite checkpoints.
    resumed=tmp_path/'resumed';resumed.mkdir()
    llm2,m2=tiny();model2=StageModel(llm2,m2,'reader',memory_dropout=.1)
    result2=train_stage(model2,data,data,resumed,contract,parent_sha='test-moment',epochs=4,step_cap=4,
                       micro_batch=1,accumulation=2,lr=.001,gate_lr=.001,eval_steps=2,patience=100,cpu=True,
                       diagnostic=True,resume=run/'checkpoint-2')
    assert result2['step']==4
    for k,v in model2.modules_.state_dict().items():
        assert torch.equal(v,final[k]),k


def test_schedule_balances_datasets_not_window_counts():
    rows=[{'dataset':'r2r','family':'r'}]*100+[{'dataset':'rxr','family':'x'}]
    seq=balanced_schedule(rows,20,42)
    assert sum(rows[i]['dataset']=='r2r' for i in seq)==10
    assert seq==balanced_schedule(rows,20,42)
