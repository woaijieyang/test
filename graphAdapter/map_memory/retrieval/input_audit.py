"""Verify visual material, token alignment and grouped projector consumption."""
from dataclasses import dataclass,asdict
import hashlib
from .host_input_compiler import pixel_hash
from ..storage.archive import IntegrityError,canonical
from contextlib import contextmanager
from ..storage.archive import IntegrityError


@dataclass(frozen=True)
class ProcessingReceipt:
    snapshot_id: str
    source_pixel_hashes: tuple
    processor_input_pixel_hashes: tuple
    slot_tensors: tuple


class _ObservedProcessor:
    def __init__(self,processor):self.original=processor;self.inputs=[];self.outputs=[]
    def __getattr__(self,name):return getattr(self.original,name)
    def preprocess(self,image,*args,**kwargs):
        value=self.original.preprocess(image,*args,**kwargs)
        self.inputs.append(pixel_hash(image))
        self.outputs.append(value['pixel_values'][0])
        return value


def observe_process_images(history,processor,config,*,process_images):
    expected=tuple(slot.host_pixel_hash for slot in history.slots)
    if tuple(pixel_hash(image)for image in history.images)!=expected:
        raise IntegrityError('Materialized host pixels changed before preprocessing')
    proxy=_ObservedProcessor(processor)
    try:output=process_images(list(history.images),proxy,config)
    finally:
        # The native helper normally installs this exact original processor.
        config.image_processor=processor
    if len(proxy.outputs)!=len(history.slots):
        raise IntegrityError('Native processor call count does not map one-to-one to input slots')
    receipt=ProcessingReceipt(history.snapshot_id,expected,tuple(proxy.inputs),tuple(proxy.outputs))
    return output,receipt


def _blocks(tensor,expected_counts):
    import torch
    n=len(expected_counts)
    if isinstance(tensor,(tuple,list)):
        if len(tensor)!=n:raise IntegrityError('Processor tensor list lacks slot mapping')
        blocks=[t.unsqueeze(0)if t.ndim==3 else t for t in tensor]
    elif isinstance(tensor,torch.Tensor)and tensor.ndim==5:
        if tensor.shape[0]!=n:raise IntegrityError('Nested processor tensor lacks logical slots')
        blocks=list(tensor.unbind(0))
    elif isinstance(tensor,torch.Tensor)and tensor.ndim==4:
        if tensor.shape[0]!=sum(expected_counts):raise IntegrityError('Flattened processor crop count mismatch')
        blocks=list(tensor.split(expected_counts,dim=0))
    else:raise IntegrityError('Unsupported native processor tensor layout')
    if any(t.ndim!=4 or t.shape[0]!=count for t,count in zip(blocks,expected_counts)):
        raise IntegrityError('Per-slot crop count differs from processor receipt')
    return blocks


def tensor_hash(tensor):
    import torch
    value=tensor.detach().contiguous().cpu()
    return hashlib.sha256(canonical(dict(shape=list(value.shape),dtype=str(value.dtype)))+
                          value.view(torch.uint8).numpy().tobytes()).hexdigest()


def verified_prompt_tokens(prompt,input_ids,tokenize_prompt,image_token_id,count):
    import torch
    if not isinstance(input_ids,torch.Tensor)or input_ids.ndim!=2 or input_ids.shape[0]!=1 or input_ids.dtype not in (torch.int32,torch.int64):
        raise IntegrityError('Single-host integer input IDs required')
    expected=torch.as_tensor(tokenize_prompt(prompt),dtype=input_ids.dtype).reshape(-1).cpu()
    actual=input_ids.detach().reshape(-1).cpu()
    if not torch.equal(actual,expected):raise IntegrityError('Final IDs differ from full untruncated prompt tokenizer output')
    if int((actual==image_token_id).sum())!=count:
        raise IntegrityError('Image placeholders do not match the logical image budget')
    return actual


