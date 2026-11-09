# Claude terminal admission: runtime 0.1.6

Current native status: Claude 0.1.6, Codex 0.1.5 and OpenCode 0.1.5 successful read/context/capture acceptance is complete. Claude's new 19:35 UTC run has no cancelled terminal hooks and all four events persist. See [native closure](native-acceptance-closure.md). The procedures below are retained for reproducibility; they are not pending actions.

## Applied source and accepted native test

The isolated 0.1.6 correction has been adopted into `packages/kairos-cli/` after checking every baseline file and comparing the complete source/test copy byte for byte. The package contains the exact candidate bytes that passed 74/74 Windows client tests. Two targeted tests also pass from the adopted root: terminal-hook configuration and upgrade/recovery from 0.1.5. Offline npm installation of the same artifact configured all three synthetic clients and passed local doctor without contacting a provider.

Artifact: `packages/kairos-cli/artifacts/daycry-kairos-0.1.6.tgz`.
SHA-256: `41bbf76ed6ee7252ee3656fb6b04003ed611edaa0ced97ee1256dd42d9471882`.
Size: 39,637 bytes; 18 package files, all matching the adopted source. The package remains local and unpublished. Prior packages are unchanged.

## Change and evidence

Claude Stop and SessionEnd handlers are now synchronous with an eight-second bound. They finish local dispatcher admission before returning. Ordinary tool/compaction hooks remain asynchronous. Model generation stays in the independent dispatcher, and outages remain fail-soft. The change does not request model generation, change captured content, hide diagnostics or alter native approval policy.

[Claude's hook reference](https://code.claude.com/docs/en/hooks#configure-an-async-hook) documents that print-mode teardown kills unfinished asynchronous hooks and finalizes them as cancelled. An async timeout is not enforced once such a hook enters the background. The regression failed on 0.1.5 because terminal handlers had `async=true`, and passes with 0.1.6.

The retained historical native run has a cancelled Stop response with empty stdout/stderr, although all four lifecycle events persisted correctly. The explicitly loaded custom-agents plugin has no Stop handler; built-in plugins have virtual paths and native packets do not name the command/source. Exact attribution of that individual historical cancellation remains limited. The new 19:35 UTC native run has clean terminal outcomes and matching persistence, resolving the current diagnostic.

## Codex coordination

The operator refreshed and reviewed the Codex fixture before this adoption. Its installed runtime remains **0.1.5**, with seven saved approvals, including SessionStart, UserPromptSubmit, Stop and SessionEnd. That fixture uses its own stable runtime files and was not modified by adopting the working 0.1.6 package. Its newly approved definitions must not be refreshed again merely to run the pending tests.

The following Codex procedure was completed successfully; it is retained for reproduction from the stack root:

```powershell
python kairos/scripts/accept-native-clients.py --run-context codex
python kairos/scripts/accept-native-clients.py --run codex
python kairos/scripts/accept-native-clients.py --collect
```

The native trust-status API is inaccessible from the tool session. Operator confirmation plus the saved approval records are recorded; neither is relabeled as successful native context/capture execution. Collection must verify the new session independently.

## Claude application and acceptance

After the Codex run, close the Claude acceptance session and explicitly refresh only its fixture:

```powershell
python kairos/scripts/accept-native-clients.py --refresh-runtime claude
python kairos/scripts/accept-native-clients.py --run claude
python kairos/scripts/accept-native-clients.py --collect
```

Expect runtime 0.1.6 from the refresh. Reuse the existing summary key and project policy; do not call `--prepare` or `--enable-capture` again. The refresh must stop rather than switch an active owned dispatcher. If it stops, inspect its status and wait for idle shutdown; do not delete queues or kill other clients.

Accept only if projects/context succeed, native context hooks contain valid scoped references, terminal hook diagnostics are clean, and the current session's SessionStart, UserPromptSubmit, Stop and SessionEnd match live notes/history/receipts and hashes. Empty generation-job lists are expected for technical lifecycle summaries. Preserve the previous proof with its timestamp; do not reuse its events to accept the new session. If cancellation remains, investigate source attribution rather than suppressing it.

No Docker rebuild, index rebuild, server policy, credential, model, port or working-project change is required. OpenCode retains its accepted 0.1.5 read/capture run and separately dated 0.1.4 context proof. C-08 and A-01/A-07 are closed for the accepted technical-summary cycle. The six other parity items remain open in the native-product ledger.

## Technical knowledge handoff

The curation service recorded the terminal-admission lesson as a pending candidate, with no approval, indexing or publication:

- Candidate: `docs/knowledge/candidates/pending/2026-11-06-terminal-hook-admission.md`
- SHA-256: `1386937f9b6587f3f0cffcebd4861f7473f545511e3415103f2f3d2df622fa52`
- Producer: `debug-root-cause`

The selected automatic-memory ledger records the original proposal reference. The candidate explicitly preserves the native-validation and source-attribution limitations. Curator review is separate from tests and native acceptance.
