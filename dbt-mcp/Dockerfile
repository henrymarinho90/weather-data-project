# dbt-core-mcp (https://github.com/NiclasOlofsson/dbt-core-mcp) on the same dbt
# image Airflow uses, so the MCP server drives the exact same dbt + adapter.
# Passed from DBT_IMAGE in .env by docker-compose
ARG DBT_IMAGE=ghcr.io/dbt-labs/dbt-postgres:1.9.0
FROM ${DBT_IMAGE}

# dbt-core-mcp runs dbt with its own interpreter (sys.executable), so it must
# share dbt's Python. Pins come from dbt-core-mcp 1.7.1's uv.lock; `pip check`
# fails the build if any upgrade breaks a requirement declared by dbt.
RUN pip install --no-cache-dir dbt-core-mcp==1.7.1 fastmcp==3.0.0b1 mcp==1.26.0 \
        pydantic==2.12.5 pydantic-core==2.41.5 authlib==1.6.6 \
 && pip check

COPY server.py /opt/dbt-mcp/server.py
EXPOSE 5010
ENTRYPOINT ["python", "/opt/dbt-mcp/server.py"]
