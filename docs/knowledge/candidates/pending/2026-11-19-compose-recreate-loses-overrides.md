---
content_origin: agent
proposed_by: retro
tipo: gotcha
category: GOTCHA
title: Recreating a Compose service with only the base file drops the overrides it was created with
fecha: 2026-11-19
evidencia: Milestone B review of reliable-operations, attempt 2 (finding N1, Important) and attempt 3 (R3-1, R3-2, Important); fixed in fix2 (4c069d0) and fix3 (f480c34, a6ff425) with RED tests in server/memory_platform/tests/test_deploy.py and test_deploy_rollback.py; mutation removing the project filter killed by 17 tests.
fuentes:
  - docs/roadmap/2026-11-15-reliable-operations/review.md
  - docs/roadmap/2026-11-15-reliable-operations/execution-history.md
  - scripts/deploy-memory.py
tags:
  - component:deploy
  - tool:docker-compose
  - initiative:reliable-operations
---
# Recreating a Compose service with only the base file drops its overrides

Symptom: after `scripts/deploy-memory.py --apply` or `--rollback`, `memory-backup` lost its `egress` network and off-site copies to an `rclone:` destination stopped uploading. In an isolated rehearsal, the same recreation could mount the installation image and backup volume.

Cause: `docker compose -f docker-compose.yml up -d --no-deps --force-recreate <service>` rebuilds the container from the files on the command line only. The `egress` network came from `docker-compose.backup-rclone.yml`, and the rehearsal isolation came from the rehearsal `compose.override.yml`. Neither was on the command line.

Instead: read the label `com.docker.compose.project.config_files` of the running container. Use `docker ps -a` filtered by `com.docker.compose.project=<project>`, `com.docker.compose.service=<service>` and `com.docker.compose.oneoff=False`, with no shell. Recreate with exactly those `-f` files, in label order, only when every one is on an allow-list; in a rehearsal, also require the rehearsal override. Otherwise do not recreate: report `<name>_recreate_skipped` and print a manual command with the whole label, or with an explicit marker when the label is missing or unreliable.

Recognizable signal: the next time a deploy or rollback step runs `up --force-recreate` with a fixed `-f` list, or a service loses a network or volume after a deployment, check which Compose files its container was created with before changing the deploy script.

Regression: `test_milestone_b_review_n1_*` and `test_milestone_b_review_fix3_*` in server/memory_platform/tests/test_deploy.py and test_deploy_rollback.py.
