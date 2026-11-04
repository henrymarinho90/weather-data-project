"""Serve dbt-core-mcp over Streamable HTTP instead of stdio.

dbt-core-mcp only ships a stdio entrypoint (the client spawns it). Running it
over HTTP lets it live in the compose stack next to the Superset and Airflow
MCP servers, on the project network, with the same dbt image as Airflow.
"""
import os

from dbt_core_mcp.server import create_server

PROJECT_DIR = os.getenv("DBT_PROJECT_DIR", "/usr/app/my_project")
PORT = int(os.getenv("MCP_PORT", "5010"))
# safe (default): inspect, lineage, query and test only. full: also build/run/seed.
MODE = os.getenv("DBT_MCP_MODE", "safe")
WRITE_TOOLS = {"build_models", "run_models", "load_seeds", "snapshot_models", "install_deps"}
# Demo/sample UI tool shipped with the package; not useful here
ALWAYS_DISABLED = {"demo_ui"}

server = create_server(project_dir=PROJECT_DIR)
server.app.disable(names=ALWAYS_DISABLED)
if MODE != "full":
    server.app.disable(names=WRITE_TOOLS)
print(f"dbt-core-mcp: project={PROJECT_DIR} mode={MODE} port={PORT}", flush=True)
server.app.run(transport="http", host="0.0.0.0", port=PORT, path="/mcp", show_banner=False)
