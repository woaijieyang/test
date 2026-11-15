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
