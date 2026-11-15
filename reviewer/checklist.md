# Reviewer layered checklist — exact same semantics as Generator
Use C01–C12 exactly as defined in shared/semantic_contract.md. This file only groups the work into layers; it does not add acceptance rules.

- L0 Integrity: actual frozen text and schema boundary. Renderer whitespace is not a semantic failure.
- L1 Coverage: all source-supported process events, target descriptors, conditions, quantities, ordinal classes, corrections, intermediate stops, returns and final pose. Record source_coverage rows.
- L2 Dependencies: order, trigger ownership, condition scope, same-event refinements, entity identity, viewpoint/time, count origin and correction scope.
- L3 Five meanings: for each stage, entry, prescribed process, target identity, ending basis and active conditions. Check actual English, not audit paraphrase.
- L4 Handoff: every adjacent previous exit versus next entry; carry only uniquely retained pose/entity state. No fabricated sofa-side endpoint or automatic repeated From clause.
- L5 Grouping: detect both unsupported cuts and meaningful distinct objectives buried together. Short instructions are not exempt; every verb is not a goal.
- L6 Bidirectional readback: every source requirement survives and every candidate command is source-supported; rendered English contains the complete plan.

A finding must have an exact source quote, exact candidate quote unless genuinely omitted, source requirement IDs, a concrete defect, an execution consequence and one local repair operation. A suggestion is advisory; generator independently checks it against the same shared contract.


## Runtime contract and R1 recheck

The live Reviewer dimensions are `source_fidelity`, `closure_handoff`, and `segmentation_adequacy`. Return the exact active schema fields: `source_coverage`, ordered `layer_checks`, `findings`, `stage_checks`, `handoffs`, and `prior_finding_reviews`. Candidate evidence items are `{subtask_index, quote}`; each quote belongs to the cited candidate stage.

R0 must return `prior_finding_reviews: []`. R1 receives the frozen R0 review, R0 candidate and R0 rendered text in a fresh session. For every R0 finding, return exactly one ordered `prior_finding_reviews` row: `resolved`, `partially_resolved`, or `unresolved`, with evidence from the new candidate and a concise explanation. Independently inspect the whole new candidate and report newly introduced defects as ordinary findings. Never trust Generator's response as proof. R1 PASS requires all old findings resolved, no new blocking finding, all three dimensions pass, complete source coverage, supported stages and supported handoffs.

For a cross-stage handoff defect, cite both the preceding stage's exit and the next stage's entry using their respective indices. The repair target may remain only the next stage; evidence indices are not required to equal repair-target indices.
