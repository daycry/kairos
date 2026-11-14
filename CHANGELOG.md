# Changelog

All notable changes to Kairos are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Each section comes from a closed ledger in `docs/roadmap/`, which holds the full detail and evidence. The Spanish version is [CHANGELOG.es.md](CHANGELOG.es.md).

Kairos has no tagged releases yet. Everything below is unreleased. The three components (server, kairos-mcp and the `@daycry/kairos` CLI) are at 0.4.0 and nothing has been published: the CLI is not on npm and no image is in a registry.

## [Unreleased]

### Changed — `three-components` initiative (2026-11-12 to 2026-11-14)

Kairos is split into three components: the server, kairos-mcp and the CLI, plus the web portal. The server no longer needs a language model. [Ledger](docs/roadmap/2026-11-12-three-components/tasks.md) · [final review](docs/roadmap/2026-11-12-three-components/review.md)

- **Three components in one repository.** The server lives in `server/` (the Python package is still `memory_platform`, built with `server/memory_platform/Dockerfile`), kairos-mcp in `mcp/`, the CLI in `client/` (was `packages/kairos-cli/`) and the portal image in `web/` (`web/Dockerfile`, `web/nginx.conf`). Compose keeps the same services, names, volumes and networks; only the build paths changed. `npm pack` of the CLI lists the same files. Server, kairos-mcp and CLI are all 0.4.0.
- **No extraction in the server by default.** `MEMORY_EXTRACT_ENABLED` is `0`: an event with `generate: true` (the CLI sends it with summaries) is accepted with 202 and creates no `extract` job. The receipt gains an additive `extraction: "disabled"` field. Jobs already queued are kept and marked `extraction_disabled`; `POST /v1/jobs/{id}/retry` queues them again once extraction is on.
- **`corpus_answer` is off by default.** `MEMORY_CORPUS_ANSWER=off` keeps the tool in the list of 34 and rejects a new request with `corpus_answer_disabled` without calling any provider (repeating a saved `request_id` returns the saved answer while `MEMORY_LLM_MODEL` is unchanged, or a conflict if the request or the model differs); `corpus_answer_status` still reads saved answers.
- **No default model.** `MEMORY_LLM_MODEL` has no value any more; turning on extraction or generated answers without it stops the startup with a message that names the variable. An installation that relied on the previous default must set it.
- **A closed Ollama proxy.** The internal proxy only forwards `/api/embed` and `/api/version`; everything else gets 403 from the proxy. `OLLAMA_ALLOW_CHAT=1` also allows `/api/chat`. The proxy no longer runs as root.
- **`/mcp` now goes to kairos-mcp.** The web proxy (`127.0.0.1:5173/mcp/`, the address `kairos mcp` uses) serves kairos-mcp instead of the server's own MCP, and `memory-web` joins the internal `mcp` network and waits for `memory-mcp`. The CLI bridge needs no change; the differences a client sees (Bearer credential only, `structuredContent` in 12 tools, a 401 without `X-Request-ID`) are in [integration](docs/integration.md#conectar-con-kairos-mcp).
- **The internal MCP is deprecated and goes in 0.5.0.** It stays at `memory-api:8790/mcp/` through 0.4.x with `Deprecation: true` and `Sunset: 0.5.0` on every response and one `mcp_legacy_used` log event per call (method, status and request id, nothing else). `MEMORY_MOUNT_MCP=0` unmounts it and `/mcp` answers 404; the default is `1`. Migration notes: [integration](docs/integration.md#migración-el-mcp-interno-queda-en-desuso-y-se-retira-en-la-050) and [operations](docs/operations.md#retirada-del-mcp-interno).
- **kairos-mcp, a container of its own.** The 34 MCP tools are served by `memory-mcp` (`mcp/`), which has no database access: it calls `/v1` with the caller's Bearer, wraps read results as untrusted data and publishes the same tools and contract as before (`docs/contracts/kairos-mcp.json` only gains `x-kairos-*` keys and `structured`).
- **A REST `/v1` endpoint for every MCP tool.** Each tool has a `/v1` counterpart with the same permissions, so any HTTP client can do what the MCP tools do.
- **Versioned observation and session-summary schemas.** `docs/contracts/observation.v1.schema.json` and `session-summary.v1.schema.json`, with valid and invalid examples checked by the tests.
- **Continuous integration.** Six GitHub Actions jobs (server, retrieval-eval, mcp, client, web, contracts) run on every push and pull request, read-only and with actions pinned by SHA.
- **Deployment check of `/mcp`.** `scripts/deploy-memory.py` checks `/mcp` with a temporary read key that it revokes at the end (the portal session no longer reaches kairos-mcp), says on the console when `/mcp` was not checked, and can run an isolated rehearsal with a simulated embedding provider (`--embed-stub`, `--roundtrip`). After updating, recreate the `ollama` service too: its template now uses `OLLAMA_ALLOW_CHAT`.

### Changed — `retrieval-quality` initiative (2026-11-09)

Search is now measurable and finds more of what you stored. [Ledger](docs/roadmap/2026-11-09-retrieval-quality/tasks.md) · [final review](docs/roadmap/2026-11-09-retrieval-quality/review.md)

**Search quality**

- **Retrieval evaluation.** A frozen synthetic dataset of 72 questions (Spanish, English, typos, long documents) and a `retrieval-eval` gate measure recall@k and MRR per layer and subset, offline. Combined search went from recall@5 0.50 and MRR 0.34 to 1.00 and 0.97. With the real `nomic-embed-text` model it reaches 1.00 and 0.99.
- **pgvector and HNSW.** Semantic search runs in PostgreSQL with pgvector instead of cosine similarity in Python. An HNSW index covers the indexed model, and exact SQL cosine covers the rest, with the same permissions and time limits. The PostgreSQL image is now a derived image with a pinned pgvector version.
- **Language-aware full-text search.** Notes, documents, facts, agent corpora and portal filters ignore accents and match word forms in Spanish and English (`canción`/`canciones`, `failed`/`fails`). When few results come back, `pg_trgm` adds near matches for typos and identifiers such as `ERR-4471`, marked as approximate.
- **Chunking for long texts.** Documents and notes are split into chunks of about 1,500 characters with 200 of overlap. Search now finds content past the old 8,000-character cut, and results carry an optional `matched_chunk` with the passage that matched. `admin backfill-chunks` prepares existing content and runs during deployment.
- **Hybrid search by default, with degradation.** If only the semantic layer fails, search and context still return the lexical results and say so in an optional `degraded` field (`timeout`, `provider_error`, `store_error`, `no_vectors`, `embeddings_disabled`). An optional `semantic_budget_ms` caps the time spent on the semantic layer.
- **Tunable fusion.** "Validated" is now a tunable bonus in the combined ranking (`MEMORY_FUSION_VALIDATED_BONUS`), no longer an absolute order. `MEMORY_FUSION_K` and `MEMORY_FUSION_WEIGHTS` are configurable too.

**Operations**

- **Structured logs.** The API and the worker write one-line JSON logs with level, event, duration and request id. Secrets are redacted, every previously silent failure leaves a trace with its exception type, and third-party libraries never log below INFO.
- **Prometheus metrics.** `GET /metrics` exposes search-layer latency, provider errors by code, job queue depth, failed jobs by code and embedding-slot saturation, all with closed label values. It answers only on the internal network, or with admin credentials, or not at all (`MEMORY_METRICS`), and nginx and Caddy never publish it.
- **Additive migrations up to schema v11.** These add the `vector` extension, `unaccent`, `pg_trgm`, per-language columns, the `memory.embedding_chunks` table and a partial index on failed jobs. A test now fails if any migration drops or rewrites existing data.
- **Deployment rehearsal.** `scripts/deploy-memory.py` can run an isolated rehearsal project. The full activation (migration, vector and chunk backfill, verification) was rehearsed end to end with identical content and an empty queue at the end. The real deployment moves to Initiative 5 of the [master plan](docs/roadmap/2026-11-10-platform-audit/plan.md).
- **Manuals.** The architecture, configuration, operations, integration and user manuals cover all of the above, and every new variable is listed and passed through Compose.

**Clients and contract**

- **MCP contract.** Additive changes only: the optional `matched_chunk`, `degraded` and `semantic_budget_ms`. All 34 tools keep their contract.
- **CLI 0.3.0 (unpublished).** Automatic context also uses semantic search, within a 1.1 s budget, and accepts the server's `degraded` notice.

**Known limits**

- With the real embedding model, one of 12 long-document questions ranks second instead of first (`ca18:long`). This is accepted as debt; the fusion will be tuned against the real model in Initiative 5.

### Added — earlier initiatives (2026-11-04 to 2026-11-06)

These ledgers predate the current format and `changelog-sync` cannot read them, so this summary follows their checklists.

- **Native product (`native-product`, 2026-11-04).** Kairos becomes a standalone repository with a native API and worker on PostgreSQL. It adds private work state per actor and project, 23 MCP tools, a "My work" view, a dependency-free Node installer, a deployment flow with backup and MCP verification, its own manuals and exported contracts. The MCP tools were accepted in real Claude Code, Codex and OpenCode clients. [Ledger](docs/roadmap/2026-11-04-native-product/tasks.md)
- **Automatic memory per client (`automatic-memory`, 2026-11-05).** Native client events are captured automatically, with privacy applied before anything is stored. A recoverable outbox, a local dispatcher over authenticated loopback IPC (hooks never call the remote server) and bounded, authorized context injection complete the flow. The installer merges hooks without removing other configuration. Accepted in Claude, Codex and OpenCode. [Ledger](docs/roadmap/2026-11-05-automatic-memory/tasks.md)
- **Functional workflows (`functional-parity`, 2026-11-06).** This adds local code search, outline and symbol expansion with explicit exclusions and limits. It also adds named observation writes and tool-use retrieval, and shared team work separate from private lists. Generated corpus answers come with token budgets and checked citations, and there are observation, rule, work and activity views. Registry publication of the package is still pending. [Ledger](docs/roadmap/2026-11-06-functional-parity/tasks.md)
