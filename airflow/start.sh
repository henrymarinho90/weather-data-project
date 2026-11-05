#!/usr/bin/env bash
# Airflow container entrypoint: work out where ./dbt lives on the HOST (the
# DockerOperator mounts it through the host's Docker daemon), set the Airflow
# 'mcp' user's password, then run Airflow.
set -euo pipefail

if [ -z "${DBT_HOST_PATH:-}" ]; then
    # This container mounts ./airflow/dags from the repo checkout; ./dbt is next to
    # ./airflow, wherever the checkout is (laptop, Coolify's application folder, CI)
    DBT_HOST_PATH=$(python - <<'PY'
import os, socket
import docker

mounts = docker.from_env().containers.get(socket.gethostname()).attrs["Mounts"]
dags = next(m["Source"] for m in mounts if m["Destination"] == "/opt/airflow/dags")
print(os.path.join(os.path.dirname(os.path.dirname(dags)), "dbt"))
PY
)
    case "$DBT_HOST_PATH" in
        /run/desktop/*)
            # Docker Desktop (WSL) sometimes reports placeholder mount sources that
            # the DockerOperator cannot bind; the dbt tasks would fail with
            # "mkdir /usr/app/weather: read-only file system"
            echo "start.sh: WARNING: detected a Docker Desktop placeholder path." >&2
            echo "start.sh: set DBT_HOST_PATH in .env to the absolute path of ./dbt" >&2
            ;;
    esac
fi
export DBT_HOST_PATH
# Also for processes not started from here (docker exec ... airflow dags test)
echo "$DBT_HOST_PATH" > "${AIRFLOW_HOME:-/opt/airflow}/dbt_host_path"
echo "start.sh: DBT_HOST_PATH=$DBT_HOST_PATH"

airflow db migrate
python /opt/airflow/seed_mcp_user.py
exec airflow standalone
