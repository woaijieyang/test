# Dataset-specific rules

- `rxr_en_us.md` is loaded only for Adapter profile `rxr-en-us`.
- No dataset-specific rules are loaded for `r2r-en`; it remains on the v5 common prompts and templates.
- The shared RxR file is the semantic authority for RxR-specific distinctions. Generator and Reviewer guidance specify role-specific application order but must not redefine those distinctions.
- All dataset-specific rules are prompt guidance only. The v5 common semantic contract and active runtime schemas remain authoritative for output and validation.
