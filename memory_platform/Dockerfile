ARG PYTHON_IMAGE=python:3.12-slim@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30
FROM ${PYTHON_IMAGE} AS api
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY memory_platform/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
    && useradd --create-home --uid 10001 memory
COPY --chown=10001:10001 memory_platform /app/memory_platform
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

FROM postgres:17-bookworm@sha256:839fbb5a4942a7758dd93e18b42ea5649807491a0545b5eeeb8f0b8bb11857a5 AS test
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/memory-venv
ENV PATH=/opt/memory-venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY memory_platform/requirements.txt /tmp/memory-requirements.txt
RUN pip install --no-cache-dir -r /tmp/memory-requirements.txt
WORKDIR /app
COPY --chown=postgres:postgres memory_platform /app/memory_platform
COPY --chown=postgres:postgres scripts/memory-client.py /app/scripts/memory-client.py
COPY --chown=postgres:postgres scripts/memory-admin.py /app/scripts/memory-admin.py
COPY --chown=postgres:postgres scripts/deploy-memory.py /app/scripts/deploy-memory.py
COPY --chown=postgres:postgres docker-compose.yml /app/docker-compose.yml
USER postgres
ENV PYTHONPATH=/app
RUN python -m memory_platform.tests.run_postgres

FROM test AS live-probe
# Explicit opt-in target: synthetic payloads only, existing provider/model.
ENV MEMORY_LIVE_PROBE=1
RUN python -m memory_platform.tests.run_postgres

FROM node:22-bookworm-slim@sha256:3ed98443660ff48413b5af19ecefce3b9d50845a901a43420d47cc63a9fddbe9 AS lifecycle-node
FROM test AS lifecycle-test
COPY --from=lifecycle-node /usr/local/bin/node /usr/local/bin/node
COPY --chown=postgres:postgres packages/kairos-cli /app/client
ENV MEMORY_CLIENT_PROBE=1
RUN python -m memory_platform.tests.run_postgres
