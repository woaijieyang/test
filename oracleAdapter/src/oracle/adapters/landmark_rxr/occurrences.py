"""Match exact contiguous subpaths with global ordered boundary constraints."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Alignment:
    status: str
    intervals: tuple[tuple[int, int], ...]
    solutions_capped_at_two: int
    reason: str
    connectors: tuple[tuple[int, int], ...] = ()


def align_subpaths(full_path, subpaths):
    """Keep repeated visits and zero-length segments; refuse ambiguous identity.

    Each subpath must be an exact occurrence in the complete discrete path.
    Adjacent subpaths share their boundary occurrence. No spatial proximity,
    text similarity, or independent nearest-position matching is used.
    """
    full_path = tuple(full_path)
    subpaths = tuple(tuple(p) for p in subpaths)
    if not full_path or not subpaths or any(not p for p in subpaths):
        return Alignment("UNRESOLVED", (), 0, "empty path or subpath")
    # The number of retained histories is capped only after equivalent exact
    # boundary states are grouped. Two are enough to report ambiguity.
    states = {0: [()]}
    for segment in subpaths:
        next_states = {}
        for start, histories in states.items():
            end = start + len(segment) - 1
            if full_path[start:end + 1] != segment:
                continue
            for history in histories:
                next_states.setdefault(end, []).append(history + ((start, end),))
                next_states[end] = next_states[end][:2]
        states = next_states
    solutions = states.get(len(full_path) - 1, [])
    if len(solutions) == 1:
        return Alignment("EXACT_ORDERED_OCCURRENCES", solutions[0], 1, "")
    if len(solutions) > 1:
        return Alignment("AMBIGUOUS", (), 2, "multiple source occurrence alignments")
    return Alignment("UNRESOLVED", (), 0, "subpaths do not cover the ordered source path")


def align_with_source_connectors(full_path, subpaths):
    """Keep unannotated boundary edges explicitly; never omit source nodes.

    This is a separate mapping candidate. It cannot certify that the connector
    is physically executable, and refuses ambiguous occurrence assignments.
    """
    full = tuple(full_path)
    parts = tuple(tuple(p) for p in subpaths)
    strict = align_subpaths(full, parts)
    if strict.status == "EXACT_ORDERED_OCCURRENCES":
        # Already consumes every source edge; no positive-length gap can fit
        # between the fixed first and last occurrences without losing a part.
        return strict
    if not full or not parts or any(not p for p in parts):
        return Alignment("UNRESOLVED", (), 0, "empty source path")
    states = {0: [((), ())]}
    for segment_index, segment in enumerate(parts):
        next_states = {}
        for previous_end, histories in states.items():
            starts = (0,) if segment_index == 0 else range(previous_end, len(full))
            for start in starts:
                end = start + len(segment) - 1
                if end >= len(full) or full[start:end + 1] != segment:
                    continue
                for intervals, connectors in histories:
                    gap = ((previous_end, start),) if segment_index and start > previous_end else ()
                    value = (intervals + ((start, end),), connectors + gap)
                    bucket = next_states.setdefault(end, [])
                    if value not in bucket and len(bucket) < 2:
                        bucket.append(value)
        states = next_states
    solutions = states.get(len(full) - 1, [])
    if len(solutions) != 1:
        return Alignment("AMBIGUOUS" if solutions else "UNRESOLVED", (), min(2, len(solutions)),
                         "no unique ordered source occurrence mapping")
    intervals, connectors = solutions[0]
    return Alignment("ORDERED_WITH_EXPLICIT_SOURCE_CONNECTORS" if connectors else "EXACT_ORDERED_OCCURRENCES",
                     intervals, 1, "connector execution still unverified" if connectors else "", connectors)
