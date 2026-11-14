"""Opt-in diagnostic at the causal language model prefill boundary for a single decision."""
from contextlib import contextmanager
import torch
from ..map_memory.storage.store import IntegrityError


@contextmanager
def observe_language_prefill(model, input_ids, image_token_id):
    """Compare each projected image and each text run to its actual first-forward embedding."""
    if input_ids.ndim!=2 or input_ids.shape[0]!=1:
        raise ValueError("A single host decision is required")
    ids=input_ids[0]
    placeholders=torch.where(ids==image_token_id)[0].tolist()
    projections=[]
    record={}

    def projected(module,args,output):
        if output.ndim!=3 or output.shape[1]==0:
            raise IntegrityError("Unexpected image projector layout")
        projections.extend(output.detach().unbind(0))

    def entering(module,args,kwargs):
        if record:return
        embeds=kwargs.get("inputs_embeds")
        if embeds is None or embeds.ndim!=3 or embeds.shape[0]!=1:
            raise IntegrityError("First language forward has no batch-one prefill embeddings")
        if len(projections)!=len(placeholders):raise IntegrityError("Image placeholder count differs from projections")
        patches=[block.shape[0] for block in projections]
        expected=len(ids)-len(placeholders)+sum(patches)
        if embeds.shape[1]!=expected:raise IntegrityError("Multimodal sequence length differs at language prefill")
        mask=kwargs.get("attention_mask")
        if mask is None or tuple(mask.shape)!=(1,expected) or not bool(mask.eq(1).all()):
            raise IntegrityError("A prefill token is missing from the attention mask")
        positions=kwargs.get("position_ids")
        if positions is not None and not torch.equal(positions,torch.arange(expected,device=positions.device)[None,:]):
            raise IntegrityError("Language prefill positions are not consecutive")
        cursor=0;previous=0;segments=[]
        for slot,stop in enumerate([*placeholders,len(ids)]):
            text_ids=ids[previous:stop]
            if len(text_ids):
                reference=model.get_input_embeddings()(text_ids)
                if not torch.equal(embeds[0,cursor:cursor+len(text_ids)],reference.to(embeds)):
                    raise IntegrityError("Text embedding order differs at language prefill")
                cursor+=len(text_ids)
            if slot<len(projections):
                block=projections[slot];end=cursor+len(block)
                if not torch.equal(embeds[0,cursor:end],block.to(embeds)):
                    raise IntegrityError("Projected image differs at language prefill")
                segments.append([cursor,end]);cursor=end
            previous=stop+1
        if cursor!=expected:raise IntegrityError("Incomplete language prefill coverage")
        record.update(expanded_tokens=expected,text_tokens=len(ids)-len(placeholders),image_segments=segments,
                      attention_tokens=int(mask.sum()),explicit_position_ids=positions is not None,
                      projection_dtype=str(projections[0].dtype) if projections else None,language_dtype=str(embeds.dtype))
        projections.clear()

    first=model.get_mm_projector().register_forward_hook(projected)
    try:
        second=model.get_llm().register_forward_pre_hook(entering,with_kwargs=True)
        try:
            yield record
            if not record:raise IntegrityError("No language prefill observed")
        finally:second.remove()
    finally:first.remove()
