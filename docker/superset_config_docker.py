# Project overrides, auto-imported at the end of superset_config.py
# (the unmodified upstream template from apache/superset 6.1.0).
import os

# Public address: http://localhost:8089 locally, https://superset.example.com
# behind a reverse proxy (Coolify). Links Superset generates (e.g. MCP explore
# links) use it.
PUBLIC_URL = os.getenv("SUPERSET_PUBLIC_URL", "http://localhost:8089").rstrip("/")
WEBDRIVER_BASEURL_USER_FRIENDLY = f"{PUBLIC_URL}/"

if PUBLIC_URL.startswith("https://"):
    # Behind a TLS-terminating proxy: trust its X-Forwarded-* headers (one hop),
    # build https URLs and only send cookies over https
    ENABLE_PROXY_FIX = True
    PROXY_FIX_CONFIG = {"x_for": 1, "x_proto": 1, "x_host": 1, "x_port": 1, "x_prefix": 1}
    PREFERRED_URL_SCHEME = "https"
    SESSION_COOKIE_SECURE = True

# --- MCP service (superset mcp run) ---
# https://superset.apache.org/admin-docs/configuration/mcp-server
# Local development only: no auth, every MCP request acts as MCP_DEV_USERNAME.
# The port is bound to 127.0.0.1 in docker-compose. Enable JWT auth
# (MCP_AUTH_ENABLED = True + MCP_JWT_* settings) before exposing it anywhere else.
MCP_AUTH_ENABLED = False
MCP_DEV_USERNAME = os.getenv("MCP_DEV_USERNAME", "admin")
MCP_SERVICE_HOST = "0.0.0.0"
MCP_SERVICE_PORT = int(os.getenv("MCP_PORT", "5008"))
