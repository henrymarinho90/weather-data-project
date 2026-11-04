# Project overrides, auto-imported at the end of superset_config.py
# (the unmodified upstream template from apache/superset 6.1.0).
import os

# Links Superset generates (e.g. MCP explore links) should point at the host port
WEBDRIVER_BASEURL_USER_FRIENDLY = "http://localhost:8089/"

# --- MCP service (superset mcp run) ---
# https://superset.apache.org/admin-docs/configuration/mcp-server
# Local development only: no auth, every MCP request acts as MCP_DEV_USERNAME.
# The port is bound to 127.0.0.1 in docker-compose. Enable JWT auth
# (MCP_AUTH_ENABLED = True + MCP_JWT_* settings) before exposing it anywhere else.
MCP_AUTH_ENABLED = False
MCP_DEV_USERNAME = os.getenv("MCP_DEV_USERNAME", "admin")
MCP_SERVICE_HOST = "0.0.0.0"
MCP_SERVICE_PORT = int(os.getenv("MCP_PORT", "5008"))
