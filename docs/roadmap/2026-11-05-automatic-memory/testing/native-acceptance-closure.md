# Native memory acceptance completed

Status: **native_acceptance_complete**, verified on 2026-11-06. This closes C-08 and the native-product acceptance items A-01 and A-07 for successful reads, automatic context and technical summary capture.

| Client | Runtime used | MCP reads | Automatic context | Persisted lifecycle | Native failures |
| --- | --- | --- | --- | --- | --- |
| Claude Code | 0.1.6 | projects/context accepted | Scoped SessionStart and UserPromptSubmit context accepted | SessionStart, UserPromptSubmit, Stop, SessionEnd accepted | None; the new Stop is not cancelled |
| Codex | 0.1.5 | projects/context accepted | Independent unpredictable marker echoed without tools | All four events accepted separately in both new test sessions | None |
| OpenCode | 0.1.5 | projects/context accepted, including grouped Code Mode receipts | Independent no-tools proof accepted on 0.1.4, retaining its original timestamp | SessionStart and successful-execution Stop accepted | None |

## Evidence

- [Complete current collector report](native-client-acceptance.json)
- [Closure metadata and validation scope](native-acceptance-closure.json)
- [Claude 0.1.6 readback](native-claude-capture-0.1.6.json), native run beginning 19:35:27 UTC
- [Codex 0.1.5 readback](native-codex-capture-0.1.5.json), separate context/read runs beginning 19:32 UTC
- [OpenCode 0.1.5 capture](native-opencode-capture-0.1.5.json), native run beginning 17:24:52 UTC; separate context proof from 16:12 UTC on 0.1.4

Capture readback compares current notes, immutable event history, source/canonical/capture hashes, project/session identity, provenance and accepted receipts. Technical lifecycle events have no pending generation jobs. Temporary unpredictable context markers were retired with matching receipts. Private outputs and context bodies are not exported into these reports.

The Claude cancellation is absent from the new 0.1.6 native run, and all four new lifecycle events persist. This resolves the current native acceptance diagnostic. It does not reconstruct the old cancelled invocation's exact command attribution, which the retained mixed stream did not expose.

## Verifier correction and tests

The collector previously hard-coded `native_acceptance_incomplete`, even with all per-client criteria accepted. A regression reproduced that false status before the fix. Completion now requires every expected client, successful non-timeout read execution, accepted MCP/context/capture criteria, and no native errors or failed hook outcomes. Loss of a context criterion or a cancelled hook returns the report to incomplete.

The report declares `acceptance_scope: successful_native_read_context_and_technical_summary_capture`; it does not claim complete product parity. The corrected scripts pass **63/63** tests. Client 0.1.6 passed **74/74** Windows tests in the isolated candidate; all source/test bytes matched on adoption, and two targeted checks also passed from the adopted root. The local npm artifact was installed offline with synthetic credentials and all 18 files matched source. Backend tests were not rerun for this collector-only change.

## Operational state and limits

The working distribution is 0.1.6. Installed acceptance fixtures retain their individually validated versions in the table; completing this matrix does not require refreshing all clients to one version and invalidating their trust records. Native trust and consent were respected. Working-project configurations, server models/ports and existing credentials were preserved. Test keys and approved summary consent remain available for the acceptance fixtures; no cleanup/revocation was performed as part of collection.

These are successful native technical-summary cycles for `custom-agents`. They do not establish every native failure/tool path, raw full-mode capture, unrestricted repository analysis, semantic learning quality or all end-user product functionality. Codex/OpenCode native output lacks supported plugin inventory telemetry; that absence is recorded as unknown rather than disabled. The separate, older OpenCode context proof is not relabeled as a new 0.1.5 run.

Full parity remains open in the native-product ledger: A-02 code analysis, A-03 remaining observation/tool-use operations, A-04 team work, A-05 generative corpus queries, A-06 remaining real-data views, and A-08 registry publication/install verification. The package remains local and unpublished. The pending technical-knowledge proposal remains separate from approved knowledge and is not indexed or promoted by this closure.

## Reproduce readback

From the stack root:

```powershell
python kairos/scripts/accept-native-clients.py --collect
```

Collection uses existing scoped read credentials, performs live readback and does not repeat model calls or create test events. A later failed run or missing proof must reopen acceptance. Preserve the private fixture state when reusing this command; do not confuse a local doctor or health response with these native proofs.
