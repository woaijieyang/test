"""Snapshot-scoped retrieval contracts. No simulator or model startup."""
from dataclasses import dataclass
from hashlib import sha256
from collections.abc import Mapping
import numpy as np
from ..storage.archive import freeze

@dataclass(frozen=True)
class MemoryQuery:
    episode_uid: str
    snapshot_id: str
    current_frame_uid: str
    current_capture_seq: int
    cutoff_capture_seq: int
    cutoff_event_seq: int
    instruction: str
    current_position: tuple | None = None
    pose_map_version: int | None = None
    last_reasoning: str | None = None
    last_reasoning_event_seq: int | None = None
    decision_event_seq: int | None = None

    def __post_init__(self):
        for name in ('episode_uid','snapshot_id','current_frame_uid','instruction'):
            if not isinstance(getattr(self,name),str) or not getattr(self,name).strip():
                raise ValueError('Nonempty query identity/instruction required: '+name)
        for name in ('current_capture_seq','cutoff_capture_seq','cutoff_event_seq'):
            if type(getattr(self,name)) is not int or getattr(self,name)<0:
                raise ValueError('Nonnegative query ordinal required: '+name)
        if self.cutoff_capture_seq > self.current_capture_seq:
            raise ValueError('Published cutoff cannot follow current observation')
        decision_cutoff=self.cutoff_event_seq if self.decision_event_seq is None else self.decision_event_seq
        if type(decision_cutoff)is not int or decision_cutoff<self.cutoff_event_seq:
            raise ValueError('Decision event cannot precede published snapshot cutoff')
        if self.last_reasoning is not None:
            if not isinstance(self.last_reasoning,str) or type(self.last_reasoning_event_seq) is not int or not 0<=self.last_reasoning_event_seq<decision_cutoff:
                raise ValueError('Reasoning must have an available causal event identity')
        elif self.last_reasoning_event_seq is not None:
            raise ValueError('Reasoning timestamp without reasoning')
        if self.current_position is not None:
            value=np.asarray(self.current_position,dtype=float)
            if value.shape!=(3,) or not np.isfinite(value).all() or self.pose_map_version is None:
                raise ValueError('Finite versioned position required')
            object.__setattr__(self,'current_position',tuple(float(x)for x in value))

    @property
    def instruction_hash(self):return sha256(self.instruction.encode()).hexdigest()

@dataclass(frozen=True,eq=False)
class EncodedQuery:
    instruction_hash: str
    model_identity_hash: str
    tokenizer_identity_hash: str
    windows: np.ndarray
    # Main instruction is never replaced by last reasoning. Optional supplement only.
    reasoning: np.ndarray | None = None
    reasoning_hash: str | None = None

    def __post_init__(self):
        for name in ('instruction_hash','model_identity_hash','tokenizer_identity_hash'):
            if not isinstance(getattr(self,name),str) or not getattr(self,name):
                raise ValueError('Explicit encoded-query provenance required')
        for name in ('windows','reasoning'):
            value=getattr(self,name)
            if value is None:
                if name=='windows':raise ValueError('Full-instruction windows required')
                continue
            value=np.asarray(value)
            if value.ndim!=2 or min(value.shape)<1 or value.dtype.kind!='f' or not np.isfinite(value).all() or np.any(np.linalg.norm(value,axis=1)==0):
                raise ValueError('Finite nonzero feature matrix required')
            # Reuse bytes-backed immutable arrays; mutable caller inputs are copied.
            owner=value
            while isinstance(owner,np.ndarray) and owner.base is not None:owner=owner.base
            immutable=value if isinstance(owner,bytes) and not value.flags.writeable else freeze(value)
            object.__setattr__(self,name,immutable)
        if (self.reasoning is None)!=(self.reasoning_hash is None):
            raise ValueError('Reasoning feature/source identity mismatch')

@dataclass(frozen=True)
class ViewRef:
    episode_uid: str
    snapshot_id: str
    frame_uid: str
    capture_seq: int
    event_seq: int
    env_step: int
    image_hash: str
    host_image_hash: str
    position: tuple | None
    pose_map_version: int | None
    entity_refs: tuple
    room_hint: str | None
    host_transform_hash: str | None = None
    source_snapshot_id: str | None = None

@dataclass(frozen=True)
class Candidate:
    view: ViewRef
    score: float
    ranks: tuple
    semantic_score: float | None
    visual_score: float | None
    matched_categories: tuple
    available_fields: tuple
    legality: tuple = ('same_episode','pinned_snapshot','within_cutoff','source_verified')

@dataclass(frozen=True)
class CandidateResult:
    snapshot_id: str
    views: tuple[ViewRef,...]
    ranked: tuple[Candidate,...]
    channels: Mapping
    rejected: tuple
    category_cues: tuple


@dataclass(frozen=True)
class EvidenceBundle:
    seed_ref: str
    views: tuple[ViewRef,...]
    execution_refs: tuple
    entity_refs: tuple
    edge_types: tuple
    time_span: tuple
    pose_map_version: int | None
    floor_id: str | None
    relevance: float
    missing_evidence: tuple
    selection_reason: str

@dataclass(frozen=True)
class Selection:
    slots: tuple[ViewRef,...]
    groups: tuple[EvidenceBundle,...]
    protected_recent: tuple
    rejected: tuple
    fallback_reason: str | None
    budget: int


@dataclass(frozen=True)
class CategoryVocabulary:
    labels: tuple[str,...]
    source_sha256: str
    ordered_labels_sha256: str

    @classmethod
    def from_bytes(cls,raw):
        if not isinstance(raw,bytes):raise TypeError('Exact original vocabulary bytes required')
        labels=[]
        # Same parsing and unknown/duplicate handling as pinned ObjectClasses.
        for line in raw.decode('utf-8').splitlines():
            name=line.strip()
            if name and name!='unknown' and name not in labels:labels.append(name)
        if not labels:raise ValueError('Empty detector vocabulary')
        import json
        ordered=json.dumps(labels,ensure_ascii=False).encode()
        return cls(tuple(labels),sha256(raw).hexdigest(),sha256(ordered).hexdigest())

    @classmethod
    def from_file(cls,path):
        from pathlib import Path
        return cls.from_bytes(Path(path).read_bytes())
