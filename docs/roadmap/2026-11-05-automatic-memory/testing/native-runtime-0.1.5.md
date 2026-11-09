# OpenCode: automatic context accepted; completion capture correction

## Actual 0.1.4 result

The operator's 2026-11-06 tests started at 16:12 UTC. OpenCode 2.0.12 used `opencode/big-pickle`:

- Automatic context **accepted**: the agent echoed the unpredictable marker without tools. The create/delete receipts match, the synthetic item was retired, and no raw context is exported.
- MCP read **accepted** after correcting the collector: the native Code Mode receipt contains successful `kairos.projects` and `kairos.context` calls grouped into one `execute` result.
- Lifecycle capture **incomplete**: live readback verifies SessionStart for both current sessions, but no Stop. A successful native exit is not treated as a successful capture cycle.

The current metadata-only report is [native-client-acceptance.json](native-client-acceptance.json). No historical completion event was fabricated or blindly replayed.

## Collector correction

Previously the collector accepted only one nested read call per `execute`. The actual result had two completed receipts and two JSON result objects under arbitrary labels. The correction accepts at most three distinct completed Kairos read calls and requires exactly one complete matching between tool-specific result shapes and returned objects. Labels and order are not evidence. It rejects duplicates, extra/missing results, ambiguous associations, truncated output, errors and foreign tools. It never evaluates the code or exports the returned content. Individual responses remain supported.

Two tests failed before the patch. The complete script suite passes 62/62 tests. Recollection of the same private native output confirms the two reads without another model call.

## Completion event investigation

The installed `@opencode/cli` 2.0.12 PE executable has SHA-256 `58d550b26e9241759a6906c65f1e0605eaf512d63cbaf6d8eb472375b9311c95`. REA identified the artifact and analyzed selected inert JavaScript sources recovered from its embedded, NUL-terminated Bun chunks. No executable or bundle bootstrap was run for that analysis. Recovery and evidence remain outside the product under the workspace's ignored `.pytest_cache/rea-opencode-2.0.12/`.

The selected native CLI loop terminates on `session.execution.succeeded`; the execution schema declares that durable event and its session ID. The adapter instead subscribed to `session.status` and looked for an idle state. The executable still contains that legacy status schema, but the bounded source search found its declaration and UI reads, not the completion emission expected by the adapter. Schema presence therefore did not establish the native emission contract. This explains why a registration could appear active while the expected close was absent.

Selected source byte ranges in the original PE and per-source digests are recorded in the ignored recovery manifest. REA analysis reference: `ev_1435a43076e79491bc4cdec8ec759c81d7b7f14cdc7ad08d66243a7572e85b31`. Coverage is explicitly partial: three selected sources, unresolved virtual Bun imports and conservative AST relationships. The attempted generic string feature trace found no graph seeds; it is **not** an end-to-end runtime trace. Native disassembly was unavailable, and no disassembly-based claim is made.

Runtime 0.1.5 subscribes to `session.created` and **`session.execution.succeeded`**. It maps the latter to Stop after checking the individual session's project directory. The native event ID is used when supplied so replay keeps one identity. Failed/interrupted execution events are not mislabeled as successful completion; they remain outside this successful-cycle acceptance. V1 is unchanged. The new regression failed on 0.1.4 and passes on the corrected source, including foreign-root exclusion, stable replay identity and no generation jobs.

## Validation boundary

The 0.1.5 source passes 72/72 client tests on Windows without skips, including upgrade/recovery from 0.1.4. The scripts pass 62/62 tests. Local package verification is recorded separately in `package-0.1.5.json`.

The new completion subscription still needs the native operator-side run. The existing 0.1.4 context proof remains accepted with its original timestamp; it is not relabeled as a 0.1.5 run. Codex automation remains unaccepted and needs native hook approval/diagnosis. Claude retains its earlier successful evidence and the open cancelled-Stop diagnostic. Overall C-08 remains open.

No server deployment or database/index rebuild is needed. Existing credentials, project policy, models, ports, published documents and prior events are preserved. Older local packages remain unchanged; 0.1.5 is not published to npm.

## Operator procedure

Close the OpenCode acceptance session. From the stack root:

```powershell
python kairos/scripts/accept-native-clients.py --refresh-runtime opencode
```

Confirm `runtime_version: 0.1.5`. Do not activate capture again or create another run/key. If the installer reports an active owned dispatcher, stop and wait for its idle shutdown; do not delete the queue or kill other clients.

Then run the native read/capture test and collect its result:

```powershell
python kairos/scripts/accept-native-clients.py --run opencode --model opencode/big-pickle
python kairos/scripts/accept-native-clients.py --collect
```

This is sufficient to check the changed completion subscription while retaining the separately dated 0.1.4 context proof. To prove context under the new runtime too, the optional independent test is:

```powershell
python kairos/scripts/accept-native-clients.py --run-context opencode --model opencode/big-pickle
python kairos/scripts/accept-native-clients.py --collect
```

The remaining capture criterion requires SessionStart and Stop for the **new** native read session, current notes and immutable history, source/canonical hashes, matching accepted receipts and no pending generation jobs. A health response, plugin status or exit code cannot substitute for that readback. Keep private outputs in the existing secret directory.

## Operator readback at 17:25 UTC

The operator applied 0.1.5 and ran the bounded native test beginning at 17:24:52 UTC. Live readback accepted projects/context and both SessionStart and Stop for that new session. Current notes, immutable history, source/canonical/capture hashes and accepted receipts match; jobs are empty. The independent context proof remains the earlier 0.1.4 proof with its original timestamp. Evidence: [native-opencode-capture-0.1.5.json](native-opencode-capture-0.1.5.json). This successful read/capture cycle is accepted; Codex and the existing Claude diagnostic still prevent overall C-08 closure.
