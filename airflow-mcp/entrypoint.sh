#!/usr/bin/env bash
# Run airflow-mcp-server with a fresh Airflow JWT and restart it before the
# token expires (Airflow's api_auth.jwt_expiration_time defaults to 24h).
set -uo pipefail

: "${AIRFLOW_URL:=http://af:8080}"
: "${AIRFLOW_MCP_USERNAME:=mcp}"
: "${AIRFLOW_MCP_PASSWORD:?Set AIRFLOW_MCP_PASSWORD in .env}"
: "${AIRFLOW_MCP_MODE:=--safe}"
: "${MCP_PORT:=5009}"
: "${TOKEN_REFRESH:=23h}"

get_token() {
    python - <<'PY'
import json, os, urllib.request
req = urllib.request.Request(
    os.environ["AIRFLOW_URL"] + "/auth/token",
    json.dumps({"username": os.environ["AIRFLOW_MCP_USERNAME"],
                "password": os.environ["AIRFLOW_MCP_PASSWORD"]}).encode(),
    {"Content-Type": "application/json"},
)
print(json.load(urllib.request.urlopen(req, timeout=10))["access_token"])
PY
}

while true; do
    until TOKEN=$(get_token 2>/dev/null); do
        echo "Waiting for Airflow login at ${AIRFLOW_URL} as '${AIRFLOW_MCP_USERNAME}'..."
        sleep 10
    done
    echo "Got Airflow token; starting MCP server (${AIRFLOW_MCP_MODE}) on :${MCP_PORT}/mcp/"
    # --static-tools: publish every tool up front; the default category browser
    # relies on tools/list_changed, which not every MCP client handles
    timeout "${TOKEN_REFRESH}" airflow-mcp-server "${AIRFLOW_MCP_MODE}" --static-tools --http \
        --host 0.0.0.0 --port "${MCP_PORT}" \
        --base-url "${AIRFLOW_URL}" --auth-token "${TOKEN}"
    status=$?
    # 124 = planned restart by timeout; anything else is a crash, so back off
    [ "${status}" -ne 124 ] && echo "MCP server exited (${status}), restarting" && sleep 10
done
