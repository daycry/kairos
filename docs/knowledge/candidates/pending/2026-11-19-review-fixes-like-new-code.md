---
content_origin: agent
proposed_by: retro
tipo: lesson
category: LESSON
title: A review fix is new code and needs the full review lenses
fecha: 2026-11-19
evidencia: In the milestone B closing review of reliable-operations, all three Important findings after attempt 1 were introduced by earlier fixes (fix1 introduced N1; fix2 introduced R3-1 and R3-2), forcing a fix3 outside the three-attempt loop. The user named «Correcciones en cadena» as the main deviation and «Revisar el fix entero» as the change for the next initiative (retro 2026-11-19).
fuentes:
  - docs/roadmap/2026-11-15-reliable-operations/retro.md
  - docs/roadmap/2026-11-15-reliable-operations/review.md
tags:
  - process:adversarial-review
  - role:orchestrator
  - initiative:reliable-operations
---
# A review fix is new code and needs the full review lenses

What happened: the milestone B review needed three attempts and an extra fix. Each fix closed the finding it targeted and opened a new Important one in the same function: off-site copies broke, the manual command was wrong, and rehearsal isolation broke. The re-review of each fix only checked that the reported finding was gone.

Lesson: when a fix adds behaviour, rather than just changing a value or a message, review its diff with the same lenses as a phase. Lens B needs operator edge cases: overrides, rehearsal versus installation, missing or duplicated data, and the manual fallback path. The brief to the fixer should list those edge cases up front, as the CPU-class lesson of three-components did for denial of service.

Recognizable signal: the next time a review finding is fixed by new branching logic in deploy, recovery or operator code, or a re-review comes back with a new Important finding in the same function, run the full lenses on the fix diff before calling the finding closed.
