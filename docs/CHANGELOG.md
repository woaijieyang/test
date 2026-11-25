# Change Record

## Current system

- One shared semantic contract governs Generator and Reviewer.
- Adapter Profile selects isolated R2R English or RxR en-US rules and teaching assets.
- Each dataset has ten fixed Generator Core and ten independent Reviewer Core examples.
- Dynamic retrieval supplements Core and uses explicit dataset/role directory allowlists.
- Runtime uses the active Draft 2020-12 wire schemas and the bounded G0–R0–G1–R1 workflow.
- Renderer freezes the exact reviewed text; Host releases only the matching reviewed snapshot or exact original-source fallback.
- Source identity, prompt components, rule files, schemas, template bundles, request receipts and output snapshots are traceable by hashes.
- Offline engineering tests do not claim real-model semantic accuracy or navigation improvement.

## Maintainer rule

The root README is the only human-readable entry point that carries the current system release label. Machine-readable template manifests may retain their required `version` metadata fields. Other current documents describe behavior without repeating release numbers. Historical comparisons remain explicitly marked as archives and must not be treated as current runtime specifications. Protocol/schema identifiers remain where they are required by actual filenames and machine-readable contracts.
