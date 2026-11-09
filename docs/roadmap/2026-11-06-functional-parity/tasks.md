# Functional workflows

This implementation ledger extends A-02/A-03/A-04/A-05/A-06/A-08 in the [native product ledger](../2026-11-04-native-product/tasks.md). Native client acceptance already recorded there remains scoped to its original runtime versions. Preparation, isolated acceptance, server activation and registry publication are separate outcomes.

## Requirements and implementation

- [x] F-01 — Local code search, outline and symbol expansion, enabled explicitly for the selected client root. Exclusions apply before file reads; reject links/traversal and enforce file, aggregate and time limits. No source execution, automatic upload or whole-repository ingestion. Stable installed runtime includes its parser assets and licenses.
- [x] F-02 — Named observation writes and tool-use retrieval reuse existing authorization, event identity, hashes, versioning and durable receipts. Recovery returns current permitted technical summaries; withdrawn records and raw tool inputs/outputs are excluded.
- [x] F-03 — Explicit project team work, separate from existing actor-private lists. Shared writers use compare-and-swap and exact request retries; reads/search/brief retain attribution and current project authorization.
- [x] F-04 — Generated corpus answers with follow-up continuity, source-generation fencing, atomic token-budget admission, request reconciliation and checked citations. No provider call inside a database transaction. Timeouts remain uncertain and do not cause blind generation retries. Lexical retrieval remains available.
- [x] F-05 — Persisted observations, rules, work and activity views. Team/private visibility is explicit. Category/session filters apply server-side before pagination. Preserve project accordion/indentation, render all values as text, bound multi-project loading and show partial failures.
- [ ] F-06 — Versioned package, parameterized artifact verification, offline clean-cache installation and registry publication proof. A local tarball is not publication. Do not change existing working client configurations while testing.
- [x] F-07 — Update operational manuals, MCP/HTTP contracts and integration guidance. Record complete test results, activation state and outstanding external dependencies.

## Verification contract

Use synthetic isolated PostgreSQL, HTTP and browser fixtures. Never run destructive tests against the deployed memory database. Backend coverage includes cross-actor/project access, revoked credentials, exact retries, stale versions, withdrawal and provider failures. Client coverage includes excluded paths before reads, links, malformed UTF-8/binary data, bounded output and runtime installation. UI coverage includes keyboard navigation, remote loading/empty/error/retry/success, task mutation, list pagination, session filtering and text-only rendering. Generated answers require mock failure tests plus an explicitly scoped real provider evaluation before claiming generation quality.

## Current evidence

2026-11-06: Requirements established from shipped-artifact inspection and current implementation inventories. Docker API access from this session currently returns permission denied; this is a test-execution limitation, not a passing gate. No production data, policies, models, ports or credentials have been modified for this initiative.

2026-11-06: F-01 accepted in 88 Windows client tests and the complete isolated Linux release gate, including fresh-cache offline npx installation. Exact artifact and source hashes: [package evidence](testing/package-0.2.0.json). F-02/F-03 passed the 172-test frozen PostgreSQL gate with no failures or skips; its source manifest records the scope. Later corpus diagnostics and UI changes require their own final acceptance.

2026-11-06 final functional checks: complete backend suite 177/177, no skips, frozen source manifest matches current product files; web 65/65 plus TypeScript/Vite production build; maintained Chromium UI 20/20. Normal product-path live provider acceptance passed primary/follow-up, exact retries, persistence/reload and withdrawal with two synthetic calls. Earlier diagnostic failures are retained with their confirmed root cause. Current deployment attempt stopped at Docker engine access before build, backup, migration or service changes: [activation](testing/activation.json). F-06 remains open because the exact npm version returns 404 and authenticated publication/scope ownership could not be verified in this cache-limited session.

Documentation accepted: 12 current HTML manuals across two viewports (24 checks), no external requests or browser errors. All backend source bytes, web source bytes and the prepared CLI archive match their passing receipts. [Final verification](testing/verification.json) separates implementation, activation and npm publication.
