---
content_origin: agent
proposed_by: architect
tipo: adr
category: DECISION
title: Access control is built on three seams and limiter state stays in the API process
fecha: 2026-11-20
iniciativa: 2026-11-19-access-control
evidencia: Design gate of Initiative 4 (access-control). The architect presented three options in docs/roadmap/2026-11-19-access-control/design.md and recommended O2. The orchestrator of /dev-cycle relayed the user's choice on 2026-11-20, literal «2: un sitio para cada cosa (Recommended)». The facts behind the options were read on commit 45fd4fb and are cited with file and line in the design.
fuentes:
  - docs/roadmap/2026-11-19-access-control/design.md
  - docs/roadmap/2026-11-19-access-control/spec.md
  - docs/roadmap/2026-11-19-access-control/evaluation.md
  - server/memory_platform/store_auth.py
  - server/memory_platform/tests/test_auth_cache.py
  - web/src/memory-portal.ts
tags:
  - initiative:access-control
  - component:memory-api
  - component:portal
  - topic:authorization
  - topic:rate-limiting
---
# Access control is built on three seams and limiter state stays in the API process

## Context

Initiative 4 adds password change, disabling users, grant replacement, session and key lifecycle, per-key limits and a full access section in the portal. Three things were open and each crosses components: where the new writers of `actors`, `project_grants`, `api_keys` and `web_sessions` live, who decides which controls the portal shows, and where the limiter state (rate bucket, stream slots, login slots, daily write quota) lives. The spec assumes one replica of `memory-api` on the VPS and limits schema version 13 to new columns and indexes (CA-10). The retros of Initiatives 2 and 3 put their deviations on review loops over large diffs.

## Decision

Option O2 of the design, «Costuras de acceso», is adopted:

1. Every new writer of the permission tables lives in one new store mixin, `server/memory_platform/store_access.py`, and ends in one function, `_access_changed`, that writes the audit event and empties the per-transaction permission cache. The `admin` commands call these same methods. The resolver functions stay in `store_auth.py`.
2. The server computes `capabilities` in the resolver and publishes them in `/v1/auth/me`. The portal shows controls only from `capabilities`; the server still rejects the action itself.
3. The new portal sections are separate modules, `web/src/access-panel.ts` and `web/src/account-panel.ts`, mounted by `memory-portal.ts`.
4. The rate bucket, the stream slots and the login slots live in the memory of the `memory-api` process, behind one module, `server/memory_platform/limits.py` (and `passwords.py` for scrypt). The daily write quota is persisted in columns of `memory.api_keys`, written in batches.

## Discarded alternatives

- **O1, extend in place** — new writers in `store_auth.py`, portal sections inside `memory-portal.ts` (702 lines, 75 kB), and the portal deriving what to show from `is_admin` and scopes. Cheapest, and it is the baseline the evaluation priced. Discarded because the diffs land in the two files where review is hardest, and because adding roles or groups later would change the portal as well as the resolver.
- **O3, limiter state in PostgreSQL** — the seams of O2 plus rate windows, stream leases and login slots in tables. It is the only option that does not depend on a single replica. Discarded because it adds a write to every authenticated request on a pool sized without it, needs three new tables that CA-10 does not allow as written, cannot be reverted under additive-only migrations, and pays today for a second replica nobody has decided.
- **Rate limiting in nginx** — no per-key override and no computed `Retry-After`; `web/nginx.conf` is mounted by the deployed installation.
- **Limiting before authentication, keyed by token hash** — any invented token creates limiter state.
- **A credential or internal header for kairos-mcp** — kairos-mcp stores no credentials and a header can be spoofed; the exemption is given to the route `/v1/auth/me` instead.
- **Moving the resolver to a new package, or checking permissions at the route layer** — changes the most sensitive code and the names `test_auth_cache.py` walks, or breaks the check-wait-check rule that holds inside the transaction.

## Consequences

`capabilities` becomes part of the public surface of `/v1/auth/me` and has to be kept; a test must tie every capability to its route so that the two cannot drift. The cost is above the evaluation baseline in characteristics C-05 and C-08 only. Rate, stream and login limits are exact only while `memory-api` runs as one replica: if Initiative 5 decides several, `limits.py` is the single module that moves its state to the database, and the quota is already there. Roles, groups or single sign-on would change the resolver and `capabilities`, with new tables only.

## Participants

- User: chose O2 (2026-11-20, relayed by the `/dev-cycle` orchestrator).
- architect: presented O1, O2 and O3 and recommended O2.
