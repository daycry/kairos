# Native corpus generation: observed failure and controlled diagnosis

All experiments used a freshly initialized, disposable PostgreSQL 17.11 database
inside the existing test image. They did not access product memory, credentials
or configuration. The only provider was the existing `beam:cloud` model through
`http://host.docker.internal:11434/api/chat`. Each experiment allowed at most two
native POST requests, no automatic retry, and a 90-second deadline per call.

The synthetic source states that deployment requires two approvals and explicitly
explains that this prevents accidental releases when one reviewer misses a defect.
The follow-up question `Why?` is therefore answerable from the supplied evidence.

## Initial observations

The initial end-to-end probe used a stricter 512-output-token limit. It verified
that an unsupported question caused no provider call, that a real first answer
recovered the two-approval requirement with literal citations, and that repeating
the same request after reload reused the persisted result without another call.
Its real follow-up was rejected. The native rejection details were not captured;
this attempt alone does not establish its cause.

The second experiment used the production default of 1,024 output tokens. The
first answer and exact retry/reload passed again. The follow-up failed despite
HTTP 200, `done=true`, `done_reason=stop`, 440 input tokens and 251 output tokens.
The provider reported `corpus_answer_invalid`. This observed failure was neither
an output-length termination nor exhaustion of the 1,024-token limit.

Preserved evidence:

- [Attempt 1](live-corpus-result-attempt1.json), [source manifest](live-corpus-source-attempt1.json).
- [Attempt 2](live-corpus-result-attempt2.json), [source manifest](live-corpus-source-attempt2.json).

These attempts remain failed results. Their first-answer checks do not establish
that their entire end-to-end workflow passed.

## Controlled history-shape experiment

The diagnostic created two private synthetic corpora over the same source and
generation. A deterministic local provider seeded the same valid first answer
without making any network request. Each corpus then made one real `Why?` call.
The model, source reference, question, JSON response schema and generation hash
were identical. Only the shape of the prior assistant message changed.

| Prior assistant message | Observed native response shape | Result |
| --- | --- | --- |
| Stored envelope: `answer`, `citations`, `input_tokens`, `mode`, `output_tokens`, `prompt_version` | The same six top-level keys; one citation; HTTP 200, stop, 227 output tokens | Rejected by the strict answer schema |
| Projected answer: `answer`, `citations` | Exactly `answer` and `citations`; one citation; HTTP 200, stop, 177 output tokens | Completed, persisted and reloaded successfully |

The projected positive control also passed literal-quote and explicit-rationale
checks. This demonstrates the failure mechanism: storage metadata included in
assistant history was echoed into the model's response and violated the answer
contract. Returning only the answer/citation projection avoids that contamination
in this matched experiment. The validator must continue rejecting extra fields.

Diagnostics recorded JSON keys, types, counts and byte lengths, together with
native completion metadata. They did not record raw prompts or response values.
The experiment used exactly two model calls and completed in 4.854 seconds.

- [Diagnostic result](live-corpus-diagnostic-result.json).
- [Exact source manifest](live-corpus-diagnostic-source.json).
- [Reproducible diagnostic driver](live-corpus-diagnostic.py).

The diagnostic ran against frozen pre-fix source. Its projected control changes
the message projection in the test adapter; it is evidence for the correction.
A single synthetic fixture is not a general benchmark of model answer quality.

## Acceptance through the actual corrected product path

After the product history projection was corrected, a final explicitly authorized
experiment exercised ordinary `CorpusAnswers` and `NativeCorpusProvider`, without
a message-projection test adapter. Its two real model calls completed successfully
with the production-default 1,024-output-token cap:

| Check | Result |
| --- | --- |
| Unsupported initial question without evidence | `no_evidence`; no model call |
| Primary answer | Completed; 287 input / 208 output tokens; literal references and the two-approval fact verified |
| Same request after service reload | Exact persisted result; no additional call |
| Follow-up `Why?` | Completed; 411 input / 147 output tokens; prior-turn context, literal citations and stated rationale verified |
| Source withdrawal | Cached answer and status reads rejected; no additional call |

Both native responses reported HTTP 200, `done=true` and `done_reason=stop`.
The experiment passed against isolated PostgreSQL 17.11 in 9.042 seconds with
exactly two provider calls and no retries. The source manifest hash is
`a18591d97bd1161494865e56c9e73b7dd859d2807a2dbbb3f14376857facedef`.

- [Final native acceptance receipt](live-corpus-result.json).
- [Final native source manifest](live-corpus-source.json).
- [Normal product-path driver](live-corpus-gate.py).

The four explicitly bounded experiments used eight model calls in total. No
further real calls were made. This is local synthetic integration evidence; it
does not imply that a deployed product service has already been updated. The
complete backend regression result is tracked separately in the frozen
PostgreSQL gate receipts.

## Reproduction boundaries

The native drivers must run in the isolated test image with `/candidate` mounted
read-only and a dedicated evidence directory at `/test-output`. Use the default
bridge network solely for the fixed provider endpoint and the harness's own
loopback database. Ordinary backend tests should use `--network none`.

Running a native driver spends its declared two-call budget. Do not automatically
rerun a failed experiment. Inspect its machine-readable receipt and confirm the
scope of any further diagnostic first. Never point these test drivers at the
product database or replace their synthetic fixture with private observations.
