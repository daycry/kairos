ARG PYTHON_IMAGE=python:3.12-slim@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30
FROM ${PYTHON_IMAGE}
# kairos-mcp: MCP front of the Kairos REST API. Build context is mcp/ and nothing from the server is copied (CA-08).
# It has no database driver and no credential of its own: the only configuration is KAIROS_API_URL (and optional KAIROS_API_TIMEOUT).
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
    && useradd --create-home --uid 10001 kairos
# The image carries its own Dockerfile so that its isolation tests (tests/test_health.py) read the real file.
COPY --chown=10001:10001 VERSION Dockerfile /app/
COPY --chown=10001:10001 contract /app/contract
COPY --chown=10001:10001 kairos_mcp /app/kairos_mcp
COPY --chown=10001:10001 tests /app/tests
USER 10001:10001
EXPOSE 8791
CMD ["python", "-m", "kairos_mcp.app"]
