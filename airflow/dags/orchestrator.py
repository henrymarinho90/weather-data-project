import os
import sys
from datetime import datetime, timedelta

from airflow.providers.docker.operators.docker import DockerOperator
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG
from docker.types import Mount

sys.path.append("/opt/airflow/api-request")

from alerting import notify_failure  # noqa: E402


def ingest_weather_data():
    from insert_records import main

    return main()


def dbt_host_path():
    """HOST path of ./dbt: from .env, else as detected by airflow/start.sh."""
    if path := os.environ.get("DBT_HOST_PATH"):
        return path
    detected = os.path.join(os.environ.get("AIRFLOW_HOME", "/opt/airflow"), "dbt_host_path")
    with open(detected) as f:
        return f.read().strip()


def dbt_task(task_id, command):
    """Run a dbt command in the dbt image, on the compose network."""
    return DockerOperator(
        task_id=task_id,
        image=os.environ["DBT_IMAGE"],
        command=command,
        working_dir="/usr/app/weather",
        user=f"{os.environ.get('HOST_UID', '1000')}:{os.environ.get('HOST_GID', '1000')}",
        environment={
            "HOME": "/tmp",
            "DBT_PROFILES_DIR": "/usr/app",
            # Artifacts and logs stay in the (auto-removed) container: the project
            # mount is read-only, whoever owns the checkout on the host
            "DBT_TARGET_PATH": "/tmp/dbt-target",
            "DBT_LOG_PATH": "/tmp/dbt-logs",
            "DB_HOST": os.environ.get("DB_HOST", "db"),
            "DB_PORT": os.environ.get("DB_PORT", "5432"),
            "DB_USER": os.environ["DB_USER"],
            "DB_PASSWORD": os.environ["DB_PASSWORD"],
            "DB_NAME": os.environ["DB_NAME"],
        },
        # Must be a HOST path: DockerOperator talks to the host docker daemon.
        # airflow/start.sh detects it when DBT_HOST_PATH is not set
        mounts=[
            Mount(
                source=dbt_host_path(),
                target="/usr/app",
                type="bind",
                read_only=True,
            )
        ],
        network_mode=os.environ.get("DOCKER_NETWORK", "weather_network"),
        docker_url="unix:///var/run/docker.sock",
        auto_remove="success",
        mount_tmp_dir=False,
    )


with DAG(
    dag_id="api-dbt-orchestrator",
    description="Ingest weather data and transform it with dbt",
    start_date=datetime(2026, 10, 26),
    # Twice daily (08:00 and 20:00 UTC) = ~60 API calls/month, within the free tier
    schedule="0 8,20 * * *",
    catchup=False,
    max_active_runs=1,
    default_args={
        # One retry covers startup races; note an ingest retry can spend a second API call
        "retries": 1,
        "retry_delay": timedelta(minutes=2),
        # A hung API or dbt run must not block every later run (max_active_runs=1)
        "execution_timeout": timedelta(minutes=10),
        # Webhook alert once a task has failed for good (ALERT_WEBHOOK_URL in .env)
        "on_failure_callback": notify_failure,
    },
) as dag:
    ingest = PythonOperator(
        task_id="ingest_weather_data",
        python_callable=ingest_weather_data,
    )
    transform = dbt_task("transform_data_task", "build")
    # Fails when the newest observation is older than the source's error_after
    # (e.g. mock mode or a cached API response), even though dbt build passed
    freshness = dbt_task("check_source_freshness", "source freshness")

    ingest >> transform >> freshness
