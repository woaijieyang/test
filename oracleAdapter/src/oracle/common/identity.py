"""Lossless keys; no claim that a key proves the native state is Markovian."""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from functools import lru_cache


@dataclass(frozen=True)
class Context:
    scene_sha256: str
    profile_sha256: str
    body_action_sha256: str
    task_sha256: str
    protocol_sha256: str
    source_sha256: str
    environment_sha256: str
    backend_state_schema: str

    @lru_cache(maxsize=1024)
    def digest(self):
        if any(not value for value in asdict(self).values()):
            raise ValueError("Cache context cannot omit an identity dimension")
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()


def exact_state_key(values, reference_index, context: Context):
    """Preserve every supplied float bit, including height and orientation.

    The adapter must supply all native state relevant to future transitions.
    This avoids the known rounding alias; it is not a completeness theorem.
    """
    if reference_index < 0:
        raise ValueError("Invalid reference occurrence")
    numbers = tuple(float(v) for v in values)
    if not numbers or any(not math.isfinite(v) for v in numbers):
        raise ValueError("Finite native state required")
    return context.digest(), reference_index, tuple(v.hex() for v in numbers)
