"""Give the Airflow 'mcp' user (used by the airflow_mcp service) the password
from AIRFLOW_MCP_PASSWORD.

The simple auth manager keeps passwords already present in its passwords file
and only generates the missing ones, so seeding it before `airflow standalone`
makes the mcp password predictable while admin's stays randomly generated.
"""

import json
import os

password = os.getenv("AIRFLOW_MCP_PASSWORD")
# Same lookup as Airflow's simple auth manager: the configured file, else the default
path = os.getenv("AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_PASSWORDS_FILE") or os.path.join(
    os.getenv("AIRFLOW_HOME", "/opt/airflow"), "simple_auth_manager_passwords.json.generated"
)

if password:
    # Private directory: only the airflow user can read the passwords
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    passwords = {}
    if os.path.exists(path):
        with open(path) as f:
            passwords = json.loads(f.read().strip() or "{}")
    passwords["mcp"] = password
    with open(path, "w") as f:
        f.write(json.dumps(passwords) + "\n")
    os.chmod(path, 0o600)
    print("Seeded password for Airflow user 'mcp'.")
else:
    print("AIRFLOW_MCP_PASSWORD not set; skipping 'mcp' user password seed.")
