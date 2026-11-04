# Superset 6.1 + Postgres driver + MCP service (fastmcp).
# The official image is "lean" (no DB drivers, no fastmcp), so we add the
# versions pinned by Superset 6.1.0's own pyproject/requirements.
FROM apache/superset:6.1.0-py311

USER root
RUN uv pip install --python /app/.venv/bin/python --no-cache \
        psycopg2-binary==2.9.9 \
        fastmcp==3.1.0 \
        mcp==1.24.0
USER superset
