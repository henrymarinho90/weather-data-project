# dbt-core-mcp (https://github.com/NiclasOlofsson/dbt-core-mcp) on the same dbt
# image Airflow uses, so the MCP server drives the exact same dbt + adapter.
# Passed from DBT_IMAGE in .env by docker-compose
ARG DBT_IMAGE=ghcr.io/dbt-labs/dbt-postgres:1.9.0
FROM ${DBT_IMAGE}

# dbt-core-mcp runs dbt with its own interpreter (sys.executable), so it must
# share dbt's Python. fastmcp/mcp match docker-mcp (fastmcp < 3.2 has
# CVE-2026-32871); `pip check` fails the build if an upgrade breaks dbt.
RUN pip install --no-cache-dir dbt-core-mcp==1.7.1 fastmcp==3.4.11 mcp==1.30.0 \
 && pip check

COPY server.py /opt/dbt-mcp/server.py
# Non-root by default (docker-compose also sets the host uid/gid)
USER 1000:1000
EXPOSE 5010
ENTRYPOINT ["python", "/opt/dbt-mcp/server.py"]
