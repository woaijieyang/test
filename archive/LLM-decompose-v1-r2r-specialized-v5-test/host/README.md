# Host: deterministic compiler, validation, source-bound workflow

`compile.py`: reads `shared/semantic_contract.md`, role prompt, active Schema, and source-selected teaching examples. `template_selector.py`: fixed 35-case library per role/profile, deterministic 3-core+5-adaptive default, exact source exclusion, frozen per task. It never calls an LLM; `mode='all'` explicitly permits all35 for ablation.

`protocol.py`: checks G0/G1 full Schema, one stage_audit per stage, source and actual English quotes, supported ending type, one handoff per pair; reviewer L0–L6, stage checks, source_coverage, findings and verdict; repair one-to-one finding dispositions. This is structural evidence checking, **not** a semantic engine or third reviewer.

`run.py`: `run_record(source, transport, pins, example_count=8, selection_mode='adaptive')` selects both role example-ID lists once, stores them in event hashes/results, follows bounded G0→R0→optional G1→R1. G1 uses identical selected Generator source cases, R1 identical Reviewer cases. Renderer freezes source envelope & single-LF stages before R0/R1. Only matching pass releases candidate text; otherwise exact original fallback with distinct reason. No silent per-episode win selection.

Transport must supply true model/effort/request ID metadata and full output JSON; no default provider is configured. Missing Stage audit is rejected before dispatch, never repaired by fake Reviewer prose. For actual navigation, only `result['instruction']` is sent to existing AwareVLN; metadata, audit and examples remain offline. Real tokenizer/chat template and image IDs must be captured by the deployed host to establish final request identity.
