# Remaining native acceptance: Codex trust and Claude shutdown

## Codex: observed configuration

At this inspection the Codex fixture still uses Kairos 0.1.3 with `capture=summary` and `context=auto`. User configuration enables hooks and trusts the parent workspace. Persisted trust state contains exactly two fixture selectors: SessionStart and UserPromptSubmit. No fixture trust records for Stop or SessionEnd were observed. Those two saved records alone do not prove the current definitions trusted: native trust is tied to the exact current hash.

The installed CLI generated its experimental JSON schemas successfully. Its native `hooks/list` request accepts a list of working directories and returns each hook's enabled/trust state and current hash. Attempts to inspect this through a separate stdio app server failed before initialization with access denied / OS error 5. A read-only proxy attempt against the running control socket was also denied. Neither attempt created a thread, ran a model, changed trust or bypassed approval. No native diagnostic bodies, configuration secrets or transcripts are exported.

Consequently the remaining action is explicit native review, not another blind model test:

```powershell
python kairos/scripts/accept-native-clients.py --refresh-runtime codex
python kairos/scripts/accept-native-clients.py --open codex
```

The working installer is deliberately held at **0.1.5** while that operation is pending. In the native UI, open `/hooks`, review the Kairos fixture definitions, and approve the exact current definitions, especially SessionStart, UserPromptSubmit, Stop and SessionEnd. Exit normally. The operator is asked to confirm their state before further bounded tests. No trust record is edited by Kairos or by this diagnostic.

Reference: [Codex hook review and trust](https://learn.chatgpt.com/docs/hooks#review-and-trust-hooks). The observed two-record inventory is partial evidence; it does not substitute for the native per-definition status.

## Claude: reproduction and isolation

The retained 09:10 UTC native output has one Stop response with exit 1, outcome `cancelled`, and empty output/stdout/stderr. Live persistence nevertheless verifies the session's four lifecycle events, including Stop and SessionEnd. There are no failed or pending jobs in that accepted capture proof.

The fixture's Kairos Stop and SessionEnd handlers are asynchronous. Its explicit custom-agents 3.2.1 plugin declares no Stop handler; it does declare SessionEnd. The native initialization also lists four built-in plugins whose virtual paths cannot be read as ordinary directories. Native hook packets do not identify the command/source for the cancelled Stop. Therefore the mixed output does not conclusively attribute that individual cancellation to one command, and that attribution remains an explicit limitation.

The configuration defect is established independently: [Claude's documented print-mode teardown](https://code.claude.com/docs/en/hooks#configure-an-async-hook) cancels unfinished async hooks and reports `cancelled`. An asynchronous terminal hook therefore cannot guarantee completion of its local admission before the CLI tears down. A larger async timeout is not a correction: the documented runtime does not enforce `timeout` after an async hook enters the background.

## Isolated correction, not yet applied to the working installer

Candidate **0.1.6** is prepared under the ignored `kairos/.cache/claude-terminal-candidate-0.1.6/`. The production package source remains 0.1.5 while the operator reviews Codex; no moving hook definitions are introduced during that review.

The candidate makes only Claude Stop and SessionEnd synchronous, with an explicit eight-second bound. They wait for local dispatcher admission, not model generation. Other ordinary hooks remain asynchronous. Context, event content, privacy rules and OpenCode behavior are unchanged. The collector still reports cancelled native hooks; the change does not hide warnings or fabricate success. Project settings' explicit timeout can raise Claude's SessionEnd budget according to its documented rules; no global environment timeout is changed.

The regression `Claude terminal hooks finish bounded admission before print-mode teardown` failed on the copied 0.1.5 source (`async=true` instead of absent), then passed with the candidate. The complete isolated Windows client suite passes **74/74**, without skips, including upgrade/recovery from 0.1.5. This verifies installer/runtime behavior; it is not a new Claude native acceptance run.

After Codex's definitions have been reviewed, the candidate can be adopted without changing that already-installed Codex fixture. Claude must then be refreshed explicitly and rerun through the bounded native test. Closing its diagnostic requires both live persistence and a clean native terminal-hook outcome. If the mixed stream still shows a cancellation, source attribution must continue; it must not be suppressed because storage succeeded.

C-08 and A-01/A-07 remain open. No working project, server policy, credential, model, port, index or data volume changed during this investigation. No knowledge candidate has been promoted; the terminal-hook lesson is recorded here pending the project's curation workflow after the applied fix and native validation.
