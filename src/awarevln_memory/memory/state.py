from __future__ import annotations

import copy
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

import torch
from torch import Tensor


@dataclass
class MemoryItem:
    moment: Tensor
    policy_call_id: int
    item_id: str
    event_type: Optional[str] = None
    importance: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        moment = self.moment.detach().to(device="cpu", dtype=torch.float16)
        if moment.ndim == 3 and moment.shape[0] == 1:
            moment = moment.squeeze(0)
        if moment.ndim != 2:
            raise ValueError(
                "A memory item must be [moment_tokens, hidden_size], got "
                f"{tuple(moment.shape)}"
            )
        self.moment = moment.contiguous()


class EpisodeMemory:
    """Causal recent, event, and full-episode memory for one episode."""

    CONDITIONS = {"full", "recent", "empty", "shuffle", "archive"}

    def __init__(
        self,
        recent_calls: int = 4,
        max_event_items: int = 8,
        write_threshold: float = 0.5,
        max_archive_items: int = 256,
    ) -> None:
        if min(recent_calls, max_event_items, max_archive_items) <= 0:
            raise ValueError("Memory capacities must be positive")
        self.recent_calls = recent_calls
        self.max_event_items = max_event_items
        self.write_threshold = write_threshold
        self.max_archive_items = max_archive_items
        self.recent: deque[MemoryItem] = deque(maxlen=recent_calls)
        self.events: list[MemoryItem] = []
        self.archive: deque[MemoryItem] = deque(maxlen=max_archive_items)
        self.current_policy_call = 0

    def __len__(self) -> int:
        return len(self.recent) + len(self.events)

    def clear(self) -> None:
        self.recent.clear()
        self.events.clear()
        self.archive.clear()
        self.current_policy_call = 0

    def clone(self) -> "EpisodeMemory":
        return copy.deepcopy(self)

    def observe(
        self,
        moment: Tensor,
        policy_call_id: int,
        *,
        write_probability: Optional[float] = None,
        force_event: bool = False,
        event_type: Optional[str] = None,
        importance: Optional[float] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> MemoryItem:
        probability = float(write_probability or 0.0)
        score = probability if importance is None else float(importance)
        item = MemoryItem(
            moment=moment,
            policy_call_id=int(policy_call_id),
            item_id=f"moment_{policy_call_id:06d}",
            event_type=event_type,
            importance=score,
            metadata=dict(metadata or {}),
        )
        self.current_policy_call = max(
            self.current_policy_call,
            int(policy_call_id) + 1,
        )
        archive_item = copy.copy(item)
        archive_item.item_id = f"archive_{policy_call_id:06d}"
        self.archive.append(archive_item)
        self.recent.append(item)
        should_write = force_event or (
            write_probability is not None
            and probability >= self.write_threshold
        )
        if should_write:
            event = copy.copy(item)
            event.item_id = f"event_{policy_call_id:06d}"
            self.events.append(event)
            if len(self.events) > self.max_event_items:
                # Preserve chronological order after evicting the least useful
                # event.  Ties remove the oldest item.
                remove_index = min(
                    range(len(self.events)),
                    key=lambda index: (
                        self.events[index].importance,
                        self.events[index].policy_call_id,
                    ),
                )
                self.events.pop(remove_index)
        return item

    def remove_event(self, event_id: str) -> "EpisodeMemory":
        clone = self.clone()
        clone.events = [
            item for item in clone.events if item.item_id != event_id
        ]
        return clone

    def _condition_items(
        self,
        condition: str,
        remove_event_id: Optional[str],
    ) -> list[tuple[MemoryItem, int]]:
        if condition not in self.CONDITIONS:
            raise ValueError(
                f"Unknown memory condition {condition!r}; "
                f"expected {sorted(self.CONDITIONS)}"
            )
        recent = list(self.recent)
        events = [
            item
            for item in self.events
            if item.item_id != remove_event_id
        ]
        if condition == "empty":
            return []
        if condition == "recent":
            return [(item, 0) for item in recent]
        if condition == "archive":
            return [
                (item, 2)
                for item in self.archive
                if item.item_id != remove_event_id
            ]
        return [(item, 0) for item in recent] + [
            (item, 1) for item in events
        ]

    def as_tensors(
        self,
        *,
        condition: str = "full",
        remove_event_id: Optional[str] = None,
        device: Optional[torch.device | str] = None,
    ) -> dict[str, Any]:
        typed_items = self._condition_items(condition, remove_event_id)
        if not typed_items:
            return {
                "memory_moments": None,
                "memory_mask": None,
                "memory_types": None,
                "memory_ages": None,
                "item_ids": [],
            }
        items, types = zip(*typed_items)
        noncausal = [
            item.item_id
            for item in items
            if item.policy_call_id >= self.current_policy_call
        ]
        if noncausal:
            raise RuntimeError(
                "Memory contains current/future policy calls: "
                f"{noncausal[:8]} (current={self.current_policy_call})"
            )
        moments = torch.stack([item.moment for item in items], dim=0)
        ages = torch.tensor(
            [
                max(0, self.current_policy_call - item.policy_call_id)
                for item in items
            ],
            dtype=torch.long,
        )
        if condition == "shuffle":
            event_indices = [
                index for index, item_type in enumerate(types) if item_type == 1
            ]
            if len(event_indices) > 1:
                shuffled = ages[event_indices].flip(0)
                ages[event_indices] = shuffled
        result = {
            "memory_moments": moments.unsqueeze(0),
            "memory_mask": torch.ones(
                1,
                len(items),
                dtype=torch.bool,
            ),
            "memory_types": torch.tensor(types, dtype=torch.long).unsqueeze(0),
            "memory_ages": ages.unsqueeze(0),
            "item_ids": [item.item_id for item in items],
        }
        if device is not None:
            for key in (
                "memory_moments",
                "memory_mask",
                "memory_types",
                "memory_ages",
            ):
                result[key] = result[key].to(device)
        return result

    @classmethod
    def from_items(
        cls,
        recent: Iterable[MemoryItem],
        events: Iterable[MemoryItem],
        *,
        recent_calls: int = 4,
        max_event_items: int = 8,
        write_threshold: float = 0.5,
        archive: Optional[Iterable[MemoryItem]] = None,
        max_archive_items: int = 256,
    ) -> "EpisodeMemory":
        state = cls(
            recent_calls, max_event_items, write_threshold, max_archive_items
        )
        for item in list(recent)[-recent_calls:]:
            state.recent.append(copy.deepcopy(item))
        state.events = [
            copy.deepcopy(item)
            for item in list(events)[-max_event_items:]
        ]
        source_archive = list(archive) if archive is not None else []
        for item in source_archive[-max_archive_items:]:
            archived = copy.deepcopy(item)
            if not archived.item_id.startswith("archive_"):
                archived.item_id = f"archive_{archived.policy_call_id:06d}"
            state.archive.append(archived)
        all_items = (
            list(state.recent) + state.events + list(state.archive)
        )
        if all_items:
            state.current_policy_call = (
                max(item.policy_call_id for item in all_items) + 1
            )
        return state
