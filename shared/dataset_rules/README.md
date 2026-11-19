# Dataset-specific rules

- `r2r_en.md` is loaded only for Adapter profile `r2r-en`, after the shared semantic contract and before the R2R fixed Core and Dynamic examples.
- `rxr_en_us.md` is loaded only for Adapter profile `rxr-en-us`. The RxR shared semantic rules are followed by the matching role-specific guidance in `generator/dataset_rules/rxr_en_us.md` or `reviewer/dataset_rules/rxr_en_us.md`.
- The Adapter Profile is the sole dispatch authority. R2R must not load RxR rules/templates; RxR must not load R2R rules/templates. Both profiles always load their own ten fixed Generator and ten fixed Reviewer Core examples.
- Dataset-specific rules refine application order and risk patterns; they do not replace the shared semantic contract, active Runtime Schemas, evidence requirements, or Host state machine.
- Prompt assembly order is implemented by `host/compile.py`; this file documents the intended ownership boundary and must be updated whenever that assembly contract changes.
