# Format contract｜source bytes, stage text and tokenization

## Source representation

The adapter reads the JSON instruction value once as UTF-8 and retains the exact decoded string. It does not trim, normalize Unicode, casefold, replace curly quotes, decode literal `\\n`, or split/join lines. The source envelope is `prefix + body + suffix`; all three are preserved as exact source slices.

## Renderer modes

- SOURCE_EXACT: exact original string; used both for deliberate unchanged and fallback, with host `disposition` distinguishing them.
- BOUNDARY_ONLY: ordered source slices are copied; only whitespace at approved stage cuts is replaced with LF. A zero-width source delimiter after punctuation may be a legal cut; never split a word or contraction.
- ASSEMBLED_SINGLE: one edited stage; keep the approved assembly rather than silently restoring the source.
- ASSEMBLED_MULTI: multiple approved stages joined by LF, with prefix/suffix retained.

COPY/MOVE source spans preserve internal whitespace. EDIT and EDIT_SEAM are explicitly logged. New word seams use one ASCII U+0020. New double spaces, TABs, line breaks or literal backslash-n are not introduced as if they were copied source. Ambiguous repeated lexical spans are not guessed. `unused_source` means a source span was not mapped literally; it is not proof that a semantic requirement was omitted.

## Descriptive census (only the uploaded evaluation files)

| Feature | R2R 1,839 | RxR en-US 1,223 |
|---|---:|---:|
| No leading whitespace | 1,839 | 1,220 |
| Non-empty leading whitespace | 0 | 3 (one ASCII space each) |
| No trailing whitespace | 0 | 890 |
| Exactly one trailing ASCII space | 1,839 | 260 |
| Suffix consists only of ASCII spaces | 1,839 | 324 |
| Repeated ASCII spaces inside body | 268 | 180 |
| Repeated ASCII spaces anywhere | 268 | 201 |
| Native LF anywhere | 0 | 12 |
| Native LF inside body | 0 | 3 |
| Native LF in suffix | 0 | 9 |
| Native CRLF records | 9 | 0 |
| Non-ASCII records | 0 | 6 |

These are observations about the uploaded evaluation JSON, not universal rules for every train/eval version. In particular, do not hard-code a trailing space for R2R or trim RxR. The renderer preserves the actual source envelope regardless of dataset.

## Actor/tokenization binding

After the existing AwareVLN code assembles its full request, record the exact instruction seen by the Actor, complete prompt bytes, actual token IDs, tokenizer ID, chat-template ID, image IDs and order, truncation state and request ID. Tokenize the complete final prompt once. Do not tokenize each stage separately and concatenate token IDs.

`host.run.receipt_for_navigation()` binds the instruction observed by the Actor to the released `instruction_sha256`. It requires the actual non-empty full-prompt bytes and integer `input_ids`, tokenizer/template identifiers, ordered image IDs, a boolean truncation flag and request ID; it returns the full-prompt hash and token-ID hash together with Source/Snapshot/Instruction identities. The helper validates the values supplied by the integration caller. It cannot independently inspect the Actor or prove that the caller passed the true native request, tokenizer output or image extraction. Capture these values at the existing Actor request boundary; never reconstruct them from stage strings.
