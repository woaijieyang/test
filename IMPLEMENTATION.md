# Implementation Rationale

## Semantic Ownership

Generator is the only author of the executable instruction decomposition. Reviewer is an independent source-grounded auditor and may report findings plus local repair options, but never writes a replacement route. Adapter preserves and identifies source data. Renderer performs auditable text assembly and immutable snapshot freezing. Host owns dispatch, validation, bounded calls, recovery and release.

## Shared Semantics and Dataset Specialization

Both datasets use the same semantic acceptance contract and Runtime wire schemas. Dataset-specific rules and teaching assets are selected only by the Adapter Profile.

R2R and RxR each have ten fixed Generator Core cases and ten independent Reviewer Core cases. Core is always loaded in stable order. Dynamic retrieval supplements Core and is constrained to explicit dataset/role allowlists. Legacy assets are provenance only. Pair IDs document teaching lineage; they do not force a Reviewer verdict or create an execution dependency on a Generator Core case.

## Segmentation Principle

Read the complete instruction before deciding boundaries. A useful split requires a source-supported completed event, a distinct next objective, a supported next entry and a concrete local-focus benefit. A stage may contain multiple actions. Sentence boundaries, verb count, route length and landmark mentions are not sufficient split criteria.

Each stage must preserve Entry, Target, Process, Ending and Conditions. Preserve action order, ordinal origin, reference frame, temporal scope, negation, bounded motion, target identity, doorway crossing and terminal placement. Stage boundary never implies physical stop. An expected observation does not become a target unless the source commands movement to it.

## Review Principle

Reviewer evaluates Source Fidelity, Closure/Handoff and Segmentation Adequacy independently. Findings require direct evidence and a material execution or local-focus consequence. REVISE is for a repairable Candidate defect. UNRESOLVED is reserved for route-critical ambiguity in the Source itself. PASS means the candidate satisfies the language-level contract; it does not mean navigation success.

## Runtime Integrity

Profile, Rules, Core, Dynamic IDs, Prompt Components, Schema and Template Bundle are frozen for the complete G0–R0–G1–R1 task. R0 and R1 must review the exact snapshots later released. Provider receipts are bound to the request when the provider supplies a request hash. Technical/input fallback is never navigation-eligible. A valid Source fallback is returned exactly, without global whitespace or Unicode normalization.

## Engineering Boundary

No changes to AwareVLN Reason/Act, STOP, last_reasoning, image flow, action space, episode budget, online goal switching, memory or completion detection are part of this package. The Actor receives only the final rendered instruction string.

## Evidence Limits

Schema, protocol, regression and smoke tests verify engineering contracts only. They do not establish semantic accuracy, tokenizer invariance or navigation improvement. Real-model blind review, held-out evaluation and paired navigation rollouts are separate required experiments.
