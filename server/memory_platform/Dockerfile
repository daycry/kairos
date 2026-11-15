ARG PYTHON_IMAGE=python:3.12-slim@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30
FROM ${PYTHON_IMAGE} AS api
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY server/memory_platform/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
    && useradd --create-home --uid 10001 memory
COPY --chown=10001:10001 server/memory_platform /app/memory_platform
# JSON Schemas of structured observations (C-05): server/memory_platform/schemas.py reads them from docs/contracts next to the package
# (this runtime image keeps the package at /app/memory_platform, so /app/docs/contracts).
COPY --chown=10001:10001 docs/contracts/*.schema.json /app/docs/contracts/
USER 10001:10001
EXPOSE 8790
ENTRYPOINT ["python", "-m", "memory_platform.app"]

FROM api AS operator
USER root
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*
USER 10001:10001
ENTRYPOINT ["python", "-m", "memory_platform.admin"]

FROM api AS worker
ENTRYPOINT ["python", "-m", "memory_platform.worker"]
CMD []

# PostgreSQL with pgvector, shared by memory-postgres (docker-compose.yml) and the test targets.
# Same major version (17) and same base digest as before, so an existing data volume needs no pg_upgrade.
# The PGDG repository is already configured in the official image; the package version is pinned.
FROM postgres:17-bookworm@sha256:839fbb5a4942a7758dd93e18b42ea5649807491a0545b5eeeb8f0b8bb11857a5 AS postgres-pgvector
ARG PGVECTOR_VERSION=0.8.7-1.pgdg12+1
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-17-pgvector=${PGVECTOR_VERSION}     && rm -rf /var/lib/apt/lists/*

FROM postgres-pgvector AS test
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/memory-venv
ENV PATH=/opt/memory-venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY server/memory_platform/requirements.txt /tmp/memory-requirements.txt
RUN pip install --no-cache-dir -r /tmp/memory-requirements.txt
WORKDIR /app
# The test image mirrors the repository layout (server/, mcp/, scripts/, docs/ under /app), so the tests resolve the repository root the same way here and in a checkout.
COPY --chown=postgres:postgres server/memory_platform /app/server/memory_platform
COPY --chown=postgres:postgres docs/contracts/*.schema.json /app/docs/contracts/
COPY --chown=postgres:postgres docs/contracts/examples /app/docs/contracts/examples
COPY --chown=postgres:postgres docs/contracts/kairos-mcp.json /app/docs/contracts/kairos-mcp.json
# kairos-mcp (C-03): its contract copy is compared with the exported one, and the in-process chain tests (chain_harness.py) import kairos_mcp from here.
COPY --chown=postgres:postgres mcp /app/mcp
COPY --chown=postgres:postgres scripts/memory-client.py /app/scripts/memory-client.py
COPY --chown=postgres:postgres scripts/memory-admin.py /app/scripts/memory-admin.py
COPY --chown=postgres:postgres scripts/deploy-memory.py /app/scripts/deploy-memory.py
COPY --chown=postgres:postgres scripts/diagnose-deployment.py /app/scripts/diagnose-deployment.py
COPY --chown=postgres:postgres scripts/export-contracts.py /app/scripts/export-contracts.py
COPY --chown=postgres:postgres docker-compose.yml /app/docker-compose.yml
# The portal's nginx.conf and Dockerfile are read as text by the nginx route tests.
COPY --chown=postgres:postgres web/nginx.conf /app/web/nginx.conf
COPY --chown=postgres:postgres web/Dockerfile /app/web/Dockerfile
# Versions of the three components and the changelogs, read as text by test_versions.
COPY --chown=postgres:postgres server/VERSION /app/server/VERSION
COPY --chown=postgres:postgres client/package.json /app/client/package.json
COPY --chown=postgres:postgres CHANGELOG.md CHANGELOG.es.md /app/
COPY --chown=postgres:postgres ollama-proxy /app/ollama-proxy
USER postgres
ENV PYTHONPATH=/app/server
RUN python -m memory_platform.tests.run_postgres

FROM test AS live-probe
# Explicit opt-in target: synthetic payloads only, existing provider/model.
ENV MEMORY_LIVE_PROBE=1
RUN python -m memory_platform.tests.run_postgres

FROM test AS retrieval-eval
# Quality gate (not part of the 191-test suite = 177 + 14 of test_metrics): offline embeddings, isolated PostgreSQL.
# Run: docker build --target retrieval-eval ... (needs network for the apt-get layers; `docker build --network=none` fails there).
# Offline run of the same gate: docker build --target test -t IMG ... && docker run --rm --network=none -e MEMORY_RETRIEVAL_EVAL=1 IMG python -m memory_platform.tests.run_postgres
# The report lists the local network interfaces it observed (no outbound connection is made).
ENV MEMORY_RETRIEVAL_EVAL=1
RUN python -m memory_platform.tests.run_postgres

FROM node:22-bookworm-slim@sha256:3ed98443660ff48413b5af19ecefce3b9d50845a901a43420d47cc63a9fddbe9 AS lifecycle-node
FROM test AS lifecycle-test
COPY --from=lifecycle-node /usr/local/bin/node /usr/local/bin/node
COPY --chown=postgres:postgres client /app/client
ENV MEMORY_CLIENT_PROBE=1
RUN python -m memory_platform.tests.run_postgres
