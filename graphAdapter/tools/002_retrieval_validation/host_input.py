from pathlib import Path
from types import SimpleNamespace
import ast,copy,json,time
import numpy as np
import torch
from PIL import Image
from transformers import AutoTokenizer,SiglipImageProcessor
from graphAdapter.map_memory.storage.store import load_episode
from graphAdapter.map_memory.retrieval.contracts import Selection
from graphAdapter.map_memory.retrieval.host_input_compiler import materialize_history,compile_question
from graphAdapter.map_memory.retrieval.input_audit import observe_process_images,audit_final_inputs
from llava.conversation import conv_templates
from llava.mm_utils import process_images,tokenizer_image_token
from llava.constants import IMAGE_TOKEN_INDEX
ROOT=Path('/data/zy/vln/case2');OUT=ROOT/'outputs/graph_memory/graph002-work-20261113'
torch.set_num_threads(4)
source=ROOT/'src/vlnce_baselines/awarevln_trainer.py';tree=ast.parse(source.read_text())
sampler_node=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='sample_and_pad_images')
namespace={'copy':copy,'np':np,'Image':Image}
exec(compile(ast.Module(body=[sampler_node],type_ignores=[]),str(source),'exec'),namespace)
checkpoint=json.loads((ROOT/'models/awarevln/config.json').read_text())
config=SimpleNamespace(**checkpoint)
processor=SiglipImageProcessor.from_pretrained(ROOT/'models/awarevln/vision_tower',local_files_only=True)
tokenizer=AutoTokenizer.from_pretrained(ROOT/'models/awarevln/llm',local_files_only=True)
root=ROOT/'outputs/graph_memory/graph001-organized-20261113/validation/cold-readback/map'
reader=load_episode(root)
try:
    replay=json.loads((OUT/'REAL_RETRIEVAL_OPEN_LOOP.json').read_text())
    by_seq={v['capture_seq']:uid for uid,v in reader._graph['views'].items()}
    refs=tuple(reader.get_retrieval_view(by_seq[seq])for seq in replay['graph_slots'])
    current=refs[-1];rgb=reader.get_view(current.frame_uid)['host_view']
    selection=Selection(refs,(),(),(),None,config.num_video_frames)
    history=materialize_history(selection,reader,rgb,current=current,sampler=namespace['sample_and_pad_images'])
    instruction=replay['instruction'];interleaved_images='<image>\n'*(len(history.images)-1)
    # Evaluate only the actual source f-string assignment of the no-reasoning branch.
    choices=[node.value for node in ast.walk(tree)if isinstance(node,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='question'for t in node.targets)]
    question_node=next(node for node in choices if not any(isinstance(n,ast.Name)and n.id=='reasoning_context'for n in ast.walk(node)))
    original=eval(compile(ast.Expression(question_node),str(source),'eval'),{'instruction':instruction,'interleaved_images':interleaved_images})
    def prompt_of(question):
        conv=conv_templates['llama_3'].copy();conv.append_message(conv.roles[0],question);conv.append_message(conv.roles[1],None)
        return conv.get_prompt()
    # Validate the checked-in projector's shape mapping, without claiming a vision forward.
    projector=ROOT/'src/llava/model/multimodal_projector/base_projector.py'
    cls=next(n for n in ast.parse(projector.read_text()).body if isinstance(n,ast.ClassDef)and n.name=='DownSampleBlock')
    block_namespace={'torch':torch,'nn':torch.nn}
    exec(compile(ast.Module(body=[cls],type_ignores=[]),str(projector),'exec'),block_namespace)
    assert checkpoint['mm_projector_cfg']['mm_projector_type']=='mlp_downsample'
    assert checkpoint['mm_vision_select_feature']=='cls_patch'and checkpoint['s2'] is False
    grid=checkpoint['vision_tower_cfg']['image_size']//checkpoint['vision_tower_cfg']['patch_size']
    per_image=block_namespace['DownSampleBlock']()(torch.zeros(1,grid*grid,4)).shape[1]
    limit=min(checkpoint['llm_cfg']['tokenizer_model_max_length'],checkpoint['llm_cfg']['max_position_embeddings'])
    def fits(question):
        ids=tokenizer_image_token(prompt_of(question),tokenizer,IMAGE_TOKEN_INDEX)
        return len(ids)-config.num_video_frames+config.num_video_frames*per_image+256<=limit
    compiled=compile_question(original,history,token_count=lambda text:len(tokenizer.encode(text,add_special_tokens=False)),context_fits=fits)
    assert compiled.fallback_reason is None
    prompt=prompt_of(compiled.question)
    tensor,receipt=observe_process_images(history,processor,config,process_images=process_images)
    tensor=tensor.to(dtype=torch.float16)
    ids=tokenizer_image_token(prompt,tokenizer,IMAGE_TOKEN_INDEX,return_tensors='pt').unsqueeze(0)
    report=audit_final_inputs(history=history,receipt=receipt,images_tensor=tensor,prompt=prompt,input_ids=ids,
        tokenize_prompt=lambda text:tokenizer_image_token(text,tokenizer,IMAGE_TOKEN_INDEX,return_tensors='pt'),
        original_question=original,image_token_id=IMAGE_TOKEN_INDEX,
        generation_config={'do_sample':False,'temperature':0.,'max_new_tokens':256,'use_cache':True,'pad_token_id':tokenizer.eos_token_id},
        vision_tokens_per_slot=[per_image]*config.num_video_frames,context_limit=limit)
    report.update(scope='Real archived RGB, original sampler/question/process_images, actual checkpoint Siglip processor and tokenizer; CPU material audit only',
        facts_tokens=compiled.added_tokens,vision_budget_source='Actual config plus checked-in DownSampleBlock shape test; full vision/projector runtime NOT_RUN',
        vision_tokens_per_image=per_image,model_weights_loaded=False,model_generate_called=False,navigation_run=False,
        original_instruction_preserved=instruction in prompt)
    (OUT/'REAL_HOST_INPUT_CPU.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items()if k!='slots'},indent=2))
finally:reader.close()
