# Community MCP server for Airflow 3 (https://github.com/abhishekbhakat/airflow-mcp-server).
# Airflow itself does not ship an MCP server.
FROM python:3.15.0-slim

RUN useradd --create-home mcp
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# 0.9.1 returns JSON results only as structuredContent with an empty `content`
# list; the MCP spec asks servers to also send it as text for clients that only
# read `content`. Patch that one line (build fails if it no longer matches).
RUN python - <<'EOF'
import pathlib, airflow_mcp_server.toolset as m
path = pathlib.Path(m.__file__)
old = "return ([], parsed)"
new = 'return ([types.TextContent(type="text", text=json.dumps(parsed))], parsed)'
src = path.read_text()
assert src.count(old) == 1, "airflow-mcp-server changed; review this patch"
path.write_text(src.replace(old, new))
EOF
COPY --chmod=755 entrypoint.sh /usr/local/bin/entrypoint.sh

USER mcp
EXPOSE 5009
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
