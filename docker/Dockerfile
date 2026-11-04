# Superset 6.1 + Postgres driver + MCP service (fastmcp).
# The official image is "lean" (no DB drivers, no fastmcp), so we add them:
# psycopg2 as pinned by Superset 6.1.0, fastmcp at the newest 3.x (Superset
# allows <4.0; 3.1.0 has CVE-2026-32871). `uv pip check` guards compatibility.
FROM apache/superset:6.1.0-py311

USER root
RUN uv pip install --python /app/.venv/bin/python --no-cache \
        psycopg2-binary==2.9.9 \
        fastmcp==3.4.11 \
        mcp==1.30.0 \
 && uv pip check --python /app/.venv/bin/python
USER superset
