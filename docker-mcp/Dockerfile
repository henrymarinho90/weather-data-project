# Read-only Docker MCP server for this compose project (see server.py).
FROM python:3.12.16-slim

RUN useradd --create-home mcp
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY docker_helpers.py server.py /opt/docker-mcp/

USER mcp
WORKDIR /opt/docker-mcp
EXPOSE 5012
ENTRYPOINT ["python", "/opt/docker-mcp/server.py"]
