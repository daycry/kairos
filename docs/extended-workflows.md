# Observations, tool summaries and team work

These workflows use the same project permissions, capture consent and durable
PostgreSQL storage as the rest of Kairos. They do not change existing private
work lists or promote captured information to validated knowledge.

## Write observations

`observation_add(event)` creates a new item at version 1. The event is a structured
object containing `event_id` and `item_id` UUIDs, `project_id`, `session_id`,
`agent_id`, timezone-qualified `occurred_at`, `event_type`, `version`, `payload`
and optional `generate`/`capture`. The payload contains a title and content, with
optional category, tags (an ordered string array), provenance, evidence and facts.
Only fields in the published MCP schema are accepted. Events are limited to
256 KiB; field limits are also enforced.

`observation_record_event(event)` records a revision, correction, session event
or withdrawal through the same event contract. To revise an item, retain its
`item_id`, increment its version by exactly one and supply a new event UUID.
To replace another live item, use a correction and `payload.supersedes`. To
withdraw an item, record an event with `event_type: "delete"` and the next version.
An already withdrawn item cannot be revived through another revision.

Generate event and item identities once, before sending. If delivery is uncertain,
retry the exact event with the same identities and content. Reusing an event UUID
with changed content returns a conflict. A successful receipt means durable
acceptance. If generation was requested, poll `event_status(event_id)` and inspect
every job before treating extraction as complete. The model cannot validate its
own generated learning; validation requires permission and evidence.

The REST adapters accept the same Event JSON: `POST /v1/observations` creates an
observation and `POST /v1/observations/events` records subsequent events.

## Structured observations

An event may carry a structured document in `payload.structured`, validated against
a versioned JSON Schema (2020-12) in `docs/contracts/`: `observation.v1`
(`type`, `title`, `facts` with a literal `evidence_quote`, `narrative`, `concepts`,
`files_read`, `files_modified`) or `session-summary.v1` (`request`, `investigated`,
`learned`, `completed`, `next_steps`). The document's own `schema_version` selects the
schema; unknown fields are refused and every text has a length limit. A document that
does not match is a 422 `invalid_observation` whose message names the JSON path of the
first error and never echoes content. An event without `payload.structured` is not
validated and is accepted as before. Limits and local validation are in
`docs/integration.md` and `docs/contracts/README.md`.

## Recover tool summaries

`get_tool_uses(project, session_id?, tool?, limit=20, cursor?)` returns authorized,
current tool-use capture summaries. The default page size is 20, with a maximum
of 100. Each entry identifies its event, item, version, canonical hash, session,
agent, recorded time, hook event and stable evidence reference.

Only the technical fields `tool`, `status`, `exit_code` and `event` can appear in
the summary. Raw arguments, raw output, detail text and transcripts are excluded,
including when the source was captured with full consent. Full-consent captures
that do not contain structured technical metadata have an empty summary. Ordinary
notes are not treated as tool captures. Deleted, superseded and historical item
versions are excluded, even if their immutable audit events still exist.

Use `next_cursor` while `has_more` is true, preserving the project, session and
tool filters. Cursors cannot be reused for another selection. A scan examines at
most 500 current capture records; `scan_limited` indicates that bound. A page can
be empty with another cursor when a narrow tool filter requires further scanning.
The response is also capped at 240,000 UTF-8 bytes; `byte_limited` signals that
bound and the next cursor resumes before the omitted record. `occurred_at` is
source-declared time; `recorded_at` is the server's durable recording time.
Tool history reflects events successfully captured; it cannot reconstruct tool
calls that a client never submitted.

## Shared team work

Private and shared work are intentionally separate:

| Workflow | Visibility |
| --- | --- |
| `work_state_read` / `work_state_write` | Only the authenticated actor's lists |
| `team_work_read` / `team_work_write` | All actors with current project read permission |

`team_work_write(project, list, fields, request_id, expected_version?)` appends an
attributed update. `fields` is an object of scalar values. `task` selects a task,
`status` accepts `todo`, `doing`, `done` or `dropped`, and a null value removes a
field. A name is a literal string, never a path. Team members may store additional
scalar fields such as `owner` or `due`; these are descriptive data rather than
authorization rules.

Read the current version before changing shared work. Supply `expected_version: 0`
for a new list, or the observed version for an update. If another actor has
already changed it, Kairos returns a conflict; reread, review and issue a new
request. Reuse the same `request_id` and exact content for transport retries.
Request identity is scoped to actor and project, while the list and version are
shared across actors. Receipts include `updated_by`; the immutable entry also
retains its actor. The last writer cannot impersonate another actor by setting a
field in the state.

`team_work_read(project, list?, include_closed=false)` reads shared lists.
`team_search(project, query="", limit=20)` performs plain, case-insensitive text
search over list names and open task fields. `team_brief(project, limit=20)` gives
a bounded view of current shared work. These are evidence views, not generated
reports or validated knowledge. Completed and dropped tasks are hidden by default.
Use `include_closed` to inspect them in a selected list.

REST uses `GET /v1/projects/{project_id}/team-work` and `POST` at the same path.
The POST body is `{ "list": "release", "fields": { "task": "Review sources",
"status": "doing" }, "request_id": "stable-request-id", "expected_version": 0 }`.

Writing requires current project read and write permissions and enabled capture.
Reads require project read permission. Revoked keys, disabled users and removed
grants are rechecked; existing authority rows are locked until the transaction
finishes. No private list is copied into shared work automatically.

Shared project quotas are 100 lists, 10,000 update entries and 8 MiB of receipts.
Each entry is at most 16 KiB, each list at most 500 tasks and 128 KiB of state.
Read/search output is capped at 240,000 UTF-8 bytes and reports `truncated`.
If truncated, request a named list or narrow the search. Quotas fail explicitly;
Kairos does not silently discard old work.

## Migration and testing

The additive extended migration creates only shared-work tables and an index;
it does not rewrite observations, remove private lists or change project grants.
Run it through the standard Store migration transaction and advisory lock. A
rollback to an older application can retain these extra tables; dropping them
would destroy shared work and is not a recovery procedure.

From the product directory, the isolated PostgreSQL test target is:

```sh
docker build --no-cache --target test -f memory_platform/Dockerfile -t kairos-memory-tests .
```

For focused tests against an explicitly disposable PostgreSQL database, set
`MEMORY_TEST_DSN` to that test database and run:

```sh
python -m unittest memory_platform.tests.test_extended_tools memory_platform.tests.test_extended_gateway -v
```

Without `MEMORY_TEST_DSN`, integration cases skip. That result is not database
acceptance. Never point the test suite at the product database. Tests cover
cross-actor sharing and races, private separation, exact retries, stale versions,
permission revocation, policy rejection, withdrawal, bounded summaries, UTF-8
budgets and HTTP/MCP receipt parity.
