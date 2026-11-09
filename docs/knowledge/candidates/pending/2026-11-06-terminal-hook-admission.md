---
proposed_by: debug-root-cause
tipo: gotcha
category: GOTCHA
title: Terminal admission must finish before native CLI teardown
fecha: 2026-11-06
evidencia: Configuration regression failed on 0.1.5 and passed on the adopted 0.1.6 source; complete Windows client suite 74/74 and adopted-root targeted checks 2/2. Native retest remains pending.
fuentes:
  - docs/roadmap/2026-11-05-automatic-memory/testing/native-runtime-0.1.6.md
  - https://code.claude.com/docs/en/hooks#configure-an-async-hook
tags:
  - component:cli
  - event:lifecycle
  - provider:claude-code
---
# Terminal admission and print-mode teardown

Symptom: a native print-mode Stop hook can report cancelled even after its lifecycle event has reached storage.

Cause: asynchronous hooks can still be running when the native CLI tears down. Claude documents that print-mode teardown kills unfinished async hooks. Kairos configured its terminal handlers as async, so local admission and its acknowledgement were not ordered before teardown. The mixed historical stream does not conclusively identify the command behind every cancellation.

Use synchronous, bounded Stop and SessionEnd handlers for local admission. Keep generation work in the independent dispatcher and preserve fail-soft behavior. Do not increase an async timeout as a substitute, fabricate missing closures or suppress cancelled outcomes merely because persistence succeeded.

Recognizable signal: the next time a print-mode terminal hook reports cancelled while receipts show a delivered event, inspect whether admission is asynchronous before changing storage, models or timeouts.

Regression: Claude terminal hooks finish bounded admission before print-mode teardown in packages/kairos-cli/tests/lifecycle.test.mjs. The adopted source passes the full candidate suite and byte comparison. Final native validation and attribution of any remaining cancellation are still required; this proposal is not approval or proof of a clean new native run.
