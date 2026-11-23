# RxR authoring, data loading and failure boundaries

This maintenance change protects the reviewed teaching work against silent data drift. It does not change the source instructions, candidate routes, selected example counts, retrieval scores, fixed Core order, model-facing schemas, Renderer or bounded semantic-repair workflow. Common rules and R2R assets remain protected. The immutable evaluation anchor is commit `da277a0f9a6ee7d8eebb78dafa852e469cd1a50e`.

## Offline authoring

The training builder now computes and validates the entire eight-source, twenty-four-template bundle in memory before publishing any file. Duplicate lesson names, instruction identities or exact source strings are rejected before source download or construction. The registry is built from the explicit expected output map, not from whichever JSON files happen to be present on disk. An unexpected JSON, missing previously registered file, symbolic-link path or independently modified output blocks publication.

A pre-existing registry authorizes replacement only of its exact previously pinned bytes. It does not authorize absorbing unrelated files or silently changing the source inventory. All planned bytes and the complete read set are checked before replacement. Each replacement is atomic, the registry is published last, and ordinary write exceptions roll back the tool's own completed replacements. Concurrent edits are not overwritten during rollback. A process crash is not a transactional filesystem guarantee: incomplete publication is detected by the registry hashes and must not be served. Use an isolated maintenance checkout, never hot-edit an active worker.

Use `python -B tools/build_rxr_teaching.py --verify-upstream` to verify official archive and record bytes before construction. Use `python -B tools/build_rxr_teaching.py --check` to compare all authored outputs and the registry without writing. A missing upstream resource or mismatched archive digest is an error, not permission to fabricate source provenance. The online loader never downloads or rebuilds teaching data.

## Exact mutation evidence

`tools/rxr_evidence_alignment.py` maps one declared authored edit through exact candidate quotations. It verifies that the candidate differs by exactly that declared span. When identical quoted phrases occur at different positions and would map to different text or changed/unchanged states, the tool refuses to guess the first occurrence. The author must use a longer contextual quotation or an explicit exact occurrence. Repeated unaffected words that map identically may remain unchanged. This mechanical property does not certify that the source event or a proposed stage boundary is semantically correct.

The training diagnostic builder uses this mapper for coverage, stage checks and handoff evidence. Actual candidate explanations and dependent inherited context remain authored explicitly. The existing eight specifications should reproduce the same template bytes; this change is intended to prevent later corruption rather than add new route semantics.

## Online identity checks

The RxR training loader checks an exact registry of eight distinct source records and twenty-four unique template identities. Every filename, role, Profile, language, split, guide role, instruction, scan, path, raw instruction digest, record digest, archive identity and pair identity is bound to that registry. Paired reviews must inspect the actual corresponding Generator subtasks. Extra or nested JSON files are rejected rather than silently loaded.

The library gate compares parsed in-memory training rows with the currently pinned files, not only their identity fields. Thus stale or edited teaching bodies cannot masquerade as the current registry. This is an integrity gate, not an online natural-language judge. Existing task-level frozen bundles still govern G0/G1 and R0/R1; this gate does not add a new model role, retry loop or semantic fallback rule.

## Verification

Regression tests operate on temporary copies of the committed source registry and templates. They cover wrong source identity after hash repinning, wrong pair identity, paired-candidate drift, duplicate instruction identities, extra files, symbolic links, stale in-memory rows, invalid roles, immutable read/check behavior, independently edited files, late validation failure, simulated write failure and registry-last publication. Evidence tests distinguish repeated occurrences, unchanged repeats, deletion and undeclared additional edits.

The current full regression suite, deterministic compilation, official-source check and independent R2R baseline comparisons remain required. No test in this maintenance change estimates navigation SR or establishes causal recovery of an evaluation episode. Previously identified semantic review items remain in `docs/RXR_TEACHING_REPAIR.md`; they are not silently relabeled as solved by these data checks.
