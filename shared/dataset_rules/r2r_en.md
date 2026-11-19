# R2R English Dataset Guidance

This file supplements the shared semantic contract for R2R English instructions. It does not replace, weaken, or redefine any shared acceptance criterion.

## R2R-specific risk patterns

R2R instructions often express a compact, locally grounded route through ordered movement clauses, reference landmarks, room or doorway transitions, ordinal target choices, and terminal placements. Treat these as patterns to inspect, not as dataset-wide assumptions or segmentation triggers.

- Reconstruct the complete source event sequence before choosing boundaries. A short route may contain multiple independently completed objectives; a longer route may remain one continuous maneuver.
- Distinguish a preparatory orientation change from a completed navigation objective. A turn is not automatically a stage, but a completed turn-and-transition can establish a supported handoff when a distinct next objective follows.
- Preserve the exact role of each scene entity. A landmark can orient or disambiguate a path without becoming a destination; an expected observation does not prove arrival, crossing, or entry.
- Preserve ordinal target identity and its counting origin. "First", "second", "third", and equivalent descriptions must remain attached to the region and direction that define the count.
- Keep approach, pass-by, crossing, entry, arrival, and stationary placement distinct. Do not strengthen one event into another.
- Keep endpoint refinements, side relations, and terminal placement details attached to the movement and target they constrain. Do not create a new stage merely because a later clause describes the same endpoint more precisely.
- Keep temporal triggers and the actions they govern together unless the source establishes a completed event and a distinct subsequent objective with a useful supported handoff.
- Preserve source ambiguity when an unclear landmark, ordinal, direction, or transition changes route execution. Do not silently normalize likely transcription errors.

## Template use

The fixed R2R Generator and Reviewer Core examples provide stable semantic decision-boundary calibration. Dynamic examples provide additional source-feature-matched cases. Core is unconditional and ordered; dynamic examples supplement it and must never replace it.

A teaching case is transferable only when the current source and candidate exhibit the same semantic relation and the same relevant event completion. Do not transfer a decision based only on shared nouns, room names, object names, or surface keywords.

Reviewer examples are calibration evidence, not verdict votes. The Reviewer must independently inventory the current source requirements, inspect the candidate evidence, evaluate the existing L0-L6 checks, and only then consult the closest teaching cases. A teaching verdict is local to its own source/candidate pair.

No rule in this file determines a fixed stage count, word-count threshold, or split/keep ratio. The shared semantic contract remains authoritative for every final decision.
