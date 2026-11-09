# Native runtime 0.1.4: OpenCode contract corrections

## Current acceptance

The operator refreshed Codex and OpenCode to 0.1.3 and ran both bounded tests on 2026-11-06. Readback of those exact executions confirms successful `projects` and `context` MCP calls in both clients. Neither client echoed its temporary automatic-context marker; neither latest read session has the required persisted lifecycle events. Both canaries were retired with matching receipts. Claude retains its previously verified read, injected context and four persisted lifecycle events; its cancelled Stop diagnostic remains open.

`native-client-acceptance.json` is the current readback. Exit code zero is not acceptance of automatic context or writing. C-08 remains open.

## Proven defects and limits

1. OpenCode's named `context` hook receives `SessionContextHook`, which has no `kind` field. The adapter returned early unless `kind === "primary"`, so a valid native context event was ignored. The correction accepts that native shape, retains compatibility with explicit `primary`, and still ignores explicit auxiliary kinds. The regression failed before the patch with missing injected text and passed after it.
2. A V2 `session.created` event identifies its session at `data.sessionID`. The adapter looked only at `data.info.id`. The regression reproduced a missing SessionStart before the patch. The corrected adapter consumes the native field, preserves the older shape, and resolves the individual session directory before admission. Foreign session roots remain excluded.
3. The OpenCode retrieval request omitted the user's current query. It now forwards only bounded text from the latest user message already held in memory. Attachments, assistant messages and tool results are excluded. The existing dispatcher sanitizes that query, limits its keywords, checks project authorization and performs non-semantic retrieval. Summary capture still excludes raw prompts.
4. Codex reports `clamping SessionEnd hook timeout to 3s` as an `error` item even when the run completes. The collector now classifies this exact advisory separately; other errors remain failures. A red/green regression covers both cases. New runtime handlers request three seconds for SessionEnd, matching the native limit. This does not prove the remaining Codex hook problem resolved.

Read-only inspection inside the actual OpenCode 2.0.12 plugin host confirmed that the installation validates, session scope resolves and direct memory retrieval returns 3,682 characters. The internal plugin SDK returned session info directly; the HTTP API uses a `data` envelope. The adapter supports both. Consequently, the previous 0.1.3 envelope regression established compatibility but did not establish the cause inside this native host. No further fix is based on that discarded assumption.

The temporary host diagnostic exposed metadata only, made no capture or model calls, and wrote no private state. Its source was removed. OneDrive left its empty directory read-only; this session's cleanup was denied and a forced cleanup was rejected by automatic approval policy. Operator-side `--refresh-runtime opencode` now removes only that exact empty diagnostic directory, without recursion, before updating the fixture. Unexpected files or linked paths cause an explicit stop.

The cause of missing Codex automation remains unconfirmed. Hook approval must be checked in the native `/hooks` UI. Updating a definition changes its trust hash; the helper never bypasses native trust. Missing output is not evidence that a hook is disabled.

## Validation and distribution

- 59/59 Python script tests, including advisory classification and safe diagnostic cleanup.
- 70/70 client tests on Windows, no skipped or cancelled tests. The runner used `--experimental-test-isolation=none` because child-process isolation is unavailable in this session.
- Upgrade and partial-switch recovery covered from 0.1.0, 0.1.2 and 0.1.3; prior runtime files and pending identities are preserved.
- Local npm package 0.1.4: 18 files, each compared byte for byte with source. Older tarballs remain unchanged. See `package-0.1.4.json` for SHA-256 and size.
- Actual offline npm execution installed all three clients with a synthetic key and enabled local adapters. Local doctor returned `configured`; this synthetic test made no network/provider requests and is not native acceptance.
- No server image, database, model, port, credential or working-project configuration changed in this correction. The package is not published to npm.

## Apply only the affected OpenCode fixture first

Run from the stack root in the operator's PowerShell terminal, with the OpenCode test session closed:

```powershell
python kairos/scripts/accept-native-clients.py --refresh-runtime opencode
```

Expect `runtime_version: 0.1.4`, `keys_created: false`, `server_policy_changed: false`. This reuses the existing scoped key and capture mode; do not repeat `--enable-capture` or `--prepare`. It also retires the empty temporary diagnostic directory. If a previous dispatcher is still alive, the installer stops before switching it; do not kill unrelated processes or remove state. Wait for the owned worker's idle shutdown and retry the refresh.

Then run the two independent acceptance criteria, retaining the selected free model:

```powershell
python kairos/scripts/accept-native-clients.py --run-context opencode --model opencode/big-pickle
python kairos/scripts/accept-native-clients.py --run opencode --model opencode/big-pickle
python kairos/scripts/accept-native-clients.py --collect
```

The context test must echo the unpredictable marker without tools and confirm retirement. Capture must be recovered for the current runtime/session with matching hashes, source, receipts and job state. A local doctor, an active plugin, an HTTP 200 or a completed MCP read does not replace either criterion. Do not export the private context/log files.

For Codex, keep the existing evidence and first inspect `/hooks` using `--open codex`. If its definitions need refreshing, use `--refresh-runtime codex`, reopen it, review the changed definitions in `/hooks`, then exit normally. Only after approval run `--run-context codex`, `--run codex` and `--collect`. The changed hook command requires native approval again. Do not use a hook-trust bypass or change the configured model to hide a failure.

## Reference contracts

- [OpenCode server hooks and SDK](https://opencode.ai/v2/docs/build/plugins/server/): the named context hook, message shape and session-specific location checks.
- [OpenCode API schemas](https://opencode.ai/v2/docs/api): `session.created`, `SessionStatusUpdated`, HTTP envelopes and RPC transport.
- [Codex hooks](https://learn.chatgpt.com/docs/hooks): exact-definition trust, synchronous SessionEnd and hook diagnostics.
