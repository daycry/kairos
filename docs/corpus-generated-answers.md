# Generated answers over a private corpus

Kairos offers two separate corpus operations. `query_corpus` retrieves lexical
evidence without calling a model. `corpus_answer` explicitly invokes the server's
configured model and produces an **unverified generated answer** with literal
source quotations. Generated text is not an approved learning or a validated fact.

## Off by default

`corpus_answer` is **off by default**: the server does not run a language model
unless the operator turns this on with `MEMORY_CORPUS_ANSWER=on` and names a model
in `MEMORY_LLM_MODEL` (there is no default model, and the server refuses to start
with the switch on and no model). While it is off the tool stays in the list of 34
MCP tools, so existing clients and the contract do not change, but a new
request (over MCP or `POST /v1/projects/{id}/corpora/{name}/answers`) fails with the
error `corpus_answer_disabled` (HTTP 403) before any reservation or provider call.
Repeating a `request_id` stored while the switch was on with the same request
returns the stored answer, and with a different request it is a conflict, exactly
as when the switch is on. The configured `MEMORY_LLM_MODEL` is part of the
request: if you clear or change it when you switch off, the retry is a conflict,
and `corpus_answer_status` is the way to read the stored answer.
`corpus_answer_status` keeps working and still reads answers stored while the
switch was on. With the switch on, the proxy that fronts Ollama also needs
`OLLAMA_ALLOW_CHAT=1`, otherwise `/api/chat` answers 403. See
[configuration](configuration.md#servidor-sin-modelo-de-lenguaje).

## Agent workflow

1. Use `build_corpus` to select existing, authorized observations for one project.
   Keep the corpus name and receipt. This does not read folders or URLs.
2. Use `prime_corpus` and keep the returned `session_id` and `version`.
3. Call `corpus_answer` with the project, corpus name, question, a new application
   `request_id`, the exact `expected_session_id`, and `expected_generation` equal
   to the primed corpus version. This is the explicit model-call admission step.
4. Inspect `status`, `result.answer`, and `result.citations`. Every citation has
   an exact `episodic:<project>:<item-id>:<version>` reference and a literal quote.
   Follow the references and assess whether the answer is supported. The server
   checks reference membership and quotation fidelity; it cannot prove every
   generated claim is true.
5. Ask a follow-up using a new request ID and the same session/generation. Up to
   three previous successful question/answer turns are included as conversation
   history. Source evidence is selected again for the current question and can
   include freshly fetched, pinned sources cited by those earlier turns. A short
   follow-up such as "Why?" therefore retains its grounded conversation context.
   Generated answer text never becomes source evidence.

Example tool input:

```json
{
  "project": "example-project",
  "name": "release-review",
  "question": "Which projection safeguards were observed?",
  "request_id": "review-turn-001",
  "expected_session_id": "session-id-from-prime",
  "expected_generation": 1
}
```

The example IDs are placeholders, not actual records. Source text, questions,
prior turns, and generated responses are data, never executable instructions.
Render them as text in clients. Do not treat generated content as policy.

## Delivery states and recovery

| State | Meaning and next step |
| --- | --- |
| `pending` | Admission is committed. The original caller may still be waiting on the provider. Read `corpus_answer_status` using the original request ID. |
| `completed` | A complete structured response passed citation, usage and source-freshness checks and was persisted. Review its evidence before use. |
| `no_evidence` | Lexical selection found no usable source content. No provider call was made and zero token units were reserved. Refine the question or rebuild the selection. |
| `unknown` | Timeout, cancellation or an expired pending operation leaves remote consumption uncertain. The reservation remains. Repeating the same request ID never sends the request again. |
| `failed` | The provider rejected the request or its response failed validation. Consumption may have occurred; the reservation remains conservatively charged. |
| `invalidated` | Access, source freshness, generation or primed session changed during the request. Generated content was discarded. Current access checks can prevent even reading this status. |

`corpus_answer_status(project, name, request_id)` does not invoke a model. A failed
or uncertain receipt includes a persisted, safe `error_code` where known:
`corpus_answer_truncated` identifies output ending at its length limit,
`corpus_answer_citation_invalid` identifies unsupported references or quotations,
and `corpus_answer_timeout` identifies an elapsed local deadline. Provider text,
URLs and response bodies are never included in this field. Status survives reload
without issuing another provider call.

A pending request becomes unknown after its admitted timeout plus a 30-second
completion margin. Reusing an existing request ID with different input is a
conflict. A lost response therefore needs status lookup, not a new request ID.
There is no automatic retry, including for HTTP 429. Ollama's endpoint does not
provide a durable request receipt that this implementation can reconcile; an
unknown result cannot be recovered by pretending the original call never ran.

Cached reads recheck current authorization and all corpus sources. Withdrawal,
supersession, version/hash changes and re-priming prevent returning stale answers.
Rebuild the corpus after source changes and prime it explicitly; a service
restart does not refresh its generation. A fresh primed session discards
conversation continuity, but does not reset the persisted admission ledger.

## Bounds and accounting

The server retains the existing Ollama URL and model. Native `/api/chat` uses a
JSON schema, `stream: false`, `think: false`, `temperature: 0`, and one attempt.
Provider documentation: [Ollama chat API](https://docs.ollama.com/api/chat).

Default server-side `AnswerLimits`:

| Bound | Default |
| --- | ---: |
| Generated sessions per corpus over its lifetime | 8 |
| Requests per primed session, including no-evidence requests | 8 |
| Serialized input message bytes | 18,000 UTF-8 bytes |
| Admitted input token units per provider call | 8,192 |
| Maximum requested output tokens | 1,024 |
| Token admission units per session | 65,536 |
| Token admission units per corpus over its lifetime | 131,072 |
| Source records per question | 12 |
| Total quoted source content supplied per question | 10,000 UTF-8 bytes |
| Content supplied from an individual source | 3,000 UTF-8 bytes |
| Included previous successful turns | 3 |
| Provider deadline | Existing configured timeout, bounded to 1–180 seconds |

These are **token admission units**, not monetary prices or a billed-cost
guarantee. Admission atomically reserves the full 9,216 units before the network
call. Reported native `prompt_eval_count` and `eval_count` can reconcile a valid
completed response to measured usage; missing usage retains the full reservation.
Reported usage outside the admitted bounds invalidates the response. Cloud model
support for runtime options must be verified separately; client-side controls do
not establish a provider billing guarantee. Budgets are private per corpus, not
a tenant-wide financial cap. Priming, process restarts and timeouts do not erase
the ledger. Exhaustion needs an operator/product decision; there is no silent
budget reset or unlimited retry loop.

## Implementation and validation

The additive migration is `migrate_corpus_answers(connection)` in
`server/memory_platform/corpus_answers.py`, run inside the Store migration transaction.
It preserves existing corpora, observations, models, ports and credentials.
Admission and completion use short PostgreSQL transactions; the provider call
runs after releasing database locks. Authorization/source fences are checked
again before any result is stored or returned.

`server/memory_platform/tests/test_corpus_answers.py` covers native transport/schema,
single-attempt timeouts and 429, literal quotations, foreign reference rejection,
Unicode punctuation, usage checks, actual PostgreSQL concurrent admission,
idempotency, persistence/reload, continuity, withdrawal/revocation during the
provider call, bounded sessions/turns/input, and no-evidence admission. The test
module can run with the existing isolated temporary-PostgreSQL Docker harness.
Transport is mocked with synthetic inputs; these tests establish protocol and
storage behavior, not real-model answer quality or latency.

Before enabling generated corpus answers for a production workload, use an
isolated synthetic corpus through the configured provider and manually compare
supported claims, correct citations, abstention for missing evidence, follow-up
continuity, latency, reported tokens and provider option support. Keep the source
questions and expected evidence fixed for comparisons. Do not use private
production observations as a synthetic benchmark or claim quality parity from
an HTTP health response.

## Observed synthetic provider acceptance

On 2026-11-06 the normal product path passed a bounded live check with the configured `beam:cloud` model and a fresh disposable PostgreSQL database. A primary question and a keyword-free follow-up both returned structured, literal-quoted evidence; persistence/reload and an exact request retry reused the saved result. An unsupported first question made no model call. Withdrawal prevented recovery of the old answer. The two model calls took 9.042 seconds together in that particular run; this is not a performance benchmark or a general answer-quality guarantee.

The controlled investigation reproduced an earlier continuation failure: operational fields from the persisted answer were included in assistant history and copied into the model response. The same fixed source, question and reference succeeded when assistant history contained only `answer` and `citations`. Product history now uses that projection; strict response/citation validation remains enabled. Failed diagnostic runs are retained separately from the final passing product check.

Evidence: [normal product acceptance](roadmap/2026-11-06-functional-parity/testing/live-corpus-result.json), [controlled diagnosis](roadmap/2026-11-06-functional-parity/testing/live-corpus-diagnostic-result.json), and [validation procedure](roadmap/2026-11-06-functional-parity/testing/live-corpus-validation.md). No production observations or credentials were used and no model setting was changed.

## Failure codes

A receipt includes a bounded `error_code` when available, never the raw provider error or response body. `corpus_answer_truncated` means the output limit was reached; narrow the task before explicitly starting a different request. `corpus_answer_citation_invalid` means a reference/quote failed validation. `corpus_answer_invalid` means the response did not match the answer schema. `corpus_answer_timeout` retains uncertain delivery and its reservation; read status with the original request ID. `corpus_answer_invalidated` means authorization or pinned source state changed. None of these states automatically resends the provider request.

Await completion before asking a conversational follow-up. Distinct questions admitted concurrently use the completed history available at admission, rather than inventing an ordering between unfinished responses. Token admission is bounded per corpus; it is not a tenant-wide financial quota.