def audit_final_inputs(*,history,receipt,images_tensor,prompt,input_ids,tokenize_prompt,
                       original_question,image_token_id,generation_config,
                       vision_tokens_per_slot=None,context_limit=None,
                       forbidden_texts=(),forbidden_pixel_hashes=()):
    import torch
    if history.snapshot_id!=receipt.snapshot_id:raise IntegrityError('Processor receipt belongs to another snapshot')
    expected_pixels=tuple(s.host_pixel_hash for s in history.slots)
    if expected_pixels!=receipt.source_pixel_hashes or tuple(pixel_hash(x)for x in history.images)!=expected_pixels:
        raise IntegrityError('Image material/processor receipt mismatch')
    if any(value and value in prompt for value in forbidden_texts):raise IntegrityError('Privileged text sentinel in final prompt')
    if set(expected_pixels)&set(forbidden_pixel_hashes):raise IntegrityError('Privileged image sentinel in final slots')
    if not original_question or original_question not in prompt:
        raise IntegrityError('Original question/instruction/reasoning was changed or truncated')
    count=len(history.slots)
    if count!=history.budget:raise IntegrityError('History differs from logical image budget')
    actual=verified_prompt_tokens(prompt,input_ids,tokenize_prompt,image_token_id,count)
    crop_counts=[]
    for value in receipt.slot_tensors:
        if value.ndim not in (3,4):raise IntegrityError('Processor output has unsupported crop rank')
        crop_counts.append(1 if value.ndim==3 else value.shape[0])
    if len(crop_counts)!=count:raise IntegrityError('Incomplete processor receipt')
    blocks=_blocks(images_tensor,crop_counts);rows=[];start=0
    for slot,block,original,crops,processed_hash in zip(history.slots,blocks,receipt.slot_tensors,crop_counts,receipt.processor_input_pixel_hashes):
        expected_block=original.unsqueeze(0)if original.ndim==3 else original
        expected_block=expected_block.detach().to(device='cpu',dtype=block.dtype)
        actual_block=block.detach().cpu()
        if not torch.isfinite(actual_block).all()or actual_block.shape!=expected_block.shape or not torch.equal(actual_block,expected_block):
            raise IntegrityError('Actual final tensor differs from the selected slot processor output')
        row=asdict(slot);row.update(tensor_range=[start,start+crops],tensor_shape=list(block.shape),
            tensor_dtype=str(block.dtype),tensor_sha256=tensor_hash(actual_block),processor_input_pixel_hash=processed_hash)
        rows.append(row);start+=crops
    generated=generation_config.get('max_new_tokens')
    if type(generated)is not int or generated<0:raise IntegrityError('Explicit generation token reservation required')
    expanded=None
    if vision_tokens_per_slot is not None:
        if len(vision_tokens_per_slot)!=count or any(type(n)is not int or n<1 for n in vision_tokens_per_slot):
            raise IntegrityError('Explicit positive vision token count for each logical slot required')
        expanded=len(actual)-count+sum(vision_tokens_per_slot)
        if type(context_limit)is not int or context_limit<1:raise IntegrityError('Actual model context limit required')
        if expanded+generated>context_limit:raise IntegrityError('Expanded multimodal input plus generation exceeds context')
    return dict(status='VERIFIED_FINAL_INPUT_MATERIALS'if expanded is not None else 'VERIFIED_MATERIALS_PENDING_VISION_BUDGET',
        snapshot_id=history.snapshot_id,logical_image_slots=count,crop_count=start,slots=rows,
        prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),token_ids_sha256=tensor_hash(input_ids),
        text_and_placeholder_tokens=len(actual),expanded_input_tokens=expanded,reserved_generation_tokens=generated,
        generation_config_sha256=hashlib.sha256(canonical(generation_config)).hexdigest(),
        vision_budget_scope='Caller-provided host/model expansion contract; runtime observation still required',
        model_invocation_proven=False)


