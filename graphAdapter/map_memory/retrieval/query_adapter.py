"""Lossless CLIP token windows; no model, simulator or host side effects."""
from dataclasses import dataclass

@dataclass(frozen=True)
class InstructionWindow:
    start: int
    end: int
    token_ids: tuple[int, ...]
    text: str
    text_roundtrip_exact: bool


def window_instruction(instruction, tokenizer, *, overlap=16):
    """Use explicit token IDs for encoding; decoded text is an audit rendering.

    Capacity comes from the bound tokenizer, including its two special tokens.
    Never call its truncating batch API. Original token intervals are exhaustive.
    """
    if not isinstance(instruction, str) or not instruction.strip():
        raise ValueError('A nonempty full instruction is required')
    context = tokenizer.context_length
    if type(context) is not int or context < 3:
        raise ValueError('Tokenizer must expose a valid actual context length')
    capacity = context - 2
    if type(overlap) is not int or not 0 <= overlap < capacity:
        raise ValueError('Overlap must be nonnegative and smaller than payload capacity')
    tokens = tuple(tokenizer.encode(instruction))
    special = (tokenizer.sot_token_id, tokenizer.eot_token_id)
    if not tokens or any(type(t) is not int or t < 0 for t in tokens + special):
        raise ValueError('Tokenizer returned invalid token IDs')
    if special[0] == special[1] or any(t in special for t in tokens):
        raise ValueError('Instruction contains reserved CLIP boundary tokens')
    windows = []
    start = 0
    while start < len(tokens):
        end = min(start + capacity, len(tokens))
        # Byte-level token boundaries can expand after rendering/re-encoding.
        # Shrink only this window; the next window still covers every raw token.
        while end > start:
            payload = tokens[start:end]
            text = tokenizer.decode(list(payload))
            roundtrip = tuple(tokenizer.encode(text))
            if len(roundtrip) <= capacity:
                break
            end -= 1
        if end == start:
            raise ValueError('A token cannot be rendered within tokenizer capacity')
        windows.append(InstructionWindow(start, end, (special[0], *payload, special[1]),
                                         text, roundtrip == payload))
        if end == len(tokens):
            break
        start = max(start + 1, end - overlap)
    return tuple(windows)


