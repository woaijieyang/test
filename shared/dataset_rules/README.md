# Dataset-specific rules

- `r2r_en.md` is loaded only for Adapter profile `r2r-en`, after the shared semantic contract and before the R2R fixed Core and Dynamic examples.
- `rxr_en_us.md` is loaded only for Adapter profile `rxr-en-us`. The RxR shared semantic rules are followed by the matching role-specific guidance in `generator/dataset_rules/rxr_en_us.md` or `reviewer/dataset_rules/rxr_en_us.md`.
- The Adapter Profile is the sole dispatch authority. R2R must not load RxR rules/templates; RxR must not load R2R rules/templates. Both profiles always load their own ten fixed Generator and ten fixed Reviewer Core examples.
- Dataset-specific rules refine application order and risk patterns; they do not replace the shared semantic contract, active Runtime Schemas, evidence requirements, or Host state machine.
- Prompt assembly order is implemented by `host/compile.py`; this file documents the intended ownership boundary and must be updated whenever that assembly contract changes.

- `generator/dataset_rules/r2r_en.md` and `reviewer/dataset_rules/r2r_en.md` provide role-specific R2R guidance. They are loaded only under `r2r-en`, after the shared R2R rules; neither file is a generic prompt or shared semantic rule.
- `shared/dataset_rules/r2r_fragments.json` is consumed only by the R2R Host selector to rank R2R teaching examples. It is not injected into RxR prompts and does not determine KEEP/SPLIT decisions.
- R2R adaptive retrieval uses 6–8 Generator examples, the same number of paired Reviewer examples, and 2–4 Reviewer diagnostics. The ten fixed Core cases remain unconditional. RxR keeps its existing 2–4 / 2–4 / 0–2 policy.
- R2R retrieval distinguishes completed room/region transitions and corridor endpoints from descriptive room or doorway mentions; fragment matches rank teaching cases only and never prescribe a segmentation decision.
