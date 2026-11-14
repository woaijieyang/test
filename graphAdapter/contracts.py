"""Stage-independent immutable message contracts. No evaluator objects cross this boundary."""
from dataclasses import dataclass
from typing import Optional, Tuple, Mapping, Any

from .observation_packet import ObservationPacket

@dataclass(frozen=True)
class GraphUpdate:
    frame_uid: str
    geometry_status: str
    perception_status: str
    skip_reason: Optional[str]
    contribution_refs: Tuple[str, ...]
    target_pose_map_version: Optional[int]
    complete_seq: int

@dataclass(frozen=True)
class PublishedSnapshot:
    snapshot_id: str
    graph_revision: int
    pose_map_version: int
    floor_revision: int
    semantic_revision: int
    publish_seq: int
    manifest: Mapping[str, str]
    available_decision: Optional[int] = None

@dataclass(frozen=True)
class MemoryPacket:
    snapshot_id: str
    query_id: str
    cutoff_event_seq: int
    history_slots: Tuple[str, ...]
    materialized_fields: Mapping[str, Any]
    facts: Tuple[Mapping[str, Any], ...]
    relative_geometry: Optional[Mapping[str, Any]]

@dataclass(frozen=True)
class HostInputAudit:
    decision_id: int
    frame_uid: str
    cutoff_event_seq: int
    image_slots: Tuple[Mapping[str, Any], ...]
    text_tokens: int
    prompt_hash: str
    tokenizer_hash: str
    generation_config_hash: str

def white_observation(rgb, depth, *, instruction, collision=None):
    """Only explicit arguments are accepted, never observation/info/episode dictionaries."""
    if not isinstance(instruction, str):
        raise TypeError("instruction must be the original text string")
    if collision not in (True, False, None):
        raise TypeError("collision must be boolean or unknown")
    return dict(rgb=rgb, depth=depth, instruction=instruction, collision=collision)