class QueryEncoder:
    """Use the private perception worker's existing CLIP; never load a new model.

    Calls must stay on its owning worker thread. This is not a main-VLM reader.
    Immutable text features can be reused across snapshots and episodes; selected
    candidate lists and poses are deliberately not stored here.
    """
    def __init__(self,models,model_identity,vocabulary,*,overlap=16,batch_windows=16,max_bytes=4*1024*1024):
        import threading
        from collections import OrderedDict
        from ..storage.archive import IntegrityError,canonical,digest
        from .contracts import CategoryVocabulary
        if type(batch_windows)is not int or batch_windows<1 or type(max_bytes)is not int or max_bytes<0:
            raise ValueError('Positive batch size and nonnegative cache budget required')
        if not isinstance(vocabulary,CategoryVocabulary):raise TypeError('Source-bound vocabulary required')
        if (models.clip_model_hash!=model_identity['weights']['open_clip_pytorch_model.bin']
                or models.preprocess_hash!=model_identity['preprocess_hash']
                or vocabulary.source_sha256!=model_identity['vocabulary_sha256']
                or models.class_vocabulary_hash!=vocabulary.ordered_labels_sha256):
            raise IntegrityError('Perception model/preprocess/vocabulary identity mismatch')
        self.model=models.clip_model;self.tokenizer=models.clip_tokenizer
        if self.model.training or self.model.context_length!=self.tokenizer.context_length:
            raise IntegrityError('Frozen CLIP and matching actual tokenizer context required')
        if type(overlap)is not int or not 0<=overlap<self.tokenizer.context_length-2:
            raise ValueError('Invalid tokenizer overlap')
        self.owner=threading.get_ident();self.closed=False
        self.model_identity_hash=digest(canonical(model_identity))
        self.tokenizer_identity_hash=digest(canonical(dict(encoder=self.tokenizer.encoder,
            context_length=self.tokenizer.context_length,sot=self.tokenizer.sot_token_id,eot=self.tokenizer.eot_token_id)))
        self.overlap=overlap;self.batch_windows=batch_windows;self.max_bytes=max_bytes
        self.cache=OrderedDict();self.cache_bytes=0;self.cache_hits=0;self.model_batches=0

    def _check(self):
        import threading
        if self.closed:raise RuntimeError('Query encoder is closed')
        if threading.get_ident()!=self.owner:raise RuntimeError('Private CLIP query encoder called from another thread')
        if self.model.training:raise RuntimeError('CLIP training mode changed during retrieval session')

    def _key(self,text):
        from hashlib import sha256
        return (sha256(text.encode()).hexdigest(),self.model_identity_hash,self.tokenizer_identity_hash,self.overlap)

    def _encode_text(self,text):
        import torch,numpy as np
        from ..storage.archive import freeze,IntegrityError
        key=self._key(text)
        if key in self.cache:
            value,size=self.cache.pop(key);self.cache[key]=(value,size);self.cache_hits+=1;return value
        windows=window_instruction(text,self.tokenizer,overlap=self.overlap)
        device=next(self.model.parameters()).device
        chunks=[]
        with torch.inference_mode():
            for start in range(0,len(windows),self.batch_windows):
                batch=windows[start:start+self.batch_windows]
                tokens=torch.zeros((len(batch),self.tokenizer.context_length),dtype=torch.long,device=device)
                for i,window in enumerate(batch):tokens[i,:len(window.token_ids)]=torch.tensor(window.token_ids,dtype=torch.long,device=device)
                features=self.model.encode_text(tokens)
                if features.ndim!=2 or features.shape[0]!=len(batch) or not torch.isfinite(features).all():
                    raise IntegrityError('CLIP returned invalid text features')
                norms=features.float().norm(dim=-1,keepdim=True)
                if (norms==0).any():raise IntegrityError('CLIP returned zero text features')
                chunks.append((features.float()/norms).cpu().numpy());self.model_batches+=1
        features=freeze(np.concatenate(chunks,axis=0))
        value=(features,windows)
        # Conservative accounting includes window audit text and Python token IDs.
        size=features.nbytes+sum(len(w.text.encode())+len(w.token_ids)*36+256 for w in windows)+512
        if size<=self.max_bytes:
            while self.cache and self.cache_bytes+size>self.max_bytes:
                _,(_,removed)=self.cache.popitem(last=False);self.cache_bytes-=removed
            self.cache[key]=(value,size);self.cache_bytes+=size
        return value

    def encode(self,query):
        from hashlib import sha256
        from .contracts import EncodedQuery
        self._check()
        full,_=self._encode_text(query.instruction)
        reasoning=None;reasoning_hash=None
        if query.last_reasoning:
            reasoning,_=self._encode_text(query.last_reasoning)
            reasoning_hash=sha256(query.last_reasoning.encode()).hexdigest()
        return EncodedQuery(query.instruction_hash,self.model_identity_hash,self.tokenizer_identity_hash,
                            full,reasoning,reasoning_hash)

    def audit(self,text):
        self._check()
        cached=self.cache.get(self._key(text))
        windows=cached[0][1]if cached is not None else window_instruction(text,self.tokenizer,overlap=self.overlap)
        return dict(tokenizer_identity_hash=self.tokenizer_identity_hash,context_length=self.tokenizer.context_length,
            overlap=self.overlap,covered_tokens=windows[-1].end,
            windows=tuple(dict(start=w.start,end=w.end,token_ids=w.token_ids,text_roundtrip_exact=w.text_roundtrip_exact)for w in windows))

    def close(self):
        self.cache.clear();self.cache_bytes=0;self.closed=True
        # The caller owns the perception model and its lifetime.
        self.model=None;self.tokenizer=None