class AttachmentFeatureCache:
    """GPU features for independent supplemental images under one frozen episode model."""
    def __init__(self,limit):
        from collections import OrderedDict
        if type(limit) is not int or limit<0:raise ValueError('Invalid attachment cache byte limit')
        self.limit=limit;self.items=OrderedDict();self.bytes=0;self.signature=None
        self.hits=self.encodes=0

    def clear(self):
        self.items.clear();self.bytes=0;self.signature=None

    def bind(self,tower,scope):
        # No weight copies or SHA passes. In-place optimizer/load_state_dict operations
        # change the tensor version, while replacement changes the tensor identity.
        import torch
        if torch.is_grad_enabled() or any(layer.training for layer in tower.modules()):
            self.clear()
            return False
        try:
            weights=tuple((id(p),p.data_ptr(),p._version,p.dtype,p.device) for p in
                          (*tower.parameters(),*tower.buffers()))
        except RuntimeError:  # Inference tensors without version counters cannot be tracked.
            self.clear()
            return False
        signature=(scope,id(tower),id(tower.forward.__func__),tower.select_layer,tower.select_feature,
                   torch.is_autocast_enabled(),torch.get_autocast_gpu_dtype() if torch.is_autocast_enabled() else None,
                   weights)
        if signature!=self.signature:
            self.clear();self.signature=signature
        return True

    def feature(self,tower,block,token):
        # The receipt identifies the input; exact GPU equality also protects against a
        # stale receipt, in-place mutation, or a different invocation of the processor.
        import torch
        cached=self.items.get(token)
        if cached is not None:
            previous,features,_=cached
            if (previous.dtype!=block.dtype or previous.device!=block.device
                    or previous.shape!=block.shape or not torch.equal(previous,block)):
                raise IntegrityError('Cached visual input differs from the audited tensor')
            self.items.move_to_end(token);self.hits+=1
            return features
        features=tower(block)
        self.encodes+=1
        size=features.numel()*features.element_size()+block.numel()*block.element_size()
        if size<=self.limit:
            while self.items and self.bytes+size>self.limit:
                _,(_,_,removed)=self.items.popitem(last=False);self.bytes-=removed
            self.items[token]=(block.detach().clone(),features.detach().clone(),size);self.bytes+=size
        return features


@contextmanager
def separate_attachment_encoding(model,native_count,attachment_count=1,*,cache=None,scope=None,receipt_keys=(),expected_tensor=None):
    """Scope to the existing single-owner evaluator; restore the instance on all exits."""
    import torch
    if 'encode_images' in vars(model):
        raise IntegrityError('Cannot overlay another instance image encoder')
    original=model.encode_images
    sizes=[]
    def encode(images):
        if sizes or images.ndim!=4 or attachment_count<1 or images.shape[0]!=native_count+attachment_count:
            raise IntegrityError('Expected one native visual batch followed by one attachment')
        native=original(images[:native_count])
        use_cache=False
        if cache is not None:
            from llava.model.llava_arch import LlavaMetaModel
            from llava.model.multimodal_encoder.siglip_encoder import SiglipVisionTower
            tower=model.get_vision_tower()
            # Other encoders can implement temporal processing or a different projection.
            if (getattr(original,'__func__',None) is LlavaMetaModel.encode_images and type(tower) is SiglipVisionTower
                    and not model.training and not model.config.s2 and scope and len(receipt_keys)==attachment_count):
                if images is not expected_tensor:
                    raise IntegrityError('Visual encoder did not receive the audited image batch')
                use_cache=cache.bind(tower,scope)
        if use_cache:
            projector=model.get_mm_projector()
            extras=[projector(cache.feature(tower,images[i:i+1],receipt_keys[i-native_count]))
                    for i in range(native_count,images.shape[0])]
        else:extras=[original(images[i:i+1]) for i in range(native_count,images.shape[0])]
        if native.shape[0]!=native_count or any(v.shape[0]!=1 or v.shape[1:]!=native.shape[1:] for v in extras):
            raise IntegrityError('Invalid grouped image features')
        sizes.extend([native_count]+[1]*attachment_count)
        return torch.cat((native,*extras),dim=0)
    model.encode_images=encode
    try:
        yield sizes
        if sizes!=[native_count]+[1]*attachment_count:raise IntegrityError('Visual evidence did not reach the native encoder')
    finally:
        del model.encode_images
