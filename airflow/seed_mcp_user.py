"""Give the Airflow 'mcp' user (used by the airflow_mcp service) the password
from AIRFLOW_MCP_PASSWORD.

The simple auth manager keeps passwords already present in its passwords file
and only generates the missing ones, so seeding it before `airflow standalone`
makes the mcp password predictable while admin's stays randomly generated.
"""

import json
import os

password = os.getenv("AIRFLOW_MCP_PASSWORD")
path = os.path.join(
    os.getenv("AIRFLOW_HOME", "/opt/airflow"), "simple_auth_manager_passwords.json.generated"
)

if password:
    passwords = {}
    if os.path.exists(path):
        with open(path) as f:
            passwords = json.loads(f.read().strip() or "{}")
    passwords["mcp"] = password
    with open(path, "w") as f:
        f.write(json.dumps(passwords) + "\n")
    print("Seeded password for Airflow user 'mcp'.")
else:
    print("AIRFLOW_MCP_PASSWORD not set; skipping 'mcp' user password seed.")
